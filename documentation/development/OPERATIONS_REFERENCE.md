# Medical RAG - Key Operations Reference

## Operation 1: Upload & Ingest Documents

### Frontend Flow
```
User selects PDFs → Click "Select Files" → Drag & Drop area
                                               ↓
                         POST /upload (multipart/form-data)
                                               ↓
            Backend saves to documents/{knowledge_base}/
                                               ↓
           Frontend displays "Files ready for ingest"
```

### Request Example
```bash
POST /upload?knowledge_base=diabetic_foot
Content-Type: multipart/form-data

[PDF Binary Data]
```

### Response
```json
{
  "success": true,
  "knowledge_base": "diabetic_foot",
  "uploaded_files": ["complications.pdf", "treatment.pdf"],
  "message": "2 files uploaded successfully"
}
```

### Backend Processing
```
documents/
└── diabetic_foot/
    ├── complications.pdf
    └── treatment.pdf
```

---

## Operation 2: Ingest (Parsing & Vectorization)

### Frontend Flow
```
User clicks "Start Ingestion"
         ↓
POST /ingest/start
{
  knowledge_base: "diabetic_foot",
  chunk_size: 1024,
  chunk_overlap: 200,
  replace_collection: false
}
         ↓
Returns job_id
         ↓
Frontend polls GET /ingest/status every 500ms
         ↓
Shows progress bar: 0% → 25% → 50% → 75% → 100%
         ↓
When complete: "Ingestion finished! 2 files, 245 chunks"
```

### Backend Processing (Background Thread)
```
1. Discover PDFs in documents/diabetic_foot/
2. For each PDF:
   ├─ Parse with Docling (structured)
   └─ Fallback to PyPDF2 (if Docling fails)
3. Extract text + metadata (filename, page number)
4. Split into chunks:
   ├─ Size: 1024 characters
   └─ Overlap: 200 characters
5. For each chunk:
   ├─ Add metadata: knowledge_base="diabetic_foot"
   ├─ Generate embedding: BAAI/bge-small-en (384-dim)
   └─ Store in PGVector: medical_docs__diabetic_foot
6. Emit progress: {status: "running", progress: 45}
```

### Status Poll Example
```bash
GET /ingest/status?knowledge_base=diabetic_foot
```

### Response (Running)
```json
{
  "status": "running",
  "job_id": "job-uuid-123",
  "progress": 65,
  "started_at": "2026-05-13T10:30:00Z",
  "result": null,
  "error": null
}
```

### Response (Completed)
```json
{
  "status": "completed",
  "job_id": "job-uuid-123",
  "progress": 100,
  "started_at": "2026-05-13T10:30:00Z",
  "finished_at": "2026-05-13T10:35:45Z",
  "result": {
    "scanned_files": 2,
    "parsed_documents": 45,
    "chunks_created": 245,
    "failed_files": []
  },
  "error": null
}
```

---

## Operation 3: Ask Question (RAG Pipeline)

### Frontend Flow
```
User types question in chat: "What are complications?"
                             ↓
                      Click "Send" or Enter
                             ↓
User message appears immediately in chat
                             ↓
POST /ask
{
  question: "What are complications?",
  knowledge_base: "diabetic_foot",
  conversation_id: "conv-uuid" (optional)
}
                             ↓
UI shows loading spinner
                             ↓
Response received (5-20 seconds)
                             ↓
Answer appears in chat + sources displayed
```

### Request Payload
```json
{
  "question": "What are the main complications of diabetic foot?",
  "knowledge_base": "diabetic_foot",
  "conversation_id": "18847c5f-500a-4730-8323-9da05149e875",
  "llm_model": "medgemma:4b",
  "llm_temperature": 0.0,
  "use_hybrid_search": true,
  "use_reranking": true,
  "similarity_threshold": 0.5
}
```

### Backend RAG Pipeline (Detailed)

