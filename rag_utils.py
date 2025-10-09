import re
from collections import defaultdict
from collections.abc import Iterable
from typing import List, Tuple, Dict
import json


def strip_code_fences(text: str) -> str:
    """
    Rimuove i code fences tipo `````` o `````` e restituisce il contenuto interno.
    Se non trova fence, rimuove eventuali marcatori residui e ritorna il testo ripulito.
    """
    lines = text.strip().splitlines()
    # Se il testo inizia con un fence
    if lines and lines[0].strip().startswith("```"):
        content_lines = []
        opened = False
        for line in lines:
            ls = line.strip()
            if ls.startswith("```") and not opened:
                opened = True
                continue
            if ls.startswith("```"):
                break
            if opened:
                content_lines.append(line)
        if content_lines:
            return "\n".join(content_lines).strip()
    # Fallback: rimuovi marcatori residui inline
    return text.replace("```json", "")

def extract_json_braces(text: str) -> str:
    """
    Estrae la prima sottostringa compresa tra la prima '{' e l'ultima '}'.
    Utile quando il modello aggiunge testo prima/dopo il JSON.
    """
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise ValueError("Nessun blocco JSON con graffe trovato")
    return text[s:e+1]

def load_loose_json(text: str):
    """
    Pipeline completa: rimuove code fences, estrae il blob JSON tra graffe e fa json.loads.
    Lancia eccezione se non riesce ad estrarre o a fare il parse.
    """
    clean = strip_code_fences(text)
    raw = extract_json_braces(clean)
    return json.loads(raw)