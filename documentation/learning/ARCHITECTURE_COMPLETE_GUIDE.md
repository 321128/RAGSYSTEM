# Medical RAG System - Complete Architecture Guide

## 1. System Overview

The Medical RAG (Retrieval-Augmented Generation) system is a **local medical document Q&A application** that combines three key technologies:

- **Document Retrieval**: PostgreSQL with pgvector for semantic search
- **Intelligent Ranking**: Hybrid search (semantic + keyword) + cross-encoder reranking
- **Language Model**: Ollama-based LLM for generating answers

**Primary Workflow:**
```
Upload PDFs → Parse into chunks → Embed with sentence vectors → Store in pgvector
                                                                         ↓
                                    User asks question → Retrieve relevant chunks
                                                                         ↓
                                    Rerank & filter → Send context to LLM → Answer
```

---

## 2. Technology Stack

### **Frontend Layer**
- **Framework**: React + Vite
- **Port**: `5201`
- **Features**: Material Design UI, real-time status updates, chat history
- **State Management**: React hooks (useState, useEffect, useMemo)

### **Backend Layer**
- **Framework**: FastAPI (Python)
- **Port**: `5200`
- **Worker Model**: ThreadPoolExecutor for async ingestion/Q&A
- **Key Libraries**:
  - `LangChain` - document handling, chains, prompts
  - `SQLAlchemy` - ORM for chat history
  - `PGVector` - vector similarity search

### **Storage Layer**
- **Database**: PostgreSQL + pgvector extension
- **Port**: `5202`
- **Credentials**: `admin / admin123`
- **Collections**: Per-knowledge-base vector collections
- **Tables**:
  - `langchain_pg_collection` - Vector embeddings
  - `conversations` - Chat session metadata
  - `messages` - Individual messages with references

### **AI/ML Stack**
| Component | Provider | Model | Purpose |
|-----------|----------|-------|---------|
| **LLM** | Ollama (local) | medgemma:4b | Answer generation (medical-specialized) |
| **Embeddings** | HuggingFace | BAAI/bge-small-en | Convert text to vectors (384-dim) |
| **Reranker** | Sentence Transformers | cross-encoder/ms-marco-MiniLM-L-6-v2 | Re-score relevance |

---

## 3. Component Architecture

### **3.1 Frontend (React/Vite)**

**Key Sections:**
```
App.jsx (1500+ lines)
├── Overview        - System status, health checks
├── Knowledge Bases - Create, switch, delete KBs
├── Documents       - Upload & manage PDFs
├── Ingest          - Chunking parameters, progress tracking
├── Chat            - Q&A interface + conversation history
└── Settings        - LLM/Embedding config view
```

**State Management:**
```javascript
const [activeKnowledgeBase, setActiveKnowledgeBase] = useState('default');
const [conversations, setConversations] = useState([]);
const [currentConversation, setCurrentConversation] = useState(null);
const [conversationMessages, setConversationMessages] = useState([]);
const [question, setQuestion] = useState('');
const [answer, setAnswer] = useState('');
const [sources, setSources] = useState([]);
```

**Key UI Patterns:**
- **Polling**: Frontend polls `/ingest/status` every 500ms during ingestion
- **Async Operations**: Upload, ingest, ask all run with loading states
- **Theme Toggle**: Dark/light mode with localStorage persistence

---

### **3.2 Backend (FastAPI)**

**Core Files:**
```
backend/
├── app.py           - HTTP API endpoints, ingestion orchestration
├── rag_pipeline.py  - Retrieval chains, LLM setup, reranking
├── ingest.py        - PDF parsing, chunking, embedding
├── parser.py        - PDF extraction (Docling → PyPDF fallback)
├── database.py      - SQLAlchemy models for chat history
└── config.py        - Settings from .env
```

**Main API Endpoints:**

| Endpoint | Method | Purpose | Key Params |
|----------|--------|---------|-----------|
| `/health` | GET | Backend status | — |
| `/settings` | GET | Config info | — |
| `/conversations` | GET/POST | List/create chats | knowledge_base |
| `/conversations/{id}` | GET/PUT/DELETE | Single chat ops | — |
| `/documents` | GET | List PDFs by KB | knowledge_base |
| `/ingest/start` | POST | Begin ingestion | knowledge_base, replace_collection |
| `/ingest/status` | GET | Progress updates | knowledge_base |
| `/ingest/cancel` | POST | Stop ingestion | knowledge_base |
| `/data/clear` | POST | Delete KB & chunks | knowledge_base |
| `/ask` | POST | Ask question | question, conversation_id, kb, ... |