```
Step 1: Initialize
├─ Get vectorstore for collection: medical_docs__diabetic_foot
└─ Get LLM: medgemma:4b via Ollama

Step 2: Retrieve (enhanced_retrieve function)
├─ Hybrid Search:
│  ├─ Semantic: Query pgvector for similar chunks
│  │  └─ Returns 30 candidates with scores (cosine similarity)
│  └─ Keyword: BM25 matching on chunk text
│     └─ Returns 20 candidates with BM25 scores
├─ Merge & deduplicate:
│  └─ Combine both result sets (keeping order)
├─ Metadata filter:
│  └─ Keep only: knowledge_base == "diabetic_foot" ✓
├─ Threshold filter:
│  └─ Keep only: score >= 0.5 ✓
└─ Rerank (if enabled):
   ├─ Load cross-encoder model
   ├─ Score each candidate: query_text vs candidate_text
   ├─ Resort by new scores (descending)
   └─ Return top K=10

Result: Top 10 most relevant chunks

Step 3: Build Context
├─ Format chunks:
│  ├─ Chunk 1 (similarity: 0.87):
│  │  "...complications include ulcers, infections, gangrene..."
│  ├─ Chunk 2 (similarity: 0.81):
│  │  "...prevention: proper foot care, regular inspections..."
│  └─ ... (8 more chunks)
└─ Total context: ~3000-5000 tokens

Step 4: Build Prompt
├─ System instruction
├─ Retrieved context
├─ Question
└─ Instruction: "Answer ONLY from context"

Prompt Template:
"""
You are a medical research assistant providing comprehensive answers.

Using ONLY the context below, answer the question thoroughly.

Rules:
- Answer only from the provided context
- Include specific facts, numbers, percentages
- For procedures: explain all steps
- Be specific: medications, doses, duration
- Quote relevant phrases from sources
- If information is missing: state explicitly

Context:
{context}

Question:
{question}

Answer:
"""

Step 5: LLM Inference
├─ Model: medgemma:4b
├─ Temperature: 0.0 (deterministic)
├─ Context window: 8192 tokens
├─ Max output: 2048 tokens
└─ Inference time: ~5-15 seconds

Response:
"""
Diabetic foot complications are serious concerns requiring proper management.
The main complications include:

1. **Ulcers and Wounds**
   - Non-healing sores due to reduced moisture and circulation
   - Can progress to infection if not treated

2. **Infections**  
   - Bacterial and fungal infections common
   - Can lead to sepsis if untreated

3. **Gangrene**
   - Tissue death from severe ischemia
   - May require amputation in advanced cases

[more details from context...]

According to the source documents, prevention through regular foot care
and monitoring is critical.
"""

Step 6: Extract Sources
├─ Parse answer references
├─ Find matching chunks
└─ Compile source list:
   [
     {source: "complications.pdf", page: 2, snippet: "..."},
     {source: "treatment.pdf", page: 5, snippet: "..."}
   ]

Step 7: Store in Database
├─ INSERT into messages:
│  ├─ conversation_id: "18847c5f-500a..."
│  ├─ role: "user"
│  ├─ content: "What are the main complications of diabetic foot?"
│  └─ sources: "[]"
└─ INSERT into messages:
   ├─ conversation_id: "18847c5f-500a..."
   ├─ role: "assistant"
   ├─ content: "[full answer text]"
   └─ sources: "[{...source list...}]"

Step 8: Return Response
```

### Response Payload
```json
{
  "answer": "Diabetic foot complications are serious concerns...",
  "sources": [
    {
      "source": "complications.pdf",
      "page": 2,
      "content": "Complications include ulcers, infections, gangrene..."
    },
    {
      "source": "treatment.pdf",
      "page": 5,  
      "content": "Prevention through regular foot care is critical..."
    }
  ],
  "metadata": {
    "retrieval_time_ms": 342,
    "reranking_enabled": true,
    "chunks_retrieved": 10,
    "similarity_threshold": 0.5
  }
}
```

---

## Operation 4: Create Conversation

### Request
```bash
POST /conversations
{
  "title": "Diabetic Foot Complications",
  "knowledge_base": "diabetic_foot"
}
```

### Response
```json
{
  "id": "18847c5f-500a-4730-8323-9da05149e875",
  "title": "Diabetic Foot Complications",
  "knowledge_base": "diabetic_foot",
  "created_at": "2026-05-13T10:30:00Z",
  "updated_at": "2026-05-13T10:30:00Z",
  "message_count": 0
}
```

