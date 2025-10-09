import os
import re
import json
from collections import Counter
from langchain_community.document_loaders import TextLoader
from langchain.chat_models import ChatOpenAI
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA

from rag_utils import strip_code_fences, extract_json_braces, load_loose_json
from pdf_utils import export_requisiti_pdf

# Costanti OWASP/Categorie
OWASP_KEYS = {f"A0{i}:2021" for i in range(1,10)} | {"A10:2021"}
SOGLIA_MIN_CAT = 2
CANON_MAP = {
    "Cryptography": "Data Protection"
}

# Carica le variabili d'ambiente
load_dotenv()
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Caricare i documenti txt nella cartella guidelines attraverso il textloader (per importare tutti i contenuti). Inoltre servono i metadata per la comprensione delle categorie e top10 owasp coperte da ogni cheat sheet
docs_folder = "./guidelines"
metadata_file = "./guidelines/metadata.json"

with open(metadata_file, "r", encoding="utf-8") as f:
    metadata_map = {m["filename"]: m for m in json.load(f)}

all_documents = []

for filename in os.listdir(docs_folder):
    if filename.endswith('.txt'):
        loader = TextLoader(os.path.join(docs_folder, filename), encoding="utf-8")
        docs = loader.load()

        # valori di default
        category = "unknown"
        owasp_top_10 = ""

        if filename in metadata_map:
            meta = metadata_map[filename]
            category = meta.get("category", "unknown")
            owasp_top_10 = ", ".join(meta.get("owasp_top_10", []))

        for doc in docs:
            doc.page_content = (
                f"[Categoria: {category}]\n"
                f"[OWASP Top 10: {owasp_top_10}]\n\n"
                f"{doc.page_content}"
            )
            
            doc.metadata.update({
                "filename": filename,
                "category": category,
                "owasp_top_10": meta.get("owasp_top_10", []) if filename in metadata_map else []
            })
        
        all_documents.extend(docs)

# Chunking
text_splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=100)
split_documents = text_splitter.split_documents(all_documents)

# Embeddings con modelli di HuggingFace
print("Caricamento documenti completato")
print("Creazione embeddings...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Creazione FAISS per motore di ricerca interno
print("Creazione FAISS...")
vectorstore = FAISS.from_documents(split_documents, embeddings)

# LLM (deepseek v1)
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="deepseek/deepseek-chat",
    temperature=0.1,
    max_tokens=9000
)

# Setup del retrieval
print("Setup retrieval completato. Inizio QA...")
qa = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())

# Input
with open("problemstatement.txt", "r", encoding="utf-8") as f:
    problem_statement = f.read().strip()

# Categorie (importanti per il prompt e analisi)
all_categories = sorted({meta["category"] for meta in metadata_map.values()})

# Processazione json all_categories
all_categories_json = json.dumps(all_categories, ensure_ascii=False)


import json

all_categories_json = json.dumps(all_categories, ensure_ascii=False)

# Primo prompt di generazione
prompt = f"""
Ruolo: Generatore di requisiti strutturati JSON (prima generazione).

Input:
- problem_statement: <<<{problem_statement}>>>
- all_categories: {all_categories_json}

Obiettivi:
1) Selezionare le sole categorie pertinenti (minimo 10) tra all_categories rispetto al Problem Statement (categorie_filtrate).
2) Per ciascuna voce OWASP Top 10: 2021, generare 3 requisiti rilevanti al Problem Statement che siano specifici e non generici, ognuno con una categoria ∈ categorie_filtrate che il requisito di quel Top 10 di riferimento copre.
3) Restituire esclusivamente JSON conforme allo schema; nessun testo extra.

Vincoli:
- NON SONO AMMISSIBILI SINONIMI O VARIANTI DELLE CATEGORIE O DEI CODICI OWASP. DEVE ESSERE TUTTO LETTERALE, COSI' COME DEFINITO.
- categoria ∈ all_categories e anche ∈ categorie_filtrate.
- owasp_key ∈ {{"A01:2021","A02:2021","A03:2021","A04:2021","A05:2021","A06:2021","A07:2021","A08:2021","A09:2021","A10:2021"}}.
- testo nella lingua del Problem Statement.

Schema JSON (esempio di struttura, non generare questo esempio letterale):
{{
  "categorie_filtrate": ["string"],
  "owasp_map": {{
    "A01:2021": [
      {{"requisito":"string","categoria":"string"}}
    ],
    "A02:2021": [],
    "A03:2021": [],
    "A04:2021": [],
    "A05:2021": [],
    "A06:2021": [],
    "A07:2021": [],
    "A08:2021": [],
    "A09:2021": [],
    "A10:2021": []
  }}
}}

Output: Restituisci solo JSON valido che rispetta lo schema, senza testo aggiuntivo.
"""