**Ingestion State Machine:**
```
idle → running → (completed OR failed)
```

Each knowledge base has independent state tracking:
```python
ingest_states: dict[str, dict] = {
    "default": {"status": "idle", "job_id": ..., "progress": ...},
    "diabetic foot": {"status": "completed", ...},
}
```

---

### **3.3 Database Schema**

**Vector Storage (PGVector):**
```sql
-- Auto-created by LangChain
langchain_pg_collection (collection_id, name, cmetadata)
langchain_pg_embedding (id, collection_id, embedding, document, cmetadata)
```

**Chat History:**
```sql
-- Conversation metadata
conversations (
  id UUID PRIMARY KEY,
  title VARCHAR,
  knowledge_base VARCHAR,  -- Links to KB
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Individual messages
messages (
  id UUID PRIMARY KEY,
  conversation_id UUID FOREIGN KEY,
  role ENUM('user', 'assistant'),
  content TEXT,
  sources JSON,  -- Retrieved documents cited
  created_at TIMESTAMP
)
```

---

### **3.4 Configuration System**

**File**: `.env`

```ini
# LLM Configuration
LLM_PROVIDER=ollama
LLM_MODEL=medgemma:4b
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Embedding Configuration  
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=BAAI/bge-small-en

# Database
DATABASE_URL=postgresql+psycopg2://admin:admin123@localhost:5202/medicalrag

# Ingestion
INGEST_CHUNK_SIZE=1024
INGEST_CHUNK_OVERLAP=200
RETRIEVER_TOP_K=10

# Ollama Parameters
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=2048
```

**Runtime Override**: `runtime_settings` in app.py (updated via API):
```python
runtime_settings = {
    "use_hybrid_search": True,    # Semantic + BM25
    "use_reranking": True,         # Cross-encoder scoring
    "similarity_threshold": 0.5,   # Minimum match score
}
```

---

## 4. Data Flow Analysis

### **4.1 Document Ingestion Flow**

```
User selects PDFs in frontend
                    ↓
POST /upload
  ├→ Save PDFs to documents/{knowledge_base}/
  └→ Return file list
                    ↓
POST /ingest/start (knowledge_base="diabetic foot")
  ├→ Validate KB name (no path traversal)
  ├→ Set state = "running"
  ├→ Spawn background thread → ingest_to_dict()
  │   ├→ Discover PDFs in documents/diabetic\ foot/
  │   ├→ Parse each PDF:
  │   │   ├→ Try Docling (better structured PDFs)
  │   │   └→ Fallback to PyPDF2 (simpler PDFs)
  │   ├→ Split into chunks (size=1024, overlap=200):
  │   │   └→ Recursive character splitting preserves semantic units
  │   ├→ Enrich metadata:
  │   │   ├→ source (filename)
  │   │   ├→ knowledge_base ("diabetic foot")
  │   │   └→ page_number
  │   ├→ Get embeddings:
  │   │   └→ BAAI/bge-small-en (384-dim vectors)
  │   ├→ Store in PGVector:
  │   │   └→ Collection name: medical_docs__diabetic_foot
  │   └→ Send progress updates
  └→ Return job_id to frontend

Frontend polls GET /ingest/status
  ├→ Returns {"status": "running", "progress": 45, ...}
  └→ UI updates progress bar

...ingestion completes...

POST /ingest/status returns {"status": "completed", "chunks_created": 1234}
```

---

### **4.2 Question-Answering Flow**

