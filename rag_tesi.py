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
from rag_utils import load_loose_json
from pdf_utils import export_requirement_pdf

# Constraint OWASP/Categories
OWASP_KEYS = {f"A0{i}:2021" for i in range(1,10)} | {"A10:2021"}
TRESHOLD_MIN_CAT = 2
CANON_MAP = {
    "Cryptography": "Data Protection"
}

# Load env variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Loading txt documents inside guidelines folder through TextLoader (to import all contents). Also need metadata for understanding categories and covered owasp top10 by each cheat sheet
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

# Embeddings with HuggingFace models
print("Loading docs completed")
print("Creating embeddings...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Creating FAISS for internal-search engine
print("Creating FAISS...")
vectorstore = FAISS.from_documents(split_documents, embeddings)

# LLM (deepseek v1)
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="deepseek/deepseek-chat",
    temperature=0.1,
    max_tokens=9000
)

# Setup of retrieval
print("Setup retrieval completed. Starting QA...")
qa = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())

# Input
with open("problemstatement.txt", "r", encoding="utf-8") as f:
    problem_statement = f.read().strip()

# Categories extraction
all_categories = sorted({meta["category"] for meta in metadata_map.values()})

# Processing json all_categories
all_categories_json = json.dumps(all_categories, ensure_ascii=False)

# First generative prompt
prompt = f"""
Role: Requirements Generator via JSON (first generation).

Input:
- problem_statement: <<<{problem_statement}>>>
- all_categories: {all_categories_json}

Objectives:
1) Select only relevant categories (minimum 10) from all_categories for the Problem Statement (filtered_categories).
2) For each OWASP Top 10: 2021 entry, generate three requirements relevant to the Problem Statement that are specific and not generic, each with a category ∈ filtered_categories that the requirement in that Top 10 reference covers.
3) Return only schema-compliant JSON; no extra text.

Constraints:
- NO SYNONYMS OR VARIANTS OF OWASP CATEGORIES OR CODES ARE ALLOWED. EVERYTHING MUST BE LITERAL, AS DEFINED.
- category ∈ all_categories and also ∈ filtered_categories.
- owasp_key ∈ {{"A01:2021","A02:2021","A03:2021","A04:2021","A05:2021","A06:2021","A07:2021","A08:2021","A09:2021","A10:2021"}}.
- text in the language of the Problem Statement.

JSON Schema (writing example, do NOT generate literally this example):
{{
  "filtered_categories": ["string"],
  "owasp_map": {{
    "A01:2021": [
      {{"requirement":"string","category":"string"}}
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

Output: Return only valid JSON that matches the schema, without any additional text.
"""

# Response
print("Invocation of model...")
response = qa.run(prompt)

# Printing
print("\nGenerated Response:\n")
print(response)


# ---------- PARSING AND VALIDATION GEN1 ----------
data1 = load_loose_json(response)
assert "filtered_categories" in data1 and "owasp_map" in data1, "JSON gen1 with no keys required"

filtered_categories = set(data1["filtered_categories"])
assert filtered_categories.issubset(set(all_categories)), "filtered_categories contains non-canonical values"

# Normalization gen1
norm1 = []  # normalized records: {category, requirement, owasp_top10, source}
for owasp_key, entries in data1["owasp_map"].items():
    # Allow some keys to be missing; if they are not, .items() handles the ones that are present.
    assert owasp_key in OWASP_KEYS, f"OWASP key not valid in gen1: {owasp_key}"
    if not isinstance(entries, list):
        raise ValueError(f"owasp_map[{owasp_key}] must be a list")
    for e in entries:
        # Validating each field
        req = (e.get("requirement") or "").strip()
        cat_raw = (e.get("category") or "").strip()
        cat = CANON_MAP.get(cat_raw, cat_raw)
        assert req, "Empty Requirement in gen1"
        assert cat in all_categories, f"Category out of domain in gen1: {cat_raw}"
        assert cat in filtered_categories, f"Not filtered category in gen1: {cat}"

        # Normalizating record
        norm1.append({
            "category": cat,
            "requirement": req,
            "owasp_top10": owasp_key,
            "source": "gen1",
        })

# Counting gen1 for each category
counts_gen1 = Counter(r["category"] for r in norm1)

# Not covered categories (among the filtered ones)
not_covered_categories = sorted(c for c in filtered_categories if counts_gen1[c] < TRESHOLD_MIN_CAT)

# Serialization in json of not_covered_categories
not_covered_categories_json = json.dumps(not_covered_categories, ensure_ascii=False)

# Printing counting json gen1
print("\n[GEN1] Counting requirements for each category:")
for cat in sorted(filtered_categories):
    print(f"- {cat}: {counts_gen1[cat]}")

# ----------------------------------


