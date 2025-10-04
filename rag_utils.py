# Parsing per tesi:
# - 1^ generazione: "bullet/numero + testo - categoria"
# - 2^ generazione: intestazione categoria + elenco numerato "1.", "2.", "3." (solo righe numerate = requisiti)
# Filtri: escludi "Conformità/Standard/Descrizione/Note" ovunque.
# Output:
#   - parse_gen1: items1 ([(testo, categoria)], bycat1)
#   - parse_gen2: items2 ([(testo, categoria)], bycat2) basato SOLO su righe numerate
#   - conteggi_per_categoria
#   - unisci_testi_senza_categoria (solo contenuto 1^+2^)
#   - ricomponi_testo_numerato_solo_contenuto

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import List, Tuple, Dict

# -----------------------------
# Pulizia base e filtro righe non-requisito
# -----------------------------

_MD_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"\*(.+?)\*"), r"\1"),
    (re.compile(r"`(.+?)`"), r"\1"),
]

_NON_REQ_PREFIXES = (
    "conformità:", "conformita:",
    "descrizione:",
    "note aggiuntive:",
    "note:",
    "standard:",
    "owasp top 10",
)

def strip_md(s: str) -> str:
    t = s
    for pat, rep in _MD_PATTERNS:
        t = pat.sub(rep, t)
    t = t.replace("**", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_non_requirement_line(line: str) -> bool:
    l = strip_md(line).lower().strip()
    if not l:
        return True
    for p in _NON_REQ_PREFIXES:
        if l.startswith(p):
            return True
    if l in {"---", "--", "—"}:
        return True
    return False

# -----------------------------
# 1^ generazione: "bullet/numero + testo - categoria"
# -----------------------------

_REQ_CLASSIC = re.compile(r"^\s*(?:\d+[\.)]|[-•–—])\s*(.+?)\s*[-–—]\s*(.+?)\s*$")

def parse_gen1(raw_text: str) -> Tuple[List[Tuple[str, str]], Dict[str, List[str]]]:
    items: List[Tuple[str, str]] = []
    by_cat: Dict[str, List[str]] = defaultdict(list)

    for line in raw_text.splitlines():
        line = line.strip()
        if is_non_requirement_line(line):
            continue
        m = _REQ_CLASSIC.match(line)
        if not m:
            continue
        testo = strip_md(m.group(1)).strip()
        categoria = strip_md(m.group(2)).strip()
        # Evita che OWASP venga scambiato per categoria
        if re.match(r"(?i)A0?\d(?::\s*2021)?", categoria):
            continue
        items.append((testo, categoria))
        by_cat[categoria].append(testo)

    return items, by_cat

# -----------------------------
# 2^ generazione: intestazione categoria + elenco numerato "1.", "2.", "3."
# -----------------------------

# Header: “### **Categoria**” o “### Categoria” (accetta 1–6 cancelletto)
_HEADER_H3 = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$")

# Riga numerata: “1.”, “1)”, “1-”, “1–”, con/ senza spazio dopo
_NUM = re.compile(r"^\s*(\d+)\s*[\.\)\-–—]\s*(.+?)\s*$", re.IGNORECASE)

def _norm(s: str) -> str:
    return strip_md(s).casefold().strip()

def parse_gen2(texto: str, categorie_valide: Iterable[str] = None) -> Tuple[List[Tuple[str, str]], Dict[str, List[str]]]:
    """
    Parser a stati robusto per la 2^ generazione.

    Logica:
    - Scorre riga per riga.
    - Quando incontra “### …” prende il titolo come categoria (ripulendo **…**); se cateogorie_valide è fornita, accetta solo se la categoria è dentro alla whitelist.
    - Subito dopo, entra in raccolta di righe numerate. Se la prima riga dopo il titolo NON è numerata, esce (header senza elenco: sono note o testo).
    - Per ogni riga numerata sotto quell’header:
        * estrae il testo dopo il numero,
        * scarta righe che iniziano con “Conformità/Descrizione/Note”,
        * tronca al primo “ - ” (prende solo il requisito prima del trattino),
        * salva (testo, categoria).
    - Si ferma quando l’elenco numerato termina o quando trova un nuovo header “### …”.
    """
    items: List[Tuple[str, str]] = []
    by_cat: Dict[str, List[str]] = defaultdict(list)

    whitelist = {_norm(c) for c in categorie_valide} if categorie_valide else None

    lines = texto.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i].rstrip("\n")
        s = raw.strip()
        i += 1

        # Cerca header H3 (“### …”)
        mH = _HEADER_H3.match(s)
        if not mH:
            continue

        # Ripulisci il titolo da markup (**…**) e spazi
        title = strip_md(mH.group(1)).strip()

        # Se il titolo ha suffissi tipo “ – note”, tronca prima del separatore comune
        title = re.split(r"\s[-–—:]\s", title, 1)[0].strip()

        # Se è presente whitelist, accetta solo titoli in whitelist
        if whitelist is not None and _norm(title) not in whitelist:
            # non è un blocco categoria di interesse; continua
            continue

        current_cat = title
        # Ora verificare se subito dopo l’header iniziano righe numerate
        # Salta eventuali righe vuote o di note fino alla prima significativa
        start = i
        while start < n and not lines[start].strip():
            start += 1

        if start >= n:
            # non c’è nulla dopo l’header
            continue

        # Se la prima riga significativa dopo l'header NON è numerata, ignora questo header (probabili note/testo)
        if not _NUM.match(lines[start].strip()):
            # non entra in raccolta
            continue

        # Entra in raccolta: consumare righe numerate finché matchano
        j = start
        while j < n:
            sj = lines[j].strip()
            # Se incontriamo un nuovo header, fermare la raccolta
            if _HEADER_H3.match(sj):
                break

            mN = _NUM.match(sj)
            if not mN:
                # Elenco interrotto; fermarsi
                break

            testo = strip_md(mN.group(2)).strip()

            # Filtro: scarta non-requisito anche se numerato
            if is_non_requirement_line(testo):
                j += 1
                continue

            # Tronca alla prima occorrenza di " - " per buttare la coda OWASP/standard a destra
            if " - " in testo:
                testo = testo.split(" - ", 1)[0].strip()

            if testo:
                items.append((testo, current_cat))
                by_cat[current_cat].append(testo)

            j += 1

        # Proseguire da j (fine blocco)
        i = j

    return items, by_cat

# -----------------------------
# Conteggio e Unione delle generazioni (senza definire le categorie di sicurezza)
# -----------------------------

def conteggi_per_categoria(by_cat: Dict[str, List[str]]) -> Dict[str, int]:
    return {c: len(lst) for c, lst in by_cat.items()}

def unisci_testi_senza_categoria(items1: List[Tuple[str, str]], items2: List[Tuple[str, str]]) -> List[str]:
    return [t for (t, _c) in items1] + [t for (t, _c) in items2]

def ricomponi_testo_numerato_solo_contenuto(testi: List[str]) -> str:
    righe = []
    for i, t in enumerate(testi, start=1):
        righe.append(f"{i}. {t}")
    return "\n".join(righe)
