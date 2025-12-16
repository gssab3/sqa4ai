# SQA4AI - Enhancing Security Requirements Coverage via RAG and Automated Feedback Loops

## Introduction
This project is a specialized RAG framework designed to act as an automated Quality Assurance mechanism for Security Requirements Engineering.

## Architecture

### Knowledge Base
- **96 OWASP Cheat Sheets** manually summarized and categorized
- Each document labeled with:
  - Security category (e.g., Authentication, Input Validation)
  - OWASP Top 10:2021 references

### RAG Pipeline
1. **Document Loading**: Text files with metadata from `guidelines/`
2. **Chunking**: `RecursiveCharacterTextSplitter` (3000 chars, 100 overlap)
3. **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2`
4. **Vector Store**: FAISS for similarity search
5. **LLM**: DeepSeek v3 via OpenRouter API

### Dual-Generation Strategy
- **GEN1**: Generates 3 requirements per OWASP Top 10 category, selecting relevant security categories
- **GEN2**: Supplements under-covered categories (threshold: <2 requirements)

### Output
- Structured JSON with requirements mapped to OWASP Top 10
- PDF report (`requirements_llm.pdf`) with numbered requirements and statistics

## Setup

### Prerequisites
- Python 3.10+
- OpenRouter API key