# Risposta
print("Invocazione del modello...")
response = qa.run(prompt)

# Stampa
print("\nRisposta Generata:\n")
print(response)


# ---------- PARSING E VALIDAZIONE GEN1 ----------
data1 = load_loose_json(response)
assert "categorie_filtrate" in data1 and "owasp_map" in data1, "JSON gen1 privo di chiavi richieste"

categorie_filtrate = set(data1["categorie_filtrate"])
assert categorie_filtrate.issubset(set(all_categories)), "categorie_filtrate contiene valori non canonici"

# Normalizzazione gen1
norm1 = []  # record normalizzati: {categoria, requisito, owasp_top10, origine}
for owasp_key, entries in data1["owasp_map"].items():
    # Consenti che alcune chiavi possano non essere presenti; se non ci sono, .items() gestisce quelle presenti
    assert owasp_key in OWASP_KEYS, f"Chiave OWASP non valida in gen1: {owasp_key}"
    if not isinstance(entries, list):
        raise ValueError(f"owasp_map[{owasp_key}] deve essere una lista")
    for e in entries:
        # Validazioni campo per campo
        req = (e.get("requisito") or "").strip()
        cat_raw = (e.get("categoria") or "").strip()
        cat = CANON_MAP.get(cat_raw, cat_raw)
        assert req, "Requisito vuoto in gen1"
        assert cat in all_categories, f"Categoria fuori dominio in gen1: {cat_raw}"
        assert cat in categorie_filtrate, f"Categoria non filtrata in gen1: {cat}"
        # Normalizzazione record
        norm1.append({
            "categoria": cat,
            "requisito": req,
            "owasp_top10": owasp_key,
            "origine": "gen1",
        })

# Conteggi gen1 per categoria
conteggi_gen1 = Counter(r["categoria"] for r in norm1)

# Categorie non coperte (tra quelle filtrate)
categorie_non_coperte = sorted(c for c in categorie_filtrate if conteggi_gen1[c] < SOGLIA_MIN_CAT)

# Serializzazione in json di categorie_non_coperte
categorie_non_coperte_json = json.dumps(categorie_non_coperte, ensure_ascii=False)

# Stampa conteggi gen1
print("\n[GEN1] Conteggio requisiti per categoria:")
for cat in sorted(categorie_filtrate):
    print(f"- {cat}: {conteggi_gen1[cat]}")

# ----------------------------------


# Chiedere al modello di aggiungere questi altri requisiti
extra_prompt = f"""
Ruolo: Generatore di requisiti strutturati JSON (seconda generazione, per categoria).

Input:
- problem_statement: <<<{problem_statement}>>>
- categorie_non_coperte: {categorie_non_coperte_json}

Obiettivi:
1) Per ciascuna categoria in categorie_non_coperte, generare 3 requisiti di sicurezza, specifici e non generici, pertinenti al Problem Statement.
2) Ogni requisito deve avere esattamente una voce OWASP Top 10: 2021 di riferimento che copre maggiormente il rischio.
3) Restituire esclusivamente JSON conforme allo schema; nessun testo extra.

Vincoli:
- I NOMI DELLE CATEGORIE DEVONO ESSERE UGUALI ALLE CATEGORIE_NON_COPERTE, NESSUNA SIMILITUDINE. COSI' COME PER GLI OWASP. BISOGNA DEFINIRE COME RICHIESTO.
- La chiave di ogni sezione in "per_categoria" deve essere una ed una sola categoria presente in categorie_non_coperte.
- La "categoria" di ogni requisito deve coincidere esattamente con la chiave di sezione in cui è inserito ed essere un valore presente in all_categories.
- owasp_top10 ∈ {{"A01:2021","A02:2021","A03:2021","A04:2021","A05:2021","A06:2021","A07:2021","A08:2021","A09:2021","A10:2021"}}.
- "requisito" deve essere non vuoto e nella lingua del Problem Statement.
- Non inserire categorie non presenti in categorie_non_coperte, non usare sinonimi o varianti.
- Non usare varianti o termini simili agli owasp definiti, massima precisione necessaria.

Schema JSON (esempio di struttura, non generare questo esempio letterale):
{{
  "fase": "seconda",
  "categorie_non_coperte": ["string"],
  "per_categoria": {{
    "<categoria>": [
      {{"requisito":"string","owasp_top10":"A0x:2021","categoria":"<categoria>"}}
    ]
  }}
}}

Output: Restituisci solo JSON valido che rispetta lo schema, senza testo aggiuntivo.
"""

# Risposta
print("Invocazione del modello...")
response1 = qa.run(extra_prompt)