```
User types question in Chat tab
                    ↓
POST /ask
{
  "question": "What are diabetic foot complications?",
  "knowledge_base": "diabetic foot",
  "conversation_id": "uuid-123",
  "llm_temperature": 0.0
}
                    ├─→ Get active vectorstore for KB
                    │   └→ Collection: medical_docs__diabetic_foot
                    │
                    ├─→ Call enhanced_retrieve():
                    │   ├→ Hybrid search (semantic + BM25)
                    │   │   ├→ Semantic: vector similarity (pgvector)
                    │   │   └→ Keyword: BM25 sparse matching
                    │   ├→ Metadata filter: knowledge_base="diabetic foot"
                    │   ├→ Similarity threshold: >= 0.5
                    │   └→ Rerange with CrossEncoder:
                    │       ├→ Score each doc: query vs doc_text
                    │       └→ Sort by relevance score
                    │
                    ├─→ Build context from top-K chunks (default 10)
                    │   └→ Format: "Document A: ...\nDocument B: ..."
                    │
                    ├─→ Prompt template + context → LLM:
                    │   ├→ Instruction: Answer ONLY from context
                    │   ├→ Context: Retrieved chunks
                    │   ├→ Question: User input
                    │   └→ Model: medgemma:4b (medical-specialized)
                    │
                    ├─→ LLM generates answer
                    │
                    ├─→ Store in database:
                    │   ├→ INSERT Message (role=user, content, sources)
                    │   └→ INSERT Message (role=assistant, content)
                    │
                    └→ Return to frontend:
                        {
                          "answer": "Diabetic foot complications include...",
                          "sources": [
                            {"source": "foot_care.pdf", "content": "..."},
                            {"source": "complications.pdf", "content": "..."}
                          ]
                        }

Frontend displays:
  ├→ Question in chat bubble
  ├→ Answer with streaming (if implemented) or full text
  └→ Sources section with citations
```

---

## 5. Advanced Retrieval Architecture

### **5.1 Retrieval Improvements**

The system implements a **4-stage retrieval pipeline**:

```
Stage 1: Hybrid Search
  ├─ Semantic: Dense vector similarity in pgvector
  └─ Keyword: Sparse BM25 matching
       → Combines both for better coverage

Stage 2: Metadata Filtering
  ├─ Filter by: knowledge_base, source filename
  └─ Prevents cross-KB contamination

Stage 3: Similarity Threshold
  ├─ Min score: 0.5 (configurable)
  └─ Filters low-quality matches

Stage 4: Cross-Encoder Reranking
  ├─ Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  ├─ Re-scores retrieved chunks by relevance
  └─ Optional (can disable for speed)
```

### **5.2 Knowledge Base Isolation**

Each knowledge base = isolated document collection:

```
documents/
├── default/
│   └── med_basics.pdf ──→ Collection: medical_docs__default
├── diabetic_foot/
│   ├── complications.pdf
│   └── treatment.pdf ──→ Collection: medical_docs__diabetic_foot
└── surgery/
    └── techniques.pdf ──→ Collection: medical_docs__surgery
```

**Collection Naming**: `{base_collection_name}__{normalized_kb_name}`

**Isolation Mechanism**:
- User selects KB in frontend
- Backend creates vectorstore with KB-specific collection_name
- Query only searches that collection
- Metadata filter ensures no cross-contamination

---

## 6. Chat History System

### **6.1 Conversation Model**

```python
class Conversation(Base):
    id: str (UUID)
    title: str              # "What are diabetic complications?"
    knowledge_base: str     # "diabetic foot"
    created_at: datetime
    updated_at: datetime
    messages: List[Message] # Relationship
```

### **6.2 Message Model**

```python
class Message(Base):
    id: str (UUID)
    conversation_id: str    # Foreign key
    role: str               # "user" or "assistant"
    content: str            # Question or answer text
    sources: JSON str       # Retrieved documents (serialized)
    created_at: datetime
```

### **6.3 Frontend State**

```javascript
conversations         // All chats for current KB
currentConversation   // Selected chat metadata
conversationMessages  // Messages in selected chat
```

### **6.4 API Flow**

```
POST /ask (with conversation_id)
  ├→ Execute RAG pipeline
  ├→ Retrieve answer
  ├→ INSERT Message(role=user, ...)
  ├→ INSERT Message(role=assistant, sources=...)
  └→ Return answer + sources

GET /conversations/{id}
  └→ Return all messages for that conversation
     (Sorted by created_at)

DELETE /conversations/{id}
  └→ CASCADE delete all messages
```

---

## 7. Workflow Walkthrough: Start to Finish

### **Scenario: User adds diabetic foot documents and asks questions**

#### **Step 1: Create Knowledge Base**
```
Frontend → POST /kb/create (name="diabetic foot")
Backend  → Create directory: documents/diabetic\ foot/
Response → {success: true}
```