### Database Insert
```sql
INSERT INTO conversations (id, title, knowledge_base, created_at, updated_at)
VALUES (
  '18847c5f-500a-4730-8323-9da05149e875',
  'Diabetic Foot Complications',
  'diabetic_foot',
  NOW(),
  NOW()
);
```

---

## Operation 5: Get Conversation with History

### Request
```bash
GET /conversations/18847c5f-500a-4730-8323-9da05149e875
```

### Response
```json
{
  "id": "18847c5f-500a-4730-8323-9da05149e875",
  "title": "Diabetic Foot Complications",
  "knowledge_base": "diabetic_foot",
  "created_at": "2026-05-13T10:30:00Z",
  "updated_at": "2026-05-13T10:35:45Z",
  "messages": [
    {
      "id": "msg-uuid-1",
      "role": "user",
      "content": "What are the main complications?",
      "sources": [],
      "created_at": "2026-05-13T10:31:00Z"
    },
    {
      "id": "msg-uuid-2",
      "role": "assistant",
      "content": "Diabetic foot complications include...",
      "sources": [
        {
          "source": "complications.pdf",
          "content": "..."
        }
      ],
      "created_at": "2026-05-13T10:31:15Z"
    },
    {
      "id": "msg-uuid-3",
      "role": "user",
      "content": "How are these prevented?",
      "sources": [],
      "created_at": "2026-05-13T10:32:00Z"
    },
    {
      "id": "msg-uuid-4",
      "role": "assistant",
      "content": "Prevention includes regular foot care...",
      "sources": [
        {
          "source": "treatment.pdf",
          "content": "..."
        }
      ],
      "created_at": "2026-05-13T10:32:20Z"
    }
  ]
}
```

---

## Operation 6: List Knowledge Bases

### Request
```bash
GET /knowledge_bases
```

### Response
```json
{
  "knowledge_bases": [
    {
      "name": "default",
      "document_count": 0,
      "chunk_count": 0
    },
    {
      "name": "diabetic_foot",
      "document_count": 2,
      "chunk_count": 245
    },
    {
      "name": "surgery",
      "document_count": 5,
      "chunk_count": 1200
    }
  ]
}
```

### Filesystem Structure
```
documents/
├── default/           [Empty, placeholder]
├── diabetic_foot/     [2 PDFs → 245 chunks]
└── surgery/           [5 PDFs → 1200 chunks]
```

---

## Operation 7: Switch Knowledge Base

### Frontend Flow
```
User clicks dropdown: "Current KB: diabetic_foot"
         ↓
Selects: "surgery"
         ↓
Frontend updates: activeKnowledgeBase = "surgery"
         ↓
Conversations sidebar reloads with surgery conversations
         ↓
All future /ask calls use knowledge_base="surgery"
```

### Backend Behavior
```javascript
// Before switch
GET /conversations?knowledge_base=diabetic_foot
→ Returns only diabetic_foot conversations

// After switch
GET /conversations?knowledge_base=surgery
→ Returns only surgery conversations
```

---

## Operation 8: Clear Knowledge Base

### Request
```bash
POST /data/clear
{
  "knowledge_base": "diabetic_foot"
}
```

### Backend Processing
```
1. Check if ingestion in progress
   → If yes: Return 409 Conflict
   
2. Delete from PostgreSQL:
   DELETE FROM langchain_pg_embedding
   WHERE collection_id IN (
     SELECT collection_id FROM langchain_pg_collection
     WHERE name = 'medical_docs__diabetic_foot'
   )
   
3. Delete collection record:
   DELETE FROM langchain_pg_collection
   WHERE name = 'medical_docs__diabetic_foot'

4. Delete files:
   rm -rf documents/diabetic_foot/*

5. Delete conversations:
   DELETE FROM messages WHERE conversation_id IN (
     SELECT id FROM conversations WHERE knowledge_base='diabetic_foot'
   )
   DELETE FROM conversations WHERE knowledge_base='diabetic_foot'
```

### Response
```json
{
  "success": true,
  "knowledge_base": "diabetic_foot",
  "message": "Knowledge base cleared successfully"
}
```

---

