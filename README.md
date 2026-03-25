# SAR Narrative Generator

AI-assisted Suspicious Activity Report (SAR) drafting system with:

- A deterministic AML rule engine (YAML-driven)
- Retrieval-Augmented Generation (RAG) over compliance knowledge
- FastAPI backend with JWT authentication
- PostgreSQL persistence for cases and audit trail
- Plain HTML/CSS/JS analyst interface
- PDF export for finalized case reports

## Current Status

This repository is production-style and end-to-end runnable locally.

- Rule engine, RAG retrieval, narrative generation, and validation are implemented.
- Analyst review, replay, and audit logging are implemented.
- PDF export endpoint is implemented.
- A pytest suite exists for critical API flows.

## End-to-End Flow

For each incoming alert (`POST /cases`):

1. Authenticate request via JWT bearer token.
2. Evaluate AML rules from `rules.yaml` and compute risk score + level.
3. Mask sensitive fields before retrieval.
4. Retrieve supporting context from ChromaDB.
5. Generate SAR narrative with local Ollama model.
6. Validate narrative quality and compliance checks.
7. Score sentence-level explainability against retrieved evidence.
8. Persist case state and audit events in PostgreSQL.
9. Support analyst approve/reject and narrative edits.
10. Support replay and PDF export for archival.

## Repository Layout

```text
barclays/
|-- README.md
|-- requirements.txt
|-- rules.yaml
|-- .env.example
|-- backend/
|   |-- app.py
|   |-- database.py
|   `-- schemas.py
|-- data/
|   |-- alert_case.json
|   |-- aml_rules.yaml
|   |-- aml_typologies.txt
|   |-- example_sar_narratives.txt
|   |-- regulatory_writing_guidelines.txt
|   `-- sar_narrative_templates.txt
|-- frontend/
|   |-- index.html
|   |-- dashboard.html
|   |-- review.html
|   |-- new_case.html
|   |-- audit.html
|   |-- api.js
|   `-- style.css
|-- rag_pipeline/
|   |-- pipeline_service.py
|   |-- rule_engine.py
|   |-- sar_rag_pipeline.py
|   |-- ingestion_pipeline.py
|   `-- vector_db/
|-- scripts/
|   `-- ensure_local_postgres.py
|-- tests/
|   `-- test_backend.py
`-- vector_db/
```

## API Summary

Base URL: `http://localhost:8000`

Authentication:

- `POST /login` returns a bearer token.
- All `/cases` routes require `Authorization: Bearer <token>`.

Public endpoints:

- `GET /health`
- `POST /login`

Protected endpoints:

- `GET /cases`
- `POST /cases`
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/audit`
- `POST /cases/{case_id}/review`
- `POST /cases/{case_id}/replay`
- `GET /cases/{case_id}/export/pdf`

## Prerequisites

- Python 3.10+
- PostgreSQL running locally
- Ollama installed locally
- (Optional) Conda environment named `rag`

## Local Setup

### 1) Install dependencies

```bash
conda activate rag
pip install -r requirements.txt
```

If you do not use Conda:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Create environment file

Copy `.env.example` to `.env` and update values for your machine:

```bash
copy .env.example .env
```

Default template:

```env
DATABASE_URL=postgresql://postgres:root@localhost:5432/sar_audit
POSTGRES_ADMIN_DB=postgres
FASTAPI_URL=http://localhost:8000
OLLAMA_MODEL=mistral:7b
CHROMA_DB_PATH=rag_pipeline/vector_db
```

Important: if your local PostgreSQL password is not `root`, update `DATABASE_URL` before continuing.

### 3) Ensure PostgreSQL database exists

```bash
python scripts/ensure_local_postgres.py
```

### 4) Ensure Ollama model is available

```bash
ollama pull mistral:7b
ollama serve
```

If `mistral:7b` is heavy for your machine, you can swap `OLLAMA_MODEL` in `.env` to a smaller local model.

### 5) Build or refresh vector store

```bash
cd rag_pipeline
python ingestion_pipeline.py
cd ..
```

### 6) Start backend

```bash
uvicorn backend.app:app --reload
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

### 7) Start frontend

```bash
cd frontend
python -m http.server 8080
```

- UI: `http://localhost:8080`

## Quick Start (PowerShell)

```powershell
conda activate rag
copy .env.example .env
python scripts/ensure_local_postgres.py

Start-Process powershell -ArgumentList '-NoExit', '-Command', 'ollama serve'
ollama pull mistral:7b

Push-Location rag_pipeline
python ingestion_pipeline.py
Pop-Location

Start-Process powershell -ArgumentList '-NoExit', '-Command', 'conda activate rag; uvicorn backend.app:app --reload'
Push-Location frontend
python -m http.server 8080
Pop-Location
```

## Default Login Credentials

- `analyst` / `password123` (role: analyst)
- `manager` / `password123` (role: manager)
- `admin` / `password123` (role: admin)

## Test Suite

Run:

```bash
pytest -q tests/test_backend.py
```

Coverage includes:

- Login success and login failure
- Auth guard for protected endpoints
- Case creation and risk-level response
- Review validation and review success
- PDF export content-type

## Core Technology Stack

- Backend: FastAPI, Pydantic, Uvicorn
- Auth: python-jose (JWT), passlib
- Database: PostgreSQL, psycopg2-binary
- Retrieval: ChromaDB, sentence-transformers
- LLM: Ollama
- PDF: reportlab
- Frontend: HTML, CSS, vanilla JavaScript
- Testing: pytest, httpx, FastAPI TestClient

## Troubleshooting

- `401 Missing Bearer token`: obtain JWT from `POST /login` and pass `Authorization: Bearer <token>`.
- `Connection refused` to PostgreSQL: verify DB service is running, then re-run `python scripts/ensure_local_postgres.py`.
- Empty/weak retrieval: re-run `python rag_pipeline/ingestion_pipeline.py` to refresh embeddings.
- Ollama generation failures: ensure `ollama serve` is running and model is pulled.

## Notes

- `rules.yaml` is the primary AML rule configuration used by the pipeline.
- `data/aml_rules.yaml` is retained in the dataset folder and can be used as reference material.
- Vector database snapshots may exist under both `rag_pipeline/vector_db/` and root `vector_db/`.
- `streamlit` exists in `requirements.txt` but the shipped analyst UI is in `frontend/` (plain HTML/CSS/JS).