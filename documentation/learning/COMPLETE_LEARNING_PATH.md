# Medical RAG Architecture - Complete Learning Path

## 📚 Documentation Structure

You now have 4 comprehensive guides. Here's what each covers and how to read them:

### 1. **ARCHITECTURE_COMPLETE_GUIDE.md** (You are here)
**What**: System overview, tech stack, components, data flows  
**When to read**: First time understanding the system  
**Length**: ~1500 lines  
**Contains**:
- System overview & high-level flow
- Technology stack (9 sections)
- Component breakdown (9 sections)
- Data flow analysis (ingestion, Q&A, retrieval)
- Advanced retrieval architecture
- Chat history system
- Workflow walkthrough
- Performance characteristics
- Error handling
- Configuration system
- Design patterns
- Architecture diagram
- Current status & next steps

**Start here if**: You're new and want the big picture

---

### 2. **MENTAL_MODELS.md** 
**What**: Conceptual understanding, principles, debugging  
**When to read**: After reading architecture guide, when you need deeper understanding  
**Length**: ~1200 lines  
**Contains**:
- 6 core mental models (with diagrams)
- Architecture principles (separation of concerns, etc.)
- Data consistency model
- Detailed question-answer loop
- Quality metrics
- Common misconceptions
- Debugging tree
- Performance optimization ladder
- Growth path

**Start here if**: You want to understand WHY the system works this way

---

### 3. **OPERATIONS_REFERENCE.md**
**What**: Complete API reference with request/response examples  
**When to read**: When building/modifying features, debugging specific operations  
**Length**: ~900 lines  
**Contains**:
- 9 detailed operations with full request/response
- Backend processing details
- Data flow timing
- Resource usage
- Error scenarios
- Connection strings
- Database schema

**Start here if**: You're integrating or debugging a specific feature

---

### 4. **Existing Documentation** (Reference)
**ARCHITECTURE_AND_RUNBOOK.md**: Original architecture (still valid)  
**README.md**: Quick start guide  
**IMPLEMENTATION_SUMMARY.md**: (Check for latest features)  

---

## 🎯 Quick Navigation by Use Case

### "I want to understand the whole system"
```
Read in order:
1. This file (overview)
2. ARCHITECTURE_COMPLETE_GUIDE.md sections 1-3
3. Render the architecture diagram (mermaid in section 12)
4. MENTAL_MODELS.md sections "Core Mental Models" (1-6)
Time: ~45 minutes
```

### "How does document ingestion work?"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 4.1: Document Ingestion Flow (12 steps)
  - Section 3.2 Backend: Describes ingest.py

OPERATIONS_REFERENCE.md:
  - Operation 2: Ingest (step-by-step)
  
MENTAL_MODELS.md:
  - Model 1: Document Lifecycle
  - Model 6 (bonus): Metadata Tag System
Time: ~20 minutes
```

### "How does question-answering work?"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 4.2: Question-Answering Flow (detailed)
  - Section 5: Advanced Retrieval Architecture
  
MENTAL_MODELS.md:
  - Model 3: Retrieval Process as Funnel
  - Model 4: Metadata Tag System
  - Model 5: Hybrid Search
  - Model 6: The Reranker
  - Section: Question-Answer Loop (Detailed)
  
OPERATIONS_REFERENCE.md:
  - Operation 3: Ask Question (full request/response)
Time: ~30 minutes
```

### "How is data organized? (Knowledge Bases, Collections)"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 3.4: Configuration System
  - Section 5.2: Knowledge Base Isolation
  - Section 7: Workflow Walkthrough (Step 1)
  
MENTAL_MODELS.md:
  - Model 2: Knowledge Base as an Island
  - Model 4: Metadata Tag System
  
OPERATIONS_REFERENCE.md:
  - Operation 6: List Knowledge Bases
  - Operation 7: Switch Knowledge Base
  - Operation 8: Clear Knowledge Base
Time: ~15 minutes
```

### "How does chat history work?"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 6: Chat History System (3 subsections)
  - Section 3.3: Database Schema (conversations/messages tables)
  
OPERATIONS_REFERENCE.md:
  - Operation 4: Create Conversation
  - Operation 5: Get Conversation with History
  
Memory Note:
  - /memories/repo/chat-history-implementation.md
Time: ~15 minutes
```