## Operation 9: Get System Settings

### Request
```bash
GET /settings
```

### Response
```json
{
  "llm_model": "medgemma:4b",
  "llm_provider": "ollama",
  "embedding_model": "BAAI/bge-small-en",
  "embedding_provider": "huggingface",
  "retriever_top_k": 10,
  "ingest_chunk_size": 1024,
  "ingest_chunk_overlap": 200,
  "llm_temperature": 0.0,
  "ollama_num_ctx": 8192,
  "ollama_num_predict": 2048,
  "use_hybrid_search": true,
  "use_reranking": true,
  "similarity_threshold": 0.5
}
```

### Frontend Display
```
Settings Tab shows:
┌─────────────────────────────────┐
│ LLM Model      │ medgemma:4b     │
│ Embeddings     │ BAAI/bge-small  │
│ Top K Results  │ 10              │
│ Temperature    │ 0.0             │
│ Hybrid Search  │ ✓ Enabled       │
│ Reranking      │ ✓ Enabled       │
└─────────────────────────────────┘
```

---

## Data Flow Timing

### Typical Response Times

| Operation | Time | Bottleneck |
|-----------|------|------------|
| Upload 10MB PDF | <1s | Network |
| Parse + Chunk | 2-5s | PDF parsing |
| Embed 100 chunks | 10-20s | Vector generation |
| Semantic search | 100-200ms | pgvector query |
| BM25 search | 50-100ms | Text matching |
| Cross-encoder rerank | 1-3s | Neural inference |
| LLM generation | 5-15s | Model inference |
| **Total Q&A** | **6-20s** | LLM inference |

### Resource Usage

```
Embedding Model (BAAI/bge-small-en):
├─ Size: ~270 MB
├─ Memory: ~500 MB during inference
└─ Device: CUDA (GPU)

LLM Model (medgemma:4b):
├─ Size: 2.5 GB quantized
├─ Memory: ~6 GB during inference
└─ Device: CUDA (GPU)

Reranker (cross-encoder MiniLM):
├─ Size: ~300 MB
├─ Memory: ~1 GB during inference
└─ Latency: ~100-200ms per query

PostgreSQL:
├─ Database size: ~2-10 GB (depending on documents)
├─ Vector embeddings: ~384 bytes per chunk
└─ Concurrent connections: 10+
```

---

## Error Scenarios & Handling

### Scenario 1: Ingestion During Query
```
User asks question while ingestion in progress
         ↓
/ask called while /ingest/start is running
         ↓
System tries to use collection
         ↓
Collection might be locked or incomplete
         ↓
Error: "Collection not yet available"
         ↓
Frontend shows: "Please wait for ingestion to complete"
```

### Scenario 2: PDF Parse Failure
```
Corrupt PDF encountered during ingestion
         ↓
Docling fails to parse
         ↓
Falls back to PyPDF2
         ↓
PyPDF2 also fails
         ↓
Error logged: "diabetic_complications.pdf: Invalid PDF"
         ↓
Ingestion continues with remaining files
         ↓
Result includes: {"failed_files": ["diabetic_complications.pdf: ..."]}
```

### Scenario 3: Embedding Generation Fails
```
CUDA out of memory during vectorization
         ↓
HuggingFace embeddings fail
         ↓
Falls back to: (Can't skip embeddings - fatal)
         ↓
Ingestion aborts
         ↓
Status: "failed"
         ↓
Error: "Out of memory: CUDA allocation failed"
         ↓
Solution: Reduce chunk size or free GPU memory
```

### Scenario 4: Empty Knowledge Base Query
```
User asks question when KB has no documents
         ↓
PGVector collection is empty
         ↓
Retrieval returns 0 chunks
         ↓
No context to feed LLM
         ↓
LLM generates fallback answer
         ↓
Response: "No documents found. Please ingest documents first."
```

---

## Connection String Reference

```
# PostgreSQL
postgresql+psycopg2://admin:admin123@localhost:5202/medicalrag

# Components
└─ Driver: psycopg2 (Python PostgreSQL adapter)
└─ Host: localhost
└─ Port: 5202
└─ Database: medicalrag
└─ User: admin
└─ Password: admin123
```

