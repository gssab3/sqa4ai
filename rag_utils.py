import re
from collections import defaultdict
from collections.abc import Iterable
from typing import List, Tuple, Dict
import json


def strip_code_fences(text: str) -> str:
    """
    Remove code fences like ```...``` and return the inner content.
    If no triple-backtick fence is found, strip residual inline markers and return cleaned text.
    """
    lines = text.strip().splitlines()
    # If the text starts with a fence
    if lines and lines[0].strip().startswith("```"):
        content_lines = []
        opened = False
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("```") and not opened:
                opened = True
                continue
            if line_str.startswith("```"):
                break
            if opened:
                content_lines.append(line)
        if content_lines:
            return "\n".join(content_lines).strip()
    # Fallback: remove residual inline markers
    return text.replace("```json", "")


def extract_json_braces(text: str) -> str:
    """
    Extract the first substring that starts at the first '{' and ends at the last '}'.
    Useful when a model inserts surrounding text around a JSON blob.
    Raises ValueError if no suitable brace pair is found.
    """
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise ValueError("No JSON block enclosed in braces found")
    return text[s:e+1]


def load_loose_json(text: str):
    """
    Full pipeline: strip code fences, extract the JSON blob between braces and parse it with json.loads.
    Raises exceptions if extraction or parsing fails.
    """
    clean = strip_code_fences(text)
    raw = extract_json_braces(clean)
    return json.loads(raw)