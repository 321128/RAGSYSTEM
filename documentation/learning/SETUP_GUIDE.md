# Medical RAG Application — Setup Guide

This guide documents the recommended steps to set up and run the Medical RAG application on a Linux system.

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- (Optional) NVIDIA GPU and CUDA drivers if you plan to run GPU-backed models
- Ollama (optional if you use local Ollama models)

## 1 — Environment

Copy the example environment file and edit values as needed:

```bash
cp .env.example .env
```

Important environment knobs:
- LLM and embeddings provider variables (check `.env` for `OLLAMA_MODEL`, `OPENAI_API_KEY`, etc.)
- `DATABASE_URL` for PostgreSQL with pgvector
- `CORS_ORIGIN_REGEX` — recommended for CORS configuration (see below)

To inspect available Ollama model tags, use Ollama or query the local API:
```bash
curl -s http://localhost:11434/api/tags | python -m json.tool
```

## 2 — Python Virtualenv

Create and activate a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

## 3 — GPU / PyTorch (optional)

If you need GPU support, ensure PyTorch matches your CUDA driver. Example for CUDA 12.1 wheels:

```bash
pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify:

```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

## 4 — Database and Containers

The project uses PostgreSQL + pgvector. Start the stack using the provided script (recommended):

```bash
./script.sh
```

This brings up:
- PostgreSQL + pgvector (host port 5202)
- FastAPI backend (port 5200)
- React frontend (port 5201)

You can also use `docker compose up` from the project root if you prefer.

## 5 — CORS Configuration (recommended)

Do NOT edit `backend/app.py` to change CORS for deployments. Use the `CORS_ORIGIN_REGEX` environment variable instead (safer and deploy-friendly).

Example `.env` entry:

```
CORS_ORIGIN_REGEX="https?://(localhost|127\\.0\\.1|192\\.168\\.0\\.[0-9]+):5201"
```

This lets the backend accept frontend origins without changing code.

## 6 — Ollama / LLM Models (optional)

If using Ollama locally, pull the desired tag:

```bash
ollama pull <model-tag>
```

Set the corresponding tag in `.env` (for example `OLLAMA_MODEL=<model-tag>`). Verify tags via the Ollama API:

```bash
curl -s http://localhost:11434/api/tags | python -m json.tool
```

Note: exact model tags vary by your Ollama installation — confirm with `ollama` or the API.

## 7 — Deploy helper

There is a convenience installer `deploy_replica.sh` at the project root to replicate/install the project on another system. It:
- Clones the repo,
- Creates a venv and installs dependencies,
- Creates a minimal `.env` if missing,
- Optionally runs `script.sh` to start containers.

Run it with:

```bash
./deploy_replica.sh
```

See the script header for flags like `--no-docker`.

## 8 — Start the Application

With the venv active, start the stack:

```bash
./script.sh
```

Check endpoints:
- Frontend UI: `http://localhost:5201`
- Backend API: `http://localhost:5200`
- OpenAPI docs: `http://localhost:5200/docs`
- Health: `GET http://localhost:5200/health` should return `{"status":"ok"}`

## Troubleshooting

- Backend shows "offline" in UI:
    - Confirm backend is running at `http://localhost:5200/health`.
    - Ensure `CORS_ORIGIN_REGEX` allows the origin or set `VITE_API_BASE_URL` in frontend if using a custom base.

- 500 errors for questions:
    - Verify configured model is available (Ollama or remote provider keys).
    - Check backend logs at `.run-logs/backend.log`.

- Ingestion fails with CUDA errors:
    - Reinstall PyTorch matching your CUDA driver.

- Ports in use:
```bash
lsof -ti :5200,5201 | xargs -r kill -9
docker compose down
```

## Key Files

- `.env` — environment overrides
- `.env.example` — example values
- `backend/app.py` — FastAPI backend (reads `CORS_ORIGIN_REGEX`)
- `backend/rag_pipeline.py` — RAG pipeline and prompts
- `backend/ingest.py` — document ingestion
- `script.sh` — start script
- `docker-compose.yml` — containers for DB (if used)
- `deploy_replica.sh` — replication helper script

## Logs

- `.run-logs/backend.log`
- `.run-logs/frontend.log`

## Quick Checklist

- [ ] Create `.env` from `.env.example`
- [ ] Install Python deps in `.venv`
- [ ] Pull any required Ollama models (if using Ollama)
- [ ] Run `./script.sh` (or `./deploy_replica.sh` on new host)
- [ ] Open `http://localhost:5201` and verify backend health
