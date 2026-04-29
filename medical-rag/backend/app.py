from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from threading import Lock, Thread
import re
import uuid
import shutil

from fastapi import FastAPI, File, HTTPException, Query as FastAPIQuery, UploadFile
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
        "http://192.240.1.45:5201",
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

ask_executor = ThreadPoolExecutor(max_workers=4)
documents_root_dir = (Path(__file__).resolve().parent / SETTINGS.documents_dir).resolve()
documents_root_dir.mkdir(parents=True, exist_ok=True)

DEFAULT_KNOWLEDGE_BASE = "default"
active_knowledge_base = DEFAULT_KNOWLEDGE_BASE

ingest_lock = Lock()
ingest_states: dict[str, dict] = {}


def _empty_ingest_state() -> dict:
    return {
        "status": "idle",
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "result": None,
        "progress": None,
    }


def _validate_knowledge_base_name(name: str) -> str:
    normalized = name.strip()
    if normalized == "":
        raise HTTPException(status_code=400, detail="knowledge_base must not be empty")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise HTTPException(status_code=400, detail="knowledge_base contains invalid path characters")
    return normalized


def _resolve_knowledge_base_name(knowledge_base: str | None) -> str:
    if knowledge_base is None:
        return active_knowledge_base
    return _validate_knowledge_base_name(knowledge_base)


def _knowledge_base_dir(knowledge_base: str, *, create: bool = True) -> Path:
    kb_path = (documents_root_dir / knowledge_base).resolve()
    if kb_path.parent != documents_root_dir:
        raise HTTPException(status_code=400, detail="knowledge_base must be a direct folder name")
    if create:
        kb_path.mkdir(parents=True, exist_ok=True)
    return kb_path


def _knowledge_base_collection_name(knowledge_base: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9]+", "_", knowledge_base.lower()).strip("_") or "default"
    return f"{SETTINGS.collection_name}__{suffix}"


def _get_ingest_state(knowledge_base: str) -> dict:
    if knowledge_base not in ingest_states:
        ingest_states[knowledge_base] = _empty_ingest_state()
    return ingest_states[knowledge_base]


def _list_knowledge_bases() -> list[str]:
    existing = [p.name for p in documents_root_dir.iterdir() if p.is_dir()]
    if DEFAULT_KNOWLEDGE_BASE not in existing:
        _knowledge_base_dir(DEFAULT_KNOWLEDGE_BASE, create=True)
        existing.append(DEFAULT_KNOWLEDGE_BASE)
    return sorted(existing, key=lambda name: name.lower())


def _matching_knowledge_base_dirs(normalized_name: str) -> list[Path]:
    return [
        path
        for path in documents_root_dir.iterdir()
        if path.is_dir() and path.name.strip() == normalized_name
    ]


def _migrate_legacy_root_pdfs() -> None:
    default_dir = _knowledge_base_dir(DEFAULT_KNOWLEDGE_BASE, create=True)
    for legacy_pdf in documents_root_dir.glob("*.pdf"):
        target = default_dir / legacy_pdf.name
        if target.exists():
            target = default_dir / f"{legacy_pdf.stem}_{int(datetime.now(tz=timezone.utc).timestamp())}{legacy_pdf.suffix}"
        legacy_pdf.rename(target)


_knowledge_base_dir(DEFAULT_KNOWLEDGE_BASE, create=True)
_migrate_legacy_root_pdfs()


@app.on_event("shutdown")
def _shutdown_executor() -> None:
    # Release executor-owned synchronization primitives on clean app shutdown.
    ask_executor.shutdown(wait=False, cancel_futures=True)


