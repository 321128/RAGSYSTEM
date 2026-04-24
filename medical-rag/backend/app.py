from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from threading import Lock, Thread
import re
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from httpx import ReadTimeout

from .config import SETTINGS
from .ingest import ingest_to_dict
from .rag_pipeline import (
    build_qa_chain,
    get_vectorstore,
    debug_retrieve,
    debug_retrieve_with_threshold,
    debug_mmr_retrieve,
    generate_fallback_answer_from_docs,
)


app = FastAPI(title="Medical RAG API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5201",
        "http://127.0.0.1:5201",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

runtime_settings = {
    "llm_model": SETTINGS.llm_model,
    "llm_temperature": SETTINGS.llm_temperature,
    "ollama_num_ctx": SETTINGS.ollama_num_ctx,
    "ollama_num_predict": SETTINGS.ollama_num_predict,
    "retriever_top_k": SETTINGS.retriever_top_k,
    "ingest_chunk_size": SETTINGS.ingest_chunk_size,
    "ingest_chunk_overlap": SETTINGS.ingest_chunk_overlap,
}

qa_chain = build_qa_chain(
    retriever_top_k=runtime_settings["retriever_top_k"],
    llm_model=runtime_settings["llm_model"],
    llm_temperature=runtime_settings["llm_temperature"],
    ollama_num_ctx=runtime_settings["ollama_num_ctx"],
    ollama_num_predict=runtime_settings["ollama_num_predict"],
)
ask_executor = ThreadPoolExecutor(max_workers=4)
documents_dir = (Path(__file__).resolve().parent / SETTINGS.documents_dir).resolve()
documents_dir.mkdir(parents=True, exist_ok=True)

ingest_lock = Lock()
ingest_state = {
    "status": "idle",
    "job_id": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "result": None,
    "progress": None,
}


def _looks_incomplete_answer(question: str, answer: str) -> bool:
    if not isinstance(answer, str):
        return True

    cleaned = answer.strip()
    if cleaned == "":
        return True

    # Common leakage from instruction-heavy prompts.
    leaked_labels = ("**STRUCTURED**", "FACT/SHORT", "DESCRIPTIVE", "Mode")
    if any(token in cleaned for token in leaked_labels):
        return True

    # For longer descriptive questions, very short answers are often truncated.
    if len(question.split()) >= 7 and len(cleaned) < 260:
        return True

    # Answers ending abruptly often indicate token cut-off.
    if cleaned[-1] not in {".", "!", "?", ")"}:
        return True

    return False


def _extractive_rescue_answer(question: str, source_documents: list) -> str:
    """Build a best-effort answer from retrieved chunks when LLM is overly strict."""
    if not source_documents:
        return "The document does not contain this information."

    tokens = [t for t in re.findall(r"[a-zA-Z0-9]+", question.lower()) if len(t) > 3]
    selected: list[str] = []

    for doc in source_documents[:6]:
        text = doc.page_content.strip()
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            s = sentence.strip()
            if len(s) < 40:
                continue
            if any(token in s.lower() for token in tokens[:8]):
                selected.append(s)
            if len(selected) >= 4:
                break
        if len(selected) >= 4:
            break

    if not selected:
        for doc in source_documents[:3]:
            compact = " ".join(doc.page_content.split())
            if compact:
                selected.append(compact[:260].rstrip())
            if len(selected) >= 2:
                break

    if not selected:
        return "The document does not contain this information."

    return " ".join(selected)


class Query(BaseModel):
    question: str


class IngestRequest(BaseModel):
    chunk_size: int = runtime_settings["ingest_chunk_size"]
    chunk_overlap: int = runtime_settings["ingest_chunk_overlap"]
    replace_collection: bool = False


class SettingsUpdateRequest(BaseModel):
    llm_model: str | None = None
    llm_temperature: float | None = None
    ollama_num_ctx: int | None = None
    ollama_num_predict: int | None = None
    retriever_top_k: int | None = None
    ingest_chunk_size: int | None = None
    ingest_chunk_overlap: int | None = None


class ClearDataRequest(BaseModel):
    delete_files: bool = True
    delete_vectorstore: bool = True


@app.get("/settings")
def get_settings() -> dict:
    return {
        "llm_provider": SETTINGS.llm_provider,
        "llm_model": runtime_settings["llm_model"],
        "llm_temperature": runtime_settings["llm_temperature"],
        "ollama_num_ctx": runtime_settings["ollama_num_ctx"],
        "ollama_num_predict": runtime_settings["ollama_num_predict"],
        "embedding_provider": SETTINGS.embedding_provider,
        "embedding_model": SETTINGS.embedding_model,
        "retriever_top_k": runtime_settings["retriever_top_k"],
        "ingest_chunk_size": runtime_settings["ingest_chunk_size"],
        "ingest_chunk_overlap": runtime_settings["ingest_chunk_overlap"],
        "database_url": SETTINGS.database_url,
        "collection_name": SETTINGS.collection_name,
        "documents_dir": str(documents_dir),
    }


@app.put("/settings")
def update_settings(request: SettingsUpdateRequest) -> dict:
    global qa_chain

    updates = request.model_dump(exclude_none=True)
    if not updates:
        return {"status": "unchanged", "settings": get_settings()}

    if "retriever_top_k" in updates and updates["retriever_top_k"] <= 0:
        raise HTTPException(status_code=400, detail="retriever_top_k must be > 0")

    if "ingest_chunk_size" in updates and updates["ingest_chunk_size"] <= 0:
        raise HTTPException(status_code=400, detail="ingest_chunk_size must be > 0")

    if "ingest_chunk_overlap" in updates and updates["ingest_chunk_overlap"] < 0:
        raise HTTPException(status_code=400, detail="ingest_chunk_overlap must be >= 0")

    next_chunk_size = updates.get("ingest_chunk_size", runtime_settings["ingest_chunk_size"])
    next_chunk_overlap = updates.get("ingest_chunk_overlap", runtime_settings["ingest_chunk_overlap"])
    if next_chunk_overlap >= next_chunk_size:
        raise HTTPException(status_code=400, detail="ingest_chunk_overlap must be less than ingest_chunk_size")

    if "ollama_num_ctx" in updates and updates["ollama_num_ctx"] <= 0:
        raise HTTPException(status_code=400, detail="ollama_num_ctx must be > 0")

    if "ollama_num_predict" in updates and updates["ollama_num_predict"] <= 0:
        raise HTTPException(status_code=400, detail="ollama_num_predict must be > 0")

    runtime_settings.update(updates)

    qa_chain = build_qa_chain(
        retriever_top_k=runtime_settings["retriever_top_k"],
        llm_model=runtime_settings["llm_model"],
        llm_temperature=runtime_settings["llm_temperature"],
        ollama_num_ctx=runtime_settings["ollama_num_ctx"],
        ollama_num_predict=runtime_settings["ollama_num_predict"],
    )

    return {"status": "updated", "settings": get_settings()}


@app.post("/data/clear")
def clear_data(request: ClearDataRequest) -> dict:
    if ingest_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Cannot clear data while ingestion is running")

    deleted_files: list[str] = []
    deleted_vectorstore = False

    if request.delete_files:
        for pdf_file in documents_dir.glob("*.pdf"):
            pdf_file.unlink(missing_ok=True)
            deleted_files.append(pdf_file.name)

    if request.delete_vectorstore:
        try:
            vectorstore = get_vectorstore()
            vectorstore.delete_collection()
            deleted_vectorstore = True
        except Exception:
            deleted_vectorstore = False

    ingest_state.update(
        {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "result": None,
            "progress": None,
        }
    )

    return {
        "status": "cleared",
        "deleted_files": deleted_files,
        "deleted_vectorstore": deleted_vectorstore,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/documents")
def list_documents() -> dict:
    files = sorted([f.name for f in documents_dir.glob("*.pdf")])
    return {"count": len(files), "documents": files}


@app.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)) -> dict:
    saved: list[str] = []

    for file in files:
        if not file.filename:
            continue

        source_name = Path(file.filename).name
        if not source_name.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Only PDF files are supported: {source_name}")

        target_path = documents_dir / source_name
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = documents_dir / f"{stem}_{int(datetime.now(tz=timezone.utc).timestamp())}{suffix}"

        payload = await file.read()
        target_path.write_bytes(payload)
        saved.append(target_path.name)

    return {"uploaded": saved, "count": len(saved)}