# Stampa
print("\nRisposta Generata:\n")
print(response1)

# ---------- PARSING E VALIDAZIONE GEN2 ----------
data2 = load_loose_json(response1)
assert "categorie_non_coperte" in data2 and "per_categoria" in data2, "JSON gen2 privo di chiavi richieste"

# Echo del modello (ridondante ma utile per coerenza)
cnn = set(data2["categorie_non_coperte"])
# Coerenza: devono combaciare con la nostra lista calcolata
assert cnn == set(categorie_non_coperte), "categorie_non_coperte in gen2 non coincide con il calcolo locale"

per_categoria = data2["per_categoria"]
assert isinstance(per_categoria, dict), "per_categoria deve essere un oggetto/dizionario"

# Normalizzazione gen2
norm2 = []  # record normalizzati: {categoria, requisito, owasp_top10, origine}
for cat_key, entries in per_categoria.items():
    cat_section = (cat_key or "").strip()
    assert cat_section in all_categories, f"Categoria chiave fuori dominio in gen2: {cat_section}"
    assert cat_section in categorie_non_coperte, f"Categoria chiave non è tra le non coperte in gen2: {cat_section}"
    if not isinstance(entries, list):
        raise ValueError(f"per_categoria[{cat_section}] deve essere una lista")
    for e in entries:
        req = (e.get("requisito") or "").strip()
        owasp = (e.get("owasp_top10") or "").strip()
        cat_field_raw = (e.get("categoria") or "").strip()
        cat_field = CANON_MAP.get(cat_field_raw, cat_field_raw)
        assert req, f"Requisito vuoto in gen2 per categoria {cat_section}"
        assert owasp in OWASP_KEYS, f"OWASP non valido in gen2: {owasp}"
        # La categoria nel record deve coincidere con la chiave di sezione
        assert cat_field == cat_section, f"categoria nel record non coincide con la sezione: {cat_field_raw}->{cat_field} != {cat_section}"
        norm2.append({
            "categoria": cat_section,
            "requisito": req,
            "owasp_top10": owasp,
            "origine": "gen2",
        })

# Conteggi gen2 per categoria
conteggi_gen2 = Counter(r["categoria"] for r in norm2)

# ---------- MERGE E CONTEGGI FINALI ----------
all_norm = norm1 + norm2
conteggi_finali = Counter(r["categoria"] for r in all_norm)

print("\n[GEN2] Conteggio requisiti per categoria (solo gen2):")
for cat in sorted(categorie_non_coperte):
    print(f"- {cat}: {conteggi_gen2[cat]}")

print("\n[TOTALE] Conteggio requisiti per categoria (GEN1 + GEN2):")
for cat in sorted(categorie_filtrate):
    g1 = conteggi_gen1[cat]
    g2 = conteggi_gen2[cat]
    tot = g1 + g2
    print(f"- {cat}: totale={tot} (gen1={g1}, gen2={g2})")


print(f"\n\n[GEN1] Requisiti generati (totale) della prima generazione: {len(norm1)}")
print(f"\n[GEN2] Requisiti generati (totale) della seconda generazione: {len(norm2)}")
print(f"\n[TOTALE] Requisiti generati complessivi (GEN1+GEN2): {len(all_norm)}")

#-----------------#
# GENERAZIONE PDF #
#-----------------#


# all_norm: lista di dict normalizzati {categoria, requisito, owasp_top10, origine}
# conteggi_gen1, conteggi_gen2 già calcolati; categorie_filtrate disponibile

lines = []

# Corpo: elenco requisiti numerati "Requisito – Categoria"
for i, r in enumerate(all_norm, 1):
    # usa " – " come separatore leggibile
    lines.append(f"{i}. {r['requisito']} – {r['categoria']}")

# Sezione conteggi finale
lines.append("")  # riga vuota
lines.append(f"Totali: GEN1={len(norm1)}, GEN2={len(norm2)}, COMPLESSIVO={len(all_norm)}")
lines.append("")
lines.append("Conteggi per categoria (totale = gen1 + gen2):")
for cat in sorted(categorie_filtrate):
    g1 = conteggi_gen1[cat]
    g2 = conteggi_gen2[cat]
    tot = g1 + g2
    lines.append(f"- {cat}: totale={tot} (gen1={g1}, gen2={g2})")

# Testo unico per il PDF
testo_unico_numerato = "\n".join(lines)


# Generazione PDF
output_pdf = "requisiti_llm.pdf"
export_requisiti_pdf(
    output_path=output_pdf,
    testo_unico_numerato=testo_unico_numerato,
    titolo="Requisiti di sicurezza generati (GEN1+GEN2)"
)
print(f"PDF creato: {output_pdf}")