def _looks_incomplete_answer(question: str, answer: str) -> bool:
    """
    Detect if an answer appears to be incomplete or truncated.
    
    Checks for:
    - Empty or whitespace-only answers
    - Leaked internal labels
    - Suspiciously short answers for complex questions
    - Answers ending abruptly without proper punctuation
    - Common truncation patterns
    
    Args:
        question: The original question asked
        answer: The generated answer
        
    Returns:
        True if answer appears incomplete, False otherwise
    """
    if not isinstance(answer, str):
        return True

    cleaned = answer.strip()
    if cleaned == "":
        return True

    # Check for common leakage from instruction-heavy prompts
    leaked_labels = ("**STRUCTURED**", "FACT/SHORT", "DESCRIPTIVE", "Mode", "**Classification**")
    if any(token in cleaned for token in leaked_labels):
        return True

    # For longer, more complex questions, very short answers are often truncated
    # Descriptive questions (7+ words) should typically produce longer answers
    question_word_count = len(question.split())
    
    # Strict threshold for complex descriptive questions
    if question_word_count >= 7:
        # For questions like "What are the stages of..." or "How do... manage...", expect detailed answers
        if "what are" in question.lower() or "how" in question.lower() or "explain" in question.lower():
            if len(cleaned) < 300:  # Very comprehensive answers should be longer
                return True
        # For other descriptive questions, 260 chars minimum
        elif len(cleaned) < 260:
            return True

    # Single word or very short factual answers are usually complete
    elif question_word_count <= 3:
        # These should be short, so don't flag them
        pass
    else:
        # Medium-length questions (4-6 words) should have reasonable answers
        if len(cleaned) < 150:
            return True

    # Answers ending abruptly without proper punctuation often indicate token cut-off
    # Allow for cases where answer ends with a quote, closing bracket, etc.
    if cleaned[-1] not in {'.', '!', '?', ')', ']', '}', '"', "'", '*', '-', '—'}:
        # But allow single words or very short answers
        if len(cleaned) > 50:
            return True

    # Check for incomplete sentences
    # If answer has many commas but no periods, it might be incomplete
    if cleaned.count(',') > 3 and cleaned.count('.') == 0:
        if len(cleaned) > 200:
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
    knowledge_base: str | None = None


class IngestRequest(BaseModel):
    chunk_size: int = runtime_settings["ingest_chunk_size"]
    chunk_overlap: int = runtime_settings["ingest_chunk_overlap"]
    replace_collection: bool = False
    knowledge_base: str | None = None


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
    knowledge_base: str | None = None


class KnowledgeBaseRequest(BaseModel):
    knowledge_base: str


@app.get("/settings")
def get_settings() -> dict:
    active_dir = _knowledge_base_dir(active_knowledge_base, create=True)
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
        "collection_name": _knowledge_base_collection_name(active_knowledge_base),
        "base_collection_name": SETTINGS.collection_name,
        "documents_dir": str(active_dir),
        "documents_root_dir": str(documents_root_dir),
        "active_knowledge_base": active_knowledge_base,
    }


@app.get("/knowledge-bases")
def list_knowledge_bases() -> dict:
    return {
        "active_knowledge_base": active_knowledge_base,
        "knowledge_bases": _list_knowledge_bases(),
    }


@app.post("/knowledge-bases")
def create_knowledge_base(request: KnowledgeBaseRequest) -> dict:
    knowledge_base = _validate_knowledge_base_name(request.knowledge_base)
    _knowledge_base_dir(knowledge_base, create=True)
    _get_ingest_state(knowledge_base)
    return {
        "status": "created",
        "knowledge_base": knowledge_base,
        "documents_dir": str(_knowledge_base_dir(knowledge_base, create=True)),
        "collection_name": _knowledge_base_collection_name(knowledge_base),
    }


@app.put("/knowledge-bases/active")
def set_active_knowledge_base(request: KnowledgeBaseRequest) -> dict:
    global active_knowledge_base

    knowledge_base = _validate_knowledge_base_name(request.knowledge_base)
    _knowledge_base_dir(knowledge_base, create=True)
    active_knowledge_base = knowledge_base
    _get_ingest_state(knowledge_base)
    return {
        "status": "active_updated",
        "active_knowledge_base": active_knowledge_base,
        "documents_dir": str(_knowledge_base_dir(active_knowledge_base, create=True)),
        "collection_name": _knowledge_base_collection_name(active_knowledge_base),
    }