#### **Step 2: Upload PDFs**
```
Frontend → File input → POST /upload (folder: "diabetic foot")
          → Files saved to documents/diabetic\ foot/
Response → {files: ["complication.pdf", "treatment.pdf"]}
```

#### **Step 3: Ingest Documents**
```
Frontend → Click "Ingest" → POST /ingest/start
          (knowledge_base: "diabetic foot", chunk_size: 1024)

Backend  → Background worker:
          1. Parse PDFs with Docling/PyPDF
          2. Create ~250 chunks (each 1024 chars)
          3. Add metadata: knowledge_base="diabetic foot"
          4. Generate vectors: BAAI/bge-small-en (384-dim)
          5. Store in PGVector collection:
             medical_docs__diabetic_foot

Frontend → Polls /ingest/status every 500ms
          → Progress: 25%, 50%, 75%, 100%
          → Final: "Ingestion complete! 2 files, 250 chunks"
```

#### **Step 4: Ask Question (New Conversation)**
```
Frontend → POST /conversations (title: "Diabetic Foot Symptoms")
Response → {id: "conv-uuid", title: "...", message_count: 0}

Frontend → User types: "What are the main complications?"
          → POST /ask
          {
            question: "What are the main complications?",
            knowledge_base: "diabetic foot",
            conversation_id: "conv-uuid"
          }

Backend  → enhanced_retrieve():
          1. Search in medical_docs__diabetic_foot collection
          2. Find 30 candidates (hybrid search)
          3. Filter metadata: knowledge_base="diabetic foot"  ✓
          4. Threshold filter: score >= 0.5 ✓
          5. Rerank top 10 with CrossEncoder
          6. Return top 5 chunks

Backend  → build_qa_chain():
          ├─ Context: [chunk1, chunk2, chunk3, chunk4, chunk5]
          ├─ Prompt: "You are a medical assistant. Using ONLY..."
          ├─ Question: "What are the main complications?"
          ├─ LLM (medgemma:4b): Generate answer
          └─ Stop sequence: <|end_of_turn|>

Backend  → Save to database:
          ├─ INSERT Message(
               conversation_id: "conv-uuid",
               role: "user",
               content: "What are the main complications?",
               sources: "[]"
             )
          └─ INSERT Message(
               conversation_id: "conv-uuid",
               role: "assistant",
               content: "Diabetic foot complications include...",
               sources: "[{source: 'complication.pdf', ...}]"
             )

Frontend → Display:
          ├─ User message: "What are the main complications?"
          ├─ Assistant message: "Diabetic foot complications..."
          └─ Sources section with clickable references
```

#### **Step 5: Follow-up Question (Same Conversation)**
```
Frontend → User types: "How are these treated?"
          → POST /ask (conversation_id: "conv-uuid")

Backend  → Same RAG pipeline
          → Save both messages to database

Frontend → Chat history now shows:
          1. [Question 1] [Answer 1]
          2. [Question 2] [Answer 2]
          (Both in same conversation)
```

---

## 8. Performance Characteristics

### **Ingestion**
- **Speed**: ~2-3 chunks per second
- **Bottleneck**: LLM embedding generation
- **Example**: 100-page PDF → ~250 chunks → ~90 seconds

### **Query Response**
- **Retrieval**: 200-500ms (hybrid search + reranking)
- **LLM**: 5-15 seconds (medgemma:4b generation)
- **Total**: ~6-16 seconds per question
- **Bottleneck**: LLM inference (not retrieval)

### **Concurrency**
- **Ingestion**: 1 per KB (sequential, thread-safe)
- **Q&A**: 4 parallel workers (ThreadPoolExecutor)
- **Upload**: No limit (local file copy)

---

## 9. Error Handling & Graceful Degradation

### **Embedding Provider Fallbacks**
```
HuggingFace (BAAI/bge-small-en)
  → Falls back to: Ollama embeddings
  → Falls back to: OpenAI embeddings
```

### **Retrieval Fallbacks**
```
Hybrid Search (semantic + BM25)
  → If BM25 unavailable: Semantic only
  
Cross-Encoder Reranking
  → If unavailable: Use original scores
  
Metadata Filtering
  → If metadata absent: Return all results
```