### "What are the advanced retrieval features?"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 5: Advanced Retrieval Architecture (entire)
  - Section 5.1: Retrieval Improvements (4-stage pipeline)
  
Repository Memory:
  - /memories/repo/retrieval-improvements-apr27.md
  
MENTAL_MODELS.md:
  - Model 3: Retrieval as Funnel
  - Model 5: Hybrid Search
  - Model 6: The Reranker
Time: ~25 minutes
```

### "How do I debug when something's wrong?"
```
MENTAL_MODELS.md:
  - Section: Debugging Mental Model (tree diagram)
  - Section: Common Misconceptions (4 things people misunderstand)
  
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 9: Error Handling & Graceful Degradation
  
OPERATIONS_REFERENCE.md:
  - Error Scenarios & Handling
Time: ~20 minutes
```

### "I need to modify the system - where's the code?"
```
ARCHITECTURE_COMPLETE_GUIDE.md:
  - Section 3: Component Architecture (file locations)
  
Key Files:
  backend/app.py              - HTTP endpoints
  backend/rag_pipeline.py     - Retrieval logic  
  backend/ingest.py           - Document processing
  backend/database.py         - Chat history models
  frontend/src/App.jsx        - UI (1500 lines)
  .env                        - Configuration
  
OPERATIONS_REFERENCE.md:
  - Use for understanding request/response format
Time: ~varies
```

---

## 🔧 Reference Tables

### Ports at a Glance
| Service | Host | Port | Purpose |
|---------|------|------|---------|
| Frontend | localhost | 5201 | React UI |
| Backend API | localhost | 5200 | FastAPI |
| PostgreSQL | localhost | 5202 | pgvector storage |
| Ollama | 127.0.0.1 | 11434 | LLM + Embeddings |

### Key Files at a Glance
| File | Purpose | Key Function |
|------|---------|--------------|
| app.py | HTTP endpoints | /ask, /ingest/start, /conversations |
| rag_pipeline.py | RAG logic | enhanced_retrieve(), build_qa_chain() |
| ingest.py | Document processing | ingest_to_dict() |
| database.py | Chat storage | Conversation, Message models |
| frontend/App.jsx | UI | 1500 lines React |

### Current Models at a Glance
| Component | Model | Provider | Purpose |
|-----------|-------|----------|---------|
| LLM | medgemma:4b | Ollama | Answer generation |
| Embeddings | BAAI/bge-small-en | HuggingFace | Vector generation |
| Reranker | cross-encoder/ms-marco-MiniLM | Sentence Transformers | Relevance scoring |

### Configuration at a Glance
| Setting | Value | Impact |
|---------|-------|--------|
| INGEST_CHUNK_SIZE | 1024 | Larger = broader context, fewer chunks |
| INGEST_CHUNK_OVERLAP | 200 | Larger = smoother transitions, more chunks |
| RETRIEVER_TOP_K | 10 | Larger = more context, slower, more noise |
| LLM_TEMPERATURE | 0.0 | 0=deterministic, 1.0=random |
| similarity_threshold | 0.5 | Higher = fewer results, better quality |

---

## 🚀 Quick Operations Reference

### Most Common Operations

**Upload Documents**
```
File: OPERATIONS_REFERENCE.md
Operation: 1 - Upload & Ingest Documents
Time: See "Ingest" row in Operations timing table
```

**Ask a Question**
```
File: OPERATIONS_REFERENCE.md
Operation: 3 - Ask Question (RAG Pipeline)
Expected Time: 6-20 seconds
```

**View Chat History**
```
File: OPERATIONS_REFERENCE.md
Operation: 5 - Get Conversation with History
Endpoint: GET /conversations/{id}
```

**Switch Knowledge Base**
```
File: OPERATIONS_REFERENCE.md
Operation: 7 - Switch Knowledge Base
Effect: All future queries use new KB
```

**Clear Knowledge Base**
```
File: OPERATIONS_REFERENCE.md
Operation: 8 - Clear Knowledge Base
Warning: Deletes all documents + chat history
```

---

## 📊 Data Flow Quick Reference

### Ingestion Path
```
User Uploads PDFs
    ↓
