# LLM and Runtime Configuration

This document describes the configuration used for the RAG case study in the paper.

## Overview

The RAG stack consists of:

- A **curated CSV database** of experimental ionic conductivities, matched to Materials Project entries.
- A **FAISS index** built on sentence embeddings (“cards”) derived from each database row.
- A **FastAPI service** (`app.py`) that:
  - embeds the user question,
  - retrieves the top-k cards via FAISS,
  - deterministically ranks them by numeric conductivity,
  - and calls a local LLM to generate a short, schema-aware answer.
- A **demo driver** (`demo_examples.py`) that sends predefined questions to the API and stores JSON outputs under `outputs/`.

## Models

### Embedding model

- **Name:** `sentence-transformers/all-MiniLM-L6-v2`  
- **Library:** `sentence-transformers` (SentenceTransformer class)  
- **Usage:**
  - All cards and questions are embedded with this model.
  - Embeddings are L2-normalized and indexed with FAISS using an inner-product index (`IndexFlatIP`), which is equivalent to cosine similarity on normalized vectors.

### Language model (LLM)

- **Backend:** [Ollama](https://ollama.com/) running locally.
- **Model:** `llama3.1:8b`
- **Endpoint:** `http://127.0.0.1:11435/api/generate`
- **Request payload:**

  ```json
  {
    "model": "llama3.1:8b",
    "prompt": "...",
    "stream": false,
    "options": {
      "temperature": 0.0
    }
  }