### **Ingestion Robustness**
```
PDF Parsing
  → Docling (structured PDFs)
  → PyPDF2 (fallback)
  → Error logged, file skipped, ingestion continues

Null Bytes in Text
  → Sanitized before DB storage
  → Prevents PostgreSQL constraint violations
```

---

## 10. Configuration & Runtime Control

### **Three Configuration Levels**

**Level 1: .env File** (Startup)
- Sets defaults for all components
- Example: `LLM_MODEL=medgemma:4b`

**Level 2: runtime_settings** (Runtime, API calltime)
- Can be modified via API
- Example: `use_reranking=false` for speed

**Level 3: Request Parameters** (Query-level)
- Per-ask customization
- Example: `POST /ask` with custom `llm_temperature`

### **Runtime Configuration Access**

```python
# backend/app.py
runtime_settings = {
    "llm_model": SETTINGS.llm_model,
    "llm_temperature": SETTINGS.llm_temperature,
    "use_hybrid_search": True,
    "use_reranking": True,
    "similarity_threshold": 0.5,
}

# Passed to build_qa_chain():
chain = build_qa_chain(
    use_hybrid_search=runtime_settings["use_hybrid_search"],
    use_reranking=runtime_settings["use_reranking"],
    similarity_threshold=runtime_settings["similarity_threshold"],
)
```

---

## 11. Key Design Patterns

### **Pattern 1: Collection Abstraction**
Each KB = separate PGVector collection = isolated search scope
- Enables multi-user, multi-domain scenarios
- No contamination between KBs

### **Pattern 2: Metadata Enrichment**
- Metadata added at ingestion time (permanent)
- Checked at retrieval time (filtering)
- Enables constrained search

### **Pattern 3: Graceful Degradation**
- Each component has optional fallback
- System works if any layer fails
- Errors logged, not fatal

### **Pattern 4: Background Threading**
- Ingestion runs in background thread
- API stays responsive
- Client polls for status

### **Pattern 5: Prompt Engineering**
- Detailed system message → Better answers
- Context window management → No overflows
- Temperature = 0 → Deterministic answers

---

## 12. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React/Vite :5201)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐   │
│  │  Knowledge   │ │  Documents   │ │  Chat Interface        │   │
│  │  Base Mgmt   │ │  & Ingest    │ │  + Conversation Panel  │   │
│  └──────────────┘ └──────────────┘ └────────────────────────┘   │
└────────────────────────────────────────────────────────────────┬─┘
                            ↕ HTTP/REST
┌────────────────────────────────────────────────────────────────┬─┐
│                   BACKEND (FastAPI :5200)                      │ │
│  ┌──────────────────────────────────────────────────────────┐  │ │
│  │ app.py: HTTP Endpoints + Orchestration                  │  │ │
│  │  ├─ /ask (RAG Pipeline)      ├─ /conversations (Chat)   │  │ │
│  │  ├─ /ingest (Ingestion)      ├─ /documents (KB Ops)     │  │ │
│  │  └─ /settings (Config)       └─ /data/clear (Reset)     │  │ │
│  └──────────────────────────────────────────────────────────┘  │ │
│  ┌──────────────────────────────────────────────────────────┐  │ │
│  │ RAG Pipeline: rag_pipeline.py                            │  │ │
│  │  ├─ get_vectorstore()        ├─ enhanced_retrieve()     │  │ │
│  │  ├─ get_embeddings()         ├─ hybrid_search()        │  │ │
│  │  ├─ get_llm()                ├─ rerank_documents()     │  │ │
│  │  └─ build_qa_chain()         └─ Custom EnhancedRetriever│  │ │
│  └──────────────────────────────────────────────────────────┘  │ │
│  ┌──────────────────────────────────────────────────────────┐  │ │
│  │ Ingestion Pipeline: ingest.py                            │  │ │
│  │  ├─ _load_documents() [PDF discovery]                   │  │ │
│  │  ├─ parse_pdf() [Docling/PyPDF]                         │  │ │
│  │  ├─ _split_into_chunks() [RecursiveCharacterSplitter]   │  │ │
│  │  ├─ metadata enrichment [knowledge_base tag]            │  │ │
│  │  └─ vectorization + PGVector storage                    │  │ │
│  └──────────────────────────────────────────────────────────┘  │ │
└────────────────────────────────────────────────────────────────┴─┘
          ↕ SQL / Embeddings generation / LLM inference
