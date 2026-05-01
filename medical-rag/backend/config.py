import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    langsmith_api_key: str | None
    database_url: str
    collection_name: str
    llm_provider: str
    embedding_model: str
    embedding_provider: str
    llm_model: str
    ollama_base_url: str
    documents_dir: str
    ingest_chunk_size: int
    ingest_chunk_overlap: int
    retriever_top_k: int
    llm_temperature: float
    ollama_num_ctx: int
    ollama_num_predict: int
    ollama_request_timeout_seconds: int
    ask_timeout_seconds: int


SETTINGS = Settings(
    langsmith_api_key=os.getenv("LANGCHAIN_API_KEY"),
    database_url=os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://admin:admin123@localhost:5202/medicalrag"
    ),
    collection_name=os.getenv("COLLECTION_NAME", "medical_docs"),
    llm_provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
    embedding_model=os.getenv("EMBEDDING_MODEL", "mxbai-embed-large:latest"),
    embedding_provider=os.getenv("EMBEDDING_PROVIDER", "ollama").lower(),
    llm_model=os.getenv("LLM_MODEL", "llama3.2:latest"),
    ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    documents_dir=os.getenv("DOCUMENTS_DIR", "../documents"),
    ingest_chunk_size=int(os.getenv("INGEST_CHUNK_SIZE", "800")),
    ingest_chunk_overlap=int(os.getenv("INGEST_CHUNK_OVERLAP", "120")),
    retriever_top_k=int(os.getenv("RETRIEVER_TOP_K", "5")),
    llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
    ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    ollama_num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "2048")),
    ollama_request_timeout_seconds=int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "30")),
    ask_timeout_seconds=int(os.getenv("ASK_TIMEOUT_SECONDS", "60")),
)
