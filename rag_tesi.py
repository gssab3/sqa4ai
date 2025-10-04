import os
import re
import json
from statistics import mean
from langchain_community.document_loaders import TextLoader
from langchain.chat_models import ChatOpenAI
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA

from rag_utils import (
    parse_gen1, parse_gen2,
    conteggi_per_categoria,
    unisci_testi_senza_categoria,
    ricomponi_testo_numerato_solo_contenuto,
)

from pdf_utils import export_requisiti_pdf

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

# print(f"Documenti caricati con metadati embedded: {len(all_documents)}")



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
    rad = f.read().strip()

# Categorie (importanti per il prompt e analisi)
all_categories = sorted({meta["category"] for meta in metadata_map.values()})


# Prompt personalizzato
prompt = f"""
Obiettivo: 
Voglio che generi 3 requisiti funzionali/non funzionali puramente di sicurezza per ogni A0x della top10 di owasp e di ogni categoria nei metadati che conosci che siano connessi e collegabili al RAD che ti manderò.  Voglio avere abbastanza requisiti di sicurezza che siano consistenti, ricoprano tutte le parti non sicure (potenzialmente) che vedi nel contesto che tra poco ti mando.
Vincoli:
I requisiti di sicurezza devono essere in conformità con ISO 27001 Annex A, NIST 800-53, NIST 800-171, Linee guida del GDPR e privacy e SANS Top 20 Critical Security Controls
Lingua di risposta: La stessa del problem statement inviato.
Categorie nei metadati di riferimento (che dovrai aggiungere poi): {", ".join(all_categories)}
Il formato di ogni requisito deve essere:
A0x
1. requisito funzionale 1 - Categoria (senza asterischi o altro, deve essere trattino spazio categoria tra quelle che ti ho inviato)
2. requisito funzionale 2 - Categoria
3. requisito non funzionale 1 - Categoria
...
Invio
A0x+1 (o "Privacy" se sono finiti i top10 e iniziano le linee guida di privacy, così per avere un nome della categoria)
e così via.
La categoria è assegnata ad ogni requisito ma si generano 3 requisiti per ogni Top10 Owasp.
RAD:
{rad}
"""

# Risposta
print("Invocazione del modello...")
response = qa.run(prompt)

# Stampa
print("\nRisposta Generata:\n")
print(response)


# -------------------
# ORA ANALISI
# -------------------

# Parsing dei requisiti con regex (esempio: "1. Testo requisito - Categoria")
pattern = r"\d+\.\s+(.+?)\s+-\s+(.+)"
requisiti_per_categoria = {cat: [] for cat in all_categories}

for line in response.splitlines():
    match = re.match(pattern, line.strip())
    if match:
        requisito, categoria = match.groups()
        if categoria in requisiti_per_categoria:
            requisiti_per_categoria[categoria].append(requisito)


# ----------------------------------
# Conta dei requisiti per categoria
conteggi = {cat: len(reqs) for cat, reqs in requisiti_per_categoria.items()}
contatore = []
print("\nConteggio requisiti per categoria:")
for cat, count in conteggi.items():
    contatore.append(count)
    print(f"- {cat}: {count} requisiti")
print(contatore, sum(contatore))

# Identificare categorie scoperte (2 requisiti)
categorie_mancanti = [cat for cat, count in conteggi.items() if count <= 0]

if categorie_mancanti:
    print("\nCategorie con pochi o nessun requisito iniziale:", categorie_mancanti, "\n\n\n\n")

# ----------------------------------


# Chiedere al modello di aggiungere questi altri requisiti
extra_prompt = f"""
Devi generarmi minimo 3 requisiti funzionali o non funzionali DI OGNI categoria che ti manderò successivamente di sicurezza A PATTO, PERO', che sia utile o compatibile con la potenziale struttura o codifica del progetto che voglio progettare (le categorie e il RAD li inserirò più in basso). Inoltre, questi devono essere in conformità con ISO 27001 Annex A, NIST 800-53, NIST 800-171, Linee guida del GDPR e privacy e SANS Top 20 Critical Security Controls.
Esse devono essere conformi ai top10 owasp:2021.
Infatti dovrà essere il formato:
Categoria
1. Requisito funzionale/non funzionale di quella categoria - top10 owasp di riferimento (uno solo)
2. Requisito funzionale/non funzionale 2 di quella categoria - top10 owasp di riferimento (uno solo)
...

Categorie: 
{", ".join(categorie_mancanti)}


RAD:
{rad}
"""

# Risposta
print("Invocazione del modello...")
response1 = qa.run(extra_prompt)

# Stampa
print("\nRisposta Generata:\n")
print(response1)

#-----------------------#
# ANALISI E STATISTICHE #
#-----------------------#


# 1) Parsing 1^ generazione
items1, bycat1 = parse_gen1(response)

# 2) Conteggi 1^ gen e categorie mancanti (soglia consigliata: <= 0)
conteggi1 = conteggi_per_categoria(bycat1)
categorie_mancanti = [cat for cat, count in conteggi1.items() if count <= 0]

# 3) Parsing 2^ generazione passando le categorie valide (le mancanti)
#    (così gli header "### **Categoria**" e le righe numerate 1./2./3. vengono riconosciuti)
items2, bycat2 = parse_gen2(response1, categorie_mancanti)

# 4) Stampe di controllo
print("[CHECK] Requisiti estratti - 1^ generazione:", len(items1))
print("[CHECK] Requisiti estratti - 2^ generazione:", len(items2))

conteggi2 = conteggi_per_categoria(bycat2)

# Preparazione dell’insieme completo di categorie per la somma
tutte_le_categorie = sorted(set(list(conteggi1.keys()) + list(conteggi2.keys())))

# Conteggi 1^ gen sugli stessi nomi
print("\n[CHECK] Conteggi per categoria - 1^ gen (tutte):")
for c in tutte_le_categorie:
    print(f" - {c}: {conteggi1.get(c, 0)}")

# Somma 1^+2^ sugli stessi nomi
print("\n[CHECK] Conteggi totali per categoria (somma 1^+2^):")
for c in tutte_le_categorie:
    print(f" - {c}: {conteggi1.get(c, 0) + conteggi2.get(c, 0)}")

# 5) Output unico di soli testi (1^ poi 2^)
lista_finale_testi = unisci_testi_senza_categoria(items1, items2)
testo_unico_numerato = ricomponi_testo_numerato_solo_contenuto(lista_finale_testi)
print("\n[CHECK] Prime 5 righe del testo unico (solo contenuto):\n", "\n".join(testo_unico_numerato.splitlines()))

#-----------------#
# GENERAZIONE PDF #
#-----------------#


output_pdf = "requisiti_llm.pdf"
export_requisiti_pdf(output_pdf, testo_unico_numerato)
print(f"PDF creato: {output_pdf}")