@app.delete("/knowledge-bases/{knowledge_base_name}")
def delete_knowledge_base(knowledge_base_name: str) -> dict:
    global active_knowledge_base

    knowledge_base = _validate_knowledge_base_name(knowledge_base_name)

    # Prevent deletion of the default knowledge base
    if knowledge_base == DEFAULT_KNOWLEDGE_BASE:
        raise HTTPException(status_code=400, detail="Cannot delete the default knowledge base")

    matching_state_keys = [key for key in ingest_states if key.strip() == knowledge_base]
    if any(ingest_states[key]["status"] == "running" for key in matching_state_keys):
        raise HTTPException(status_code=409, detail="Cannot delete knowledge base while ingestion is running")

    # Delete all matching knowledge base folders (handles legacy trailing spaces in folder names)
    matching_dirs = _matching_knowledge_base_dirs(knowledge_base)
    deleted_files: list[str] = []
    deleted_directories: list[str] = []
    for kb_dir in matching_dirs:
        for pdf_file in kb_dir.glob("*.pdf"):
            deleted_files.append(pdf_file.name)
        shutil.rmtree(kb_dir, ignore_errors=True)
        deleted_directories.append(kb_dir.name)

    # Delete the vector collection from the database
    target_collection_name = _knowledge_base_collection_name(knowledge_base)
    deleted_vectorstore = False
    try:
        vectorstore = get_vectorstore(collection_name=target_collection_name)
        vectorstore.delete_collection()
        deleted_vectorstore = True
    except Exception:
        deleted_vectorstore = False

    # Clean up ingest states, including legacy keys with trailing spaces
    for kb_key in list(ingest_states.keys()):
        if kb_key.strip() == knowledge_base:
            del ingest_states[kb_key]

    # Switch to default KB if the deleted KB was active
    if active_knowledge_base.strip() == knowledge_base:
        active_knowledge_base = DEFAULT_KNOWLEDGE_BASE

    return {
        "status": "deleted",
        "knowledge_base": knowledge_base,
        "deleted_directories": deleted_directories,
        "deleted_files": deleted_files,
        "deleted_vectorstore": deleted_vectorstore,
        "active_knowledge_base": active_knowledge_base,
    }


@app.put("/settings")
def update_settings(request: SettingsUpdateRequest) -> dict:
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

    return {"status": "updated", "settings": get_settings()}


@app.post("/data/clear")
def clear_data(request: ClearDataRequest) -> dict:
    knowledge_base = _resolve_knowledge_base_name(request.knowledge_base)
    state = _get_ingest_state(knowledge_base)
    if state["status"] == "running":
        raise HTTPException(status_code=409, detail="Cannot clear data while ingestion is running for this knowledge base")

    target_documents_dir = _knowledge_base_dir(knowledge_base, create=True)
    target_collection_name = _knowledge_base_collection_name(knowledge_base)

    deleted_files: list[str] = []
    deleted_vectorstore = False

    if request.delete_files:
        for pdf_file in target_documents_dir.glob("*.pdf"):
            pdf_file.unlink(missing_ok=True)
            deleted_files.append(pdf_file.name)

    if request.delete_vectorstore:
        try:
            vectorstore = get_vectorstore(collection_name=target_collection_name)
            vectorstore.delete_collection()
            deleted_vectorstore = True
        except Exception:
            deleted_vectorstore = False

    state.update(
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
        "knowledge_base": knowledge_base,
        "deleted_files": deleted_files,
        "deleted_vectorstore": deleted_vectorstore,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/documents")
def list_documents(knowledge_base: str | None = FastAPIQuery(default=None)) -> dict:
    resolved_knowledge_base = _resolve_knowledge_base_name(knowledge_base)
    target_documents_dir = _knowledge_base_dir(resolved_knowledge_base, create=True)
    files = sorted([f.name for f in target_documents_dir.glob("*.pdf")])
    return {
        "knowledge_base": resolved_knowledge_base,
        "count": len(files),
        "documents": files,
    }


@app.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    knowledge_base: str | None = FastAPIQuery(default=None),
) -> dict:
    resolved_knowledge_base = _resolve_knowledge_base_name(knowledge_base)
    target_documents_dir = _knowledge_base_dir(resolved_knowledge_base, create=True)
    saved: list[str] = []

    for file in files:
        if not file.filename:
            continue

        source_name = Path(file.filename).name
        if not source_name.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Only PDF files are supported: {source_name}")

        target_path = target_documents_dir / source_name
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = target_documents_dir / f"{stem}_{int(datetime.now(tz=timezone.utc).timestamp())}{suffix}"

        payload = await file.read()
        target_path.write_bytes(payload)
        saved.append(target_path.name)

    return {
        "knowledge_base": resolved_knowledge_base,
        "uploaded": saved,
        "count": len(saved),
    }