def _run_ingest_job(*, chunk_size: int, chunk_overlap: int, replace_collection: bool) -> None:
    with ingest_lock:
        ingest_state["status"] = "running"
        ingest_state["started_at"] = datetime.now(tz=timezone.utc).isoformat()
        ingest_state["finished_at"] = None
        ingest_state["error"] = None
        ingest_state["result"] = None
        ingest_state["progress"] = {
            "total_files": 0,
            "completed_files": 0,
            "successful_files": 0,
            "failed_files_count": 0,
            "current_file": None,
            "current_file_index": 0,
            "current_file_progress": 0,
            "chunks_indexed": 0,
            "files": [],
        }

        try:
            result = ingest_to_dict(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                replace_collection=replace_collection,
                progress_callback=lambda progress: ingest_state.__setitem__("progress", progress),
            )
            ingest_state["status"] = "completed"
            ingest_state["result"] = result
        except Exception as exc:
            ingest_state["status"] = "failed"
            ingest_state["error"] = str(exc)
        finally:
            ingest_state["finished_at"] = datetime.now(tz=timezone.utc).isoformat()


@app.post("/ingest/start")
def start_ingestion(request: IngestRequest) -> dict:
    if ingest_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Ingestion is already running")

    if request.chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size must be > 0")

    if request.chunk_overlap < 0:
        raise HTTPException(status_code=400, detail="chunk_overlap must be >= 0")

    if request.chunk_overlap >= request.chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap must be less than chunk_size")

    runtime_settings["ingest_chunk_size"] = request.chunk_size
    runtime_settings["ingest_chunk_overlap"] = request.chunk_overlap

    job_id = str(uuid.uuid4())
    ingest_state["job_id"] = job_id

    thread = Thread(
        target=_run_ingest_job,
        kwargs={
            "chunk_size": request.chunk_size,
            "chunk_overlap": request.chunk_overlap,
            "replace_collection": request.replace_collection,
        },
        daemon=True,
    )
    thread.start()

    return {"status": "started", "job_id": job_id}


