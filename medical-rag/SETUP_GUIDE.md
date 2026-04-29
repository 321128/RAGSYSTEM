# Medical RAG Application Setup Guide

This guide documents the complete setup process for running the Medical RAG application on this system (Linux with NVIDIA RTX 4000 SFF Ada GPU).

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- NVIDIA GPU with CUDA support
- Ollama installed and running

## Step 1: Environment Configuration

Create the `.env` file from the example:

```bash
cp .env.example .env
```

The `.env` file contains:
- LangChain tracing settings
- Ollama model configuration (llama3.2:1b)
- HuggingFace embeddings (BAAI/bge-small-en)
- Ingestion and retrieval parameters
- Database connection (PostgreSQL with pgvector)

## Step 2: Virtual Environment Setup

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate  # or . .venv/bin/activate
pip install --upgrade pip
```

## Step 3: Install Dependencies

Install all required Python packages:

```bash
pip install -r backend/requirements.txt
```

This installs:
- FastAPI and Uvicorn for the backend
- LangChain ecosystem for RAG pipeline
- Document processing libraries (PyPDF, Docling, etc.)
- Database connectors (psycopg2, SQLAlchemy)
- ML libraries (sentence-transformers, torch, etc.)

## Step 4: GPU Compatibility Fix

The system has CUDA 12.2, but the installed PyTorch was incompatible. Reinstall PyTorch with CUDA 12.1 support:

```bash
pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU access:
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0)}')"
```

## Step 5: Install Required Ollama Model

Pull the required language model:

```bash
ollama pull llama3.2:1b
```

Verify model availability:
```bash
curl -s http://localhost:11434/api/tags | python -m json.tool
```

## Step 6: CORS Configuration Fix

Update `backend/app.py` to allow the system's IP address in CORS settings:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5201",
        "http://127.0.0.1:5201",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.240.1.45:5201",  # Add your system IP
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Step 7: Start the Application

Use the provided startup script:

```bash
VENV_PY=$(pwd)/.venv/bin/python ./script.sh
```

This starts:
- PostgreSQL + pgvector database (port 5202)
- FastAPI backend (port 5200)
- React frontend (port 5201)

## Application URLs

- **Frontend UI**: http://192.240.1.45:5201
- **Backend API**: http://192.240.1.45:5200
- **API Documentation**: http://192.240.1.45:5200/docs

## Troubleshooting

### 500 Internal Server Error on Questions
- **Cause**: Missing Ollama model
- **Solution**: Run `ollama pull llama3.2:1b`

### Ingestion Fails with CUDA Error
- **Cause**: PyTorch CUDA version mismatch
- **Solution**: Reinstall PyTorch with correct CUDA version

### CORS Errors in Browser
- **Cause**: Frontend origin not allowed
- **Solution**: Add system IP to `allow_origins` in `backend/app.py`

### Port Already in Use
- **Solution**: Kill existing processes and restart
```bash
lsof -ti :5200,5201 | xargs -r kill -9
docker compose down
```

## Key Configuration Files

- `.env` - Environment variables
- `backend/requirements.txt` - Python dependencies
- `backend/app.py` - FastAPI application with CORS settings
- `script.sh` - Application startup script
- `docker-compose.yml` - Database container configuration

## System Information

- **OS**: Linux
- **GPU**: NVIDIA RTX 4000 SFF Ada Generation
- **CUDA**: 12.2 (Driver: 535.183.01)
- **Python**: 3.10
- **PyTorch**: 2.5.1+cu121
- **Ollama**: 0.6.7

## Usage

1. Upload PDF documents through the frontend
2. Start ingestion process
3. Ask questions about the uploaded medical documents
4. The system will retrieve relevant information and generate answers using the local LLM

## Logs

Application logs are available in:
- `.run-logs/backend.log`
- `.run-logs/frontend.log`