POST /upload saves to documents/{kb}/
    ↓
POST /ingest/start dispatches background worker
    ↓
Worker: Parse → Chunk → Embed → Store to PGVector
    ↓
Frontend polls /ingest/status
    ↓
Complete: Collection ready for searching

Reference: OPERATIONS_REFERENCE.md - Operation 2
```

### Query Path
```
User types question
    ↓
POST /ask with (question, knowledge_base, ...)
    ↓
Backend: hybrid_search → filter → rerank
    ↓
Top 10 chunks + context
    ↓
Feed to LLM (medgemma:4b)
    ↓
Generate answer with source citations
    ↓
Save to database
    ↓
Return to frontend

Reference: OPERATIONS_REFERENCE.md - Operation 3
Duration: 5-20 seconds
```

---

## 🎓 Learning Path (Recommended)

### Day 1: Foundation (2-3 hours)
1. Read ARCHITECTURE_COMPLETE_GUIDE.md sections 1-3 (overview, tech stack)
2. Skim the architecture diagram in section 12
3. Watch backend start with `bash script.sh start`
4. Try uploading a PDF and asking a question
5. Read MENTAL_MODELS.md section 1-6 (models)

### Day 2: Deep Dive (2-3 hours)
1. Read ARCHITECTURE_COMPLETE_GUIDE.md sections 4-6 (data flows)
2. Read MENTAL_MODELS.md section "Question-Answer Loop (Detailed)"
3. Read OPERATIONS_REFERENCE.md Operation 3 in detail
4. Open backend/rag_pipeline.py and trace enhance_retrieve() function
5. Try modifying chunk_size in .env and re-ingest to see impact

### Day 3: Operations (1-2 hours)
1. Read OPERATIONS_REFERENCE.md all operations
2. Try each API endpoint manually with curl or Postman
3. Read MENTAL_MODELS.md section "Debugging Mental Model"
4. Intentionally break something and debug it using the tree

### Day 4: Advanced (2-3 hours)
1. Read ARCHITECTURE_COMPLETE_GUIDE.md sections 7-10 (advanced topics)
2. Read MENTAL_MODELS.md section "Performance Optimization Ladder"
3. Try disabling reranking: change use_reranking=False in app.py
4. Compare query performance and answer quality
5. Read repository memory files: /memories/repo/*.md

---

## 🔍 Code Navigation

### If you want to understand [X], look at:

**How PDFs are parsed**
→ `backend/parser.py` (uses Docling + PyPDF2)

**How chunks are created**
→ `backend/ingest.py` line X: `RecursiveCharacterTextSplitter`

**How vectors are generated**
→ `backend/rag_pipeline.py` line X: `get_embeddings()`

**How retrieval works**
→ `backend/rag_pipeline.py` function: `enhanced_retrieve()`

**How reranking works**
→ `backend/rag_pipeline.py` function: `rerank_documents()`

**How LLM is called**
→ `backend/rag_pipeline.py` function: `build_qa_chain()`

**How ingestion state is managed**
→ `backend/app.py` variables: `ingest_states`, `ingest_lock`

**How chat history is saved**
→ `backend/app.py` POST /ask endpoint: Saves Message records

**How frontend displays settings**
→ `frontend/src/App.jsx` line X: `refreshSettings()` function

**How frontend manages KB switching**
→ `frontend/src/App.jsx` line X: `setActiveKnowledgeBase()`

---

## 📋 Key Concepts Glossary

| Term | Definition | File |
|------|-----------|------|
| **Knowledge Base (KB)** | Isolated document collection in separate folder | MENTAL_MODELS.md - Model 2 |
| **Collection** | PGVector collection for a KB (e.g., medical_docs__diabetic_foot) | ARCHITECTURE_COMPLETE_GUIDE.md - Section 5.2 |
| **Chunk** | Text segment from document (typically 1024 chars) | ARCHITECTURE_COMPLETE_GUIDE.md - Section 4.1 |
| **Embedding** | 384-dimensional vector representing text semantically | MENTAL_MODELS.md - Stage 1 |
| **Hybrid Search** | Combining semantic (vector) + keyword (BM25) search | MENTAL_MODELS.md - Model 5 |
| **Reranking** | Re-scoring retrieved results using cross-encoder model | MENTAL_MODELS.md - Model 6 |
| **Metadata** | Invisible tags on chunks (source, kb, page, etc.) | MENTAL_MODELS.md - Model 4 |
| **Similarity Threshold** | Minimum score to include a result (default 0.5) | ARCHITECTURE_COMPLETE_GUIDE.md - Section 5.1 |
| **Context Window** | Total tokens available to LLM (8192) | MENTAL_MODELS.md - Stage 4 |
| **Temperature** | LLM randomness (0=deterministic, 1.0=random) | ARCHITECTURE_COMPLETE_GUIDE.md - Section 14 |

---

## ❓ FAQ

**Q: Where does configuration come from?**  
A: Three levels - See ARCHITECTURE_COMPLETE_GUIDE.md Section 10

**Q: Can I use a different LLM?**  
A: Yes - change LLM_PROVIDER and LLM_MODEL in .env

**Q: Why are knowledge bases isolated?**  
A: Prevents cross-document contamination - MENTAL_MODELS.md Model 2

**Q: What if retrieval gets no results?**  
A: LLM generates fallback answer - OPERATIONS_REFERENCE.md Scenario 4

**Q: How long does ingestion take?**  
A: ~2-3 chunks/second - ARCHITECTURE_COMPLETE_GUIDE.md Performance section

**Q: Can I have multiple conversations?**  
A: Yes, per knowledge base - ARCHITECTURE_COMPLETE_GUIDE.md Section 6

**Q: What if the reranker fails?**  
A: System uses original scores - ARCHITECTURE_COMPLETE_GUIDE.md Section 9

**Q: How do I scale this?**  
A: Growth path in MENTAL_MODELS.md section "Growth Path"

---

## 🎯 Next Steps

### Option 1: Continue Learning
→ Read any document that interests you  
→ Start with questions from FAQ above

### Option 2: Hands-On Experimentation  
→ Run `bash script.sh start`  
→ Upload test documents  
→ Ask questions and observe responses  
→ Check backend logs: `tail -f .run-logs/backend.log`

### Option 3: Code-Focused Learning
→ Open `backend/rag_pipeline.py`  
→ Find `enhanced_retrieve()` function  
→ Read comments and trace execution  
→ Match to OPERATIONS_REFERENCE.md Operation 3

### Option 4: Modify & Test
→ Pending tasks from earlier:
   1. Re-ingest documents (adds metadata)
   2. Run diagnostic tests
   3. Tune performance parameters

---

## 📍 Location of Resources

All documentation is in `/home/ashok/Desktop/RAGSYSTEM/`:

```
/ARCHITECTURE_COMPLETE_GUIDE.md  (You opened this section)
/MENTAL_MODELS.md
/OPERATIONS_REFERENCE.md
/ARCHITECTURE_AND_RUNBOOK.md    (Original)
/README.md                       (Quick start)