@app.get("/ingest/status")
def get_ingest_status() -> dict:
    return ingest_state


@app.post("/ask")
def ask(query: Query) -> dict:
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        future = ask_executor.submit(qa_chain.invoke, {"query": query.question})
        response = future.result(timeout=SETTINGS.ask_timeout_seconds)
    except ReadTimeout as exc:
        raise HTTPException(status_code=504, detail="The answer request timed out. Try a shorter question or increase the timeout.") from exc
    except FuturesTimeoutError as exc:
        raise HTTPException(status_code=504, detail="The answer request timed out. Try a shorter question or increase the timeout.") from exc
    except Exception as exc:
        error_name = exc.__class__.__name__
        if error_name in {"ReadTimeout", "TimeoutException", "TimeoutError"} or "timed out" in str(exc).lower():
            raise HTTPException(status_code=504, detail="The answer request timed out. Try a shorter question or increase the timeout.") from exc
        raise

    answer = response.get("result", "")
    source_documents = response.get("source_documents", [])

    # Fallback pass: if retrieval found docs but first pass was too conservative,
    # answer directly from retrieved chunks using a simpler prompt.
    if (
        isinstance(answer, str)
        and answer.strip() == "The document does not contain this information."
        and source_documents
    ):
        try:
            answer = generate_fallback_answer_from_docs(
                query.question,
                source_documents,
                llm_model=runtime_settings["llm_model"],
                llm_temperature=runtime_settings["llm_temperature"],
                ollama_num_ctx=max(runtime_settings["ollama_num_ctx"], 8192),
                ollama_num_predict=max(runtime_settings["ollama_num_predict"], 512),
            )
        except Exception:
            pass

    # Second pass for incomplete/truncated answers.
    if source_documents and _looks_incomplete_answer(query.question, answer):
        try:
            answer = generate_fallback_answer_from_docs(
                query.question,
                source_documents,
                llm_model=runtime_settings["llm_model"],
                llm_temperature=runtime_settings["llm_temperature"],
                ollama_num_ctx=max(runtime_settings["ollama_num_ctx"], 8192),
                ollama_num_predict=max(runtime_settings["ollama_num_predict"], 640),
            )
        except Exception:
            pass

    # Final rescue: when sources exist, avoid false no-information responses.
    if (
        source_documents
        and isinstance(answer, str)
        and answer.strip() == "The document does not contain this information."
    ):
        answer = _extractive_rescue_answer(query.question, source_documents)

    return {
        "answer": answer,
        "sources": [
            {
                "page": d.metadata.get("page"),
                "source": d.metadata.get("source"),
            }
            for d in source_documents
        ],
    }


@app.post("/debug/retrieve")
def debug_retrieve_endpoint(query: Query) -> dict:
    """
    Debug endpoint: Shows all retrieved chunks with similarity scores.
    Use this to inspect what documents are being retrieved for your query.
    """
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")
    
    results = debug_retrieve(query.question, include_scores=True)
    return {
        "query": query.question,
        "retrieved_count": len(results),
        "documents": results,
    }


@app.post("/debug/retrieve-threshold")
def debug_retrieve_threshold_endpoint(query: Query, threshold: float = 0.5) -> dict:
    """
    Debug endpoint: Returns only chunks above a similarity threshold.
    Helps identify minimum quality thresholds for relevant documents.
    
    threshold: Similarity score (0-1, lower is more permissive)
    """
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")
    
    if not (0 <= threshold <= 1):
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")
    
    results = debug_retrieve_with_threshold(query.question, similarity_threshold=threshold)
    return {
        "query": query.question,
        "threshold": threshold,
        "retrieved_count": len(results),
        "documents": results,
    }


@app.post("/debug/retrieve-mmr")
def debug_retrieve_mmr_endpoint(query: Query, lambda_mult: float = 0.5) -> dict:
    """
    Debug endpoint: Uses Maximal Marginal Relevance (MMR) for diverse results.
    MMR reduces redundancy between chunks while maintaining relevance.
    
    lambda_mult: 
      - 1.0 = pure relevance (like similarity search)
      - 0.5 = balance between relevance and diversity
      - 0.0 = pure diversity
    """
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")
    
    if not (0 <= lambda_mult <= 1):
        raise HTTPException(status_code=400, detail="lambda_mult must be between 0 and 1")
    
    results = debug_mmr_retrieve(query.question, lambda_mult=lambda_mult)
    return {
        "query": query.question,
        "lambda_mult": lambda_mult,
        "retrieved_count": len(results),
        "documents": results,
    }