┌────────────────────────────────────────────────────────────────┬─┐
│                   STORAGE & AI LAYERS                          │ │
│  ┌──────────────────┐    ┌──────────────────┐                  │ │
│  │  PostgreSQL+     │    │  Ollama          │                  │ │
│  │  pgvector        │    │  (LLM + Embed)   │                  │ │
│  │  :5202           │    │  :11434          │                  │ │
│  │                  │    │                  │                  │ │
│  │  - langchain_    │    │  - medgemma:4b   │                  │ │
│  │    pg_collection │    │  - BAAI/bge-     │                  │ │
│  │  - langchain_    │    │    small-en      │                  │ │
│  │    pg_embedding  │    │                  │                  │ │
│  │  - conversations │    │  Sentence-       │                  │ │
│  │  - messages      │    │  Transformers    │                  │ │
│  │                  │    │  CrossEncoder    │                  │ │
│  └──────────────────┘    └──────────────────┘                  │ │
└────────────────────────────────────────────────────────────────┴─┘
            ↕
┌────────────────────────────────────────────────────────────────┬─┐
│                   FILE SYSTEM                                  │ │
│  documents/                                                    │ │
│  ├── default/ [PDFs]          ┌─ Collection: medical_docs__def│ │
│  ├── diabetic_foot/ [PDFs]  ─→├─ Collection: medical_docs__df│ │
│  └── surgery/ [PDFs]          └─ Collection: medical_docs__surg│ │
└────────────────────────────────────────────────────────────────┴─┘
```

---

## 13. Current Status (May 2026)

### ✅ Completed Features
- **Document Management**: Upload, parse (Docling+PyPDF), chunk, embed
- **Multi-KB Support**: Isolated collections per knowledge base
- **Semantic Search**: pgvector similarity search
- **Hybrid Retrieval**: Semantic + BM25 keyword search
- **Advanced Ranking**: Cross-encoder reranking with fallback
- **Metadata Filtering**: Per-KB result isolation
- **Chat History**: Persistent conversations with message threading
- **LLM Integration**: Ollama/OpenAI-compatible
- **Configurable Embeddings**: HuggingFace/Ollama/OpenAI support

### 🔧 Current Configuration
- **LLM**: medgemma:4b (medical-optimized, 4B params)
- **Embeddings**: BAAI/bge-small-en (HuggingFace, 384-dim)
- **Reranker**: cross-encoder/ms-marco-MiniLM-L-6-v2
- **DB**: PostgreSQL + pgvector
- **Frontend**: React + Vite (responsive, dark/light theme)

### 📋 Pending Tasks
1. **Re-ingest documents** - Add knowledge_base metadata to existing chunks
2. **Run diagnostics** - Validate all improvements with test suite
3. **Performance tuning** - Optimize for speed vs accuracy tradeoff

---

## 14. Quick Reference

### **Port Map**
```
Frontend:    http://localhost:5201
Backend:     http://localhost:5200
PostgreSQL:  localhost:5202 (admin/admin123)
Ollama:      http://127.0.0.1:11434
```

### **Key Files**
```
frontend/src/App.jsx              - Main UI (1500 lines)
backend/app.py                    - HTTP endpoints + orchestration
backend/rag_pipeline.py           - Retrieval & QA chain logic
backend/ingest.py                 - Document ingestion pipeline
backend/database.py               - Chat history models
backend/config.py                 - .env → Settings dataclass
.env                              - Configuration
```

### **Common Operations**
```bash
# Start everything
cd medical-rag && bash script.sh start

# Stop everything
bash stop.sh

# View backend logs
tail -f .run-logs/backend.log

# View frontend logs
tail -f .run-logs/frontend.log

# Reset database (careful!)
psql medicalrag -U admin -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

---

## 15. Architecture Strengths

✅ **Modularity** - Each component independently replaceable  
✅ **Scalability** - Multi-KB support, thread pooling for concurrency  
✅ **Robustness** - Graceful degradation, comprehensive error handling  
✅ **Medical Focus** - Specialized LLM (medgemma), detailed prompts  
✅ **User Experience** - Chat history, real-time progress, responsive UI  
✅ **Extensibility** - Easy to add new embedders, LLMs, rerankers  