# Asking the model to add more requirements for not covered categories
extra_prompt = f"""
Role: Generator of structured JSON requirements (second generation, per category).
Input:
- problem_statement: <<<{problem_statement}>>>
- not_covered_categories: {not_covered_categories_json}

Objectives:
1) For each category in not_covered_categories, generate three specific, non-generic security requirements relevant to the Problem Statement.
2) Each requirement must have exactly one OWASP Top 10: 2021 entry that best covers the risk.
3) Return only schema-compliant JSON; no extra text.

Constraints:
- CATEGORY NAMES MUST BE THE SAME AS THE NOT-COVERED_CATEGORIES, NO SIMILARITY. AS WITH OWASP. MUST BE DEFINED AS REQUIRED.
- The key for each section in "per_categoria" must be one and only one category present in not_covered_categories.
- The "category" of each requirement must match exactly the key of the section in which it is inserted and be a value present in all_categories.
- owasp_top10 ∈ {{"A01:2021","A02:2021","A03:2021","A04:2021","A05:2021","A06:2021","A07:2021","A08:2021","A09:2021","A10:2021"}}.
- "requirement" must be non-empty and in the language of the Problem Statement.
- Do not insert categories not present in categories_not_covered, do not use synonyms or variants.
- Do not use variants or similar terms to the owasp terms defined; maximum precision is required.

JSON Schema (Example of structure, do NOT generate this example literally):
{{
  "phase": "second",
  "not_covered_categories": ["string"],
  "per_categoria": {{
    "<category>": [
      {{"requirement":"string","owasp_top10":"A0x:2021","category":"<category>"}}
    ]
  }}
}}

Output: Return only valid JSON that matches the schema, without any additional text.
"""

# Response
print("Invocating model...")
response1 = qa.run(extra_prompt)

# Print
print("\nGenerating Response:\n")
print(response1)

# ---------- PARSING AND VALIDATION GEN2 ----------
data2 = load_loose_json(response1)
assert "not_covered_categories" in data2 and "per_categoria" in data2, "JSON gen2 without required keys"

# Echo of model (redundant but useful for consistency)
cnn = set(data2["not_covered_categories"])
# Consistency: They must match our calculated list
assert cnn == set(not_covered_categories), "not_covered_categories in gen2 does not match the local calculation"

per_categoria = data2["per_categoria"]
assert isinstance(per_categoria, dict), "per_categoria must be an object/dictionary"

# Normalization of gen2
norm2 = []  # normalized records: {category, requirement, owasp_top10, source}
for cat_key, entries in per_categoria.items():
    cat_section = (cat_key or "").strip()
    assert cat_section in all_categories, f"Out-of-domain key category in gen2: {cat_section}"
    assert cat_section in not_covered_categories, f"Key category is not among the uncovered in gen2: {cat_section}"
    if not isinstance(entries, list):
        raise ValueError(f"per_categoria[{cat_section}] must be a list")
    for e in entries:
        req = (e.get("requirement") or "").strip()
        owasp = (e.get("owasp_top10") or "").strip()
        cat_field_raw = (e.get("category") or "").strip()
        cat_field = CANON_MAP.get(cat_field_raw, cat_field_raw)
        assert req, f"Empty requirement in gen2 for category {cat_section}"
        assert owasp in OWASP_KEYS, f"OWASP not valid in gen2: {owasp}"
        # The category in the record must match the section key
        assert cat_field == cat_section, f"category in the record does not match the section: {cat_field_raw}->{cat_field} != {cat_section}"
        norm2.append({
            "category": cat_section,
            "requirement": req,
            "owasp_top10": owasp,
            "source": "gen2",
        })

# Counting gen2 per categoria
count_gen2 = Counter(r["category"] for r in norm2)

# ---------- MERGE AND FINAL COUNTINGS ----------
all_norm = norm1 + norm2
final_counting = Counter(r["category"] for r in all_norm)

print("\n[GEN2] Counting requirements per categoria (solo gen2):")
for cat in sorted(not_covered_categories):
    print(f"- {cat}: {count_gen2[cat]}")

print("\n[TOTALE] Counting requirements per categoria (GEN1 + GEN2):")
for cat in sorted(filtered_categories):
    g1 = counts_gen1[cat]
    g2 = count_gen2[cat]
    tot = g1 + g2
    print(f"- {cat}: total={tot} (gen1={g1}, gen2={g2})")


print(f"\n\n[GEN1] Generated requirements (total) of the first generation: {len(norm1)}")
print(f"\n[GEN2] Requirements generated (total) of the second generation: {len(norm2)}")
print(f"\n[TOTAL] Total generated requirements (GEN1+GEN2): {len(all_norm)}")

#-----------------#
# GENERATING PDF #
#-----------------#


# all_norm: list of normalized dicts {category, requirement, owasp_top10, source}
# conteggi_gen1, conteggi_gen2 calculated; filtered_categories available

lines = []

# Corpus: List of numbered requirements "Requirement – Category"
for i, r in enumerate(all_norm, 1):
    # use " – " as understandable separator
    lines.append(f"{i}. {r['requirement']} – {r['category']}")

# Section final countings
lines.append("")  # empty line
lines.append(f"Total: GEN1={len(norm1)}, GEN2={len(norm2)}, Total={len(all_norm)}")
lines.append("")
lines.append("Counting per categoria (total = gen1 + gen2):")
for cat in sorted(filtered_categories):
    g1 = counts_gen1[cat]
    g2 = count_gen2[cat]
    tot = g1 + g2
    lines.append(f"- {cat}: total={tot} (gen1={g1}, gen2={g2})")

# Unique corpus for PDF
corpus = "\n".join(lines)


# Generating PDF
output_pdf = "requirements_llm.pdf"
export_requirement_pdf(
    output_path=output_pdf,
    corpus=corpus,
    title="Security Requirements Generated (GEN1+GEN2)"
)
print(f"PDF created: {output_pdf}")