def _run_ingest_job(
    *,
    knowledge_base: str,
    chunk_size: int,
    chunk_overlap: int,
    replace_collection: bool,
) -> None:
    target_documents_dir = _knowledge_base_dir(knowledge_base, create=True)
    target_collection_name = _knowledge_base_collection_name(knowledge_base)
    state = _get_ingest_state(knowledge_base)

    with ingest_lock:
        state["status"] = "running"
        state["started_at"] = datetime.now(tz=timezone.utc).isoformat()
        state["finished_at"] = None
        state["error"] = None
        state["result"] = None
        state["progress"] = {
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
                documents_dir=target_documents_dir,
                collection_name=target_collection_name,
                progress_callback=lambda progress: state.__setitem__("progress", progress),
            )
            state["status"] = "completed"
            state["result"] = result
        except Exception as exc:
            state["status"] = "failed"
            state["error"] = str(exc)
        finally:
            state["finished_at"] = datetime.now(tz=timezone.utc).isoformat()


@app.post("/ingest/start")
def start_ingestion(request: IngestRequest) -> dict:
    knowledge_base = _resolve_knowledge_base_name(request.knowledge_base)

    running_knowledge_bases = [name for name, entry in ingest_states.items() if entry.get("status") == "running"]
    if running_knowledge_bases:
        raise HTTPException(
            status_code=409,
            detail=f"Ingestion is already running for knowledge base: {running_knowledge_bases[0]}",
        )

    state = _get_ingest_state(knowledge_base)
    if state["status"] == "running":
        raise HTTPException(status_code=409, detail="Ingestion is already running for this knowledge base")

    if request.chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size must be > 0")

    if request.chunk_overlap < 0:
        raise HTTPException(status_code=400, detail="chunk_overlap must be >= 0")

    if request.chunk_overlap >= request.chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap must be less than chunk_size")

    runtime_settings["ingest_chunk_size"] = request.chunk_size
    runtime_settings["ingest_chunk_overlap"] = request.chunk_overlap

    _knowledge_base_dir(knowledge_base, create=True)

    job_id = str(uuid.uuid4())
    state["job_id"] = job_id

    thread = Thread(
        target=_run_ingest_job,
        kwargs={
            "knowledge_base": knowledge_base,
            "chunk_size": request.chunk_size,
            "chunk_overlap": request.chunk_overlap,
            "replace_collection": request.replace_collection,
        },
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "job_id": job_id,
        "knowledge_base": knowledge_base,
        "collection_name": _knowledge_base_collection_name(knowledge_base),
    }


@app.get("/ingest/status")
def get_ingest_status(knowledge_base: str | None = FastAPIQuery(default=None)) -> dict:
    resolved_knowledge_base = _resolve_knowledge_base_name(knowledge_base)
    state = _get_ingest_state(resolved_knowledge_base)
    return {
        **state,
        "knowledge_base": resolved_knowledge_base,
        "collection_name": _knowledge_base_collection_name(resolved_knowledge_base),
    }