Memory Notes (for future sessions):
/memories/repo/chat-history-implementation.md
/memories/repo/retrieval-improvements-apr27.md
/memories/repo/rag-ingest-notes.md

Full System:
medical-rag/
├── backend/
│   ├── app.py               (HTTP endpoints)
│   ├── rag_pipeline.py      (Retrieval logic)
│   ├── ingest.py            (Document processing)
│   └── database.py          (Chat models)
├── frontend/
│   └── src/App.jsx          (React UI)
└── .env                     (Configuration)
```

---

## ✅ Checklist: "I Understand RAG" Test

If you can answer these, you understand the system:

- [ ] Draw the document lifecycle: Upload → Parse → Chunk → Embed → Store
- [ ] Explain why knowledge bases are isolated
- [ ] Describe hybrid search: semantic + keyword
- [ ] Explain what reranking does and why it's useful
- [ ] Draw the retrieval funnel: 1000 chunks → 10 top results
- [ ] Describe the three data sources: FS, DB, Frontend memory
- [ ] Explain metadata tags and why they matter
- [ ] Trace a question from frontend to LLM and back
- [ ] Name the three configuration levels
- [ ] List 5 recovery scenarios (graceful degradation)

If you can do all 10, you're ready to modify the system confidently!

---

**Happy Learning! 🚀**

Questions? Start with the appropriate guide above, then trace through the code in backend/.