@app.post("/ask")
def ask(query: Query) -> dict:
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")

    knowledge_base = _resolve_knowledge_base_name(query.knowledge_base)
    target_collection_name = _knowledge_base_collection_name(knowledge_base)

    # Track which paths are taken for monitoring
    debug_flags = {
        "used_fallback": False,
        "used_rescue": False,
        "used_incomplete_detection": False,
        "answer_length": 0,
        "retrieved_count": 0,
        "top_similarity_score": None,
    }

    try:
        qa_chain = build_qa_chain(
            retriever_top_k=runtime_settings["retriever_top_k"],
            llm_model=runtime_settings["llm_model"],
            llm_temperature=runtime_settings["llm_temperature"],
            ollama_num_ctx=runtime_settings["ollama_num_ctx"],
            ollama_num_predict=runtime_settings["ollama_num_predict"],
            collection_name=target_collection_name,
        )
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

    debug_flags["retrieved_count"] = len(source_documents)
    debug_flags["answer_length"] = len(answer)

    # Get top similarity score from retrieval
    if source_documents:
        try:
            vectorstore = get_vectorstore(collection_name=target_collection_name)
            docs_with_scores = vectorstore.similarity_search_with_score(query.question, k=1)
            if docs_with_scores:
                debug_flags["top_similarity_score"] = round(float(docs_with_scores[0][1]), 4)
        except Exception:
            pass

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
                ollama_num_predict=max(runtime_settings["ollama_num_predict"], 1024),
            )
            debug_flags["used_fallback"] = True
            debug_flags["answer_length"] = len(answer)
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
                ollama_num_predict=max(runtime_settings["ollama_num_predict"], 1024),
            )
            debug_flags["used_incomplete_detection"] = True
            debug_flags["answer_length"] = len(answer)
        except Exception:
            pass

    # Final rescue: when sources exist, avoid false no-information responses.
    if (
        source_documents
        and isinstance(answer, str)
        and answer.strip() == "The document does not contain this information."
    ):
        answer = _extractive_rescue_answer(query.question, source_documents)
        debug_flags["used_rescue"] = True
        debug_flags["answer_length"] = len(answer)

    return {
        "knowledge_base": knowledge_base,
        "collection_name": target_collection_name,
        "answer": answer,
        "sources": [
            {
                "page": d.metadata.get("page"),
                "source": d.metadata.get("source"),
            }
            for d in source_documents
        ],
        "debug": debug_flags,
    }


@app.post("/debug/retrieve")
def debug_retrieve_endpoint(query: Query) -> dict:
    """
    Debug endpoint: Shows all retrieved chunks with similarity scores.
    Use this to inspect what documents are being retrieved for your query.
    """
    if query.question.strip() == "":
        raise HTTPException(status_code=400, detail="question must not be empty")
    
    knowledge_base = _resolve_knowledge_base_name(query.knowledge_base)
    results = debug_retrieve(
        query.question,
        include_scores=True,
        collection_name=_knowledge_base_collection_name(knowledge_base),
    )
    return {
        "knowledge_base": knowledge_base,
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
    
    knowledge_base = _resolve_knowledge_base_name(query.knowledge_base)
    results = debug_retrieve_with_threshold(
        query.question,
        similarity_threshold=threshold,
        collection_name=_knowledge_base_collection_name(knowledge_base),
    )
    return {
        "knowledge_base": knowledge_base,
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
    
    knowledge_base = _resolve_knowledge_base_name(query.knowledge_base)
    results = debug_mmr_retrieve(
        query.question,
        lambda_mult=lambda_mult,
        collection_name=_knowledge_base_collection_name(knowledge_base),
    )
    return {
        "knowledge_base": knowledge_base,
        "query": query.question,
        "lambda_mult": lambda_mult,
        "retrieved_count": len(results),
        "documents": results,
    }
