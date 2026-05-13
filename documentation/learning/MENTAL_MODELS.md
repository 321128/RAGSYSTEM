# Medical RAG - Mental Models & Concepts

## Core Mental Models

### Model 1: The Document Lifecycle

Think of documents like this:

```
[Raw PDF Files]
     ↓ (Parse & Split)
 [Text Chunks]
     ↓ (Embed)
[Vector + Metadata]
     ↓ (Store)
[Collection in DB]
     ↓ (Query)
[Retrieved Chunks]
     ↓ (Rank)
[Top Relevant Chunks]
     ↓ (To LLM)
[Generated Answer]
```

**Key Point**: A document doesn't "exist" in the system until it's been vectorized and stored. Uploading is just preparation.

---

### Model 2: The Knowledge Base as an Island

Each knowledge base is **isolated from others**:

```
┌─────────────────┬─────────────────┬─────────────────┐
│  Default KB     │ Diabetic Foot   │  Surgery        │
│                 │                 │                 │
│  - PDFs in dir  │ - PDFs in dir   │ - PDFs in dir   │
│  - Collection:  │ - Collection:   │ - Collection:   │
│    medical_docs │   med_docs__df  │   med_docs__surg│
│  - 0 chunks     │ - 245 chunks    │ - 1200 chunks   │
│                 │                 │                 │
│  When queried:  │ When queried:   │ When queried:   │
│  - Only search  │ - Only search   │ - Only search   │
│    this coll.   │   this coll.    │   this coll.    │
│  - Can't see    │ - Can't see     │ - Can't see     │
│    other KBs    │   other KBs     │   other KBs     │
└─────────────────┴─────────────────┴─────────────────┘
```

**Key Point**: This prevents "cross-document contamination" where answers mix information from unrelated docs.

---

### Model 3: The Retrieval Process as a Funnel

```
               [1000 chunks in collection]
                          ↓
                [Semantic + BM25 Search]
                    (Returns all matches)
                          ↓
              [Filter by Similarity >= 0.5]
                (Keeps 50 good matches)
                          ↓
                    [Other Filters]
              (Metadata, knowledge_base check)
                (Now 40 candidates)
                          ↓
              [Cross-Encoder Reranking]
               (Score each candidate)
             (Add uncertainty ordering)
                          ↓
                  [Take Top 10]
              (Most relevant chunks)
                          ↓
                 [Build Context]
             (Format for LLM)
                          ↓
                  [Send to LLM]
```

**Key Point**: Each stage filters and ranks. The result is NOT just "most similar" but "most relevant & credible".

---

### Model 4: The Metadata Tag System

Every chunk has invisible tags:

```
Chunk Text:
"Diabetic foot complications include ulcers, infections..."

Attached Metadata (invisible but searchable):
├─ source: "complications.pdf"
├─ page: 2
├─ knowledge_base: "diabetic_foot"
├─ chunk_index: 5
└─ created_at: 2026-05-13T10:35:00Z

When you query:
┌────────────────────────────────────────┐
│ "Show me chunks from diabetic_foot KB" │
└────────────────────────────────────────┘
         ↓
    System checks metadata
         ↓
Filter → knowledge_base == "diabetic_foot" ✓
  Only these chunks returned
```

**Key Point**: Metadata is what enables knowledge base isolation. Without it, you get contamination.

---

### Model 5: Hybrid Search as "Two Searches"

```
Query: "What causes diabetic foot pain?"

Search 1 - Semantic (Vector Similarity):
├─ Convert query to 384-dim vector
├─ Search pgvector for similar vectors
│  (Good for: synonyms, related concepts)
└─ Score: 0.92 "Nerve damage causes pain in..."
          0.85 "Infection leads to pain and..."
          0.78 "Loss of sensation prevents..."

Search 2 - BM25 (Keyword Matching):
├─ Split query into keywords: diabetic, foot, pain
├─ Find chunks with these keywords
│  (Good for: exact matches, specific terms)
└─ Score: 0.95 "Diabetic foot pain can be..."
          0.87 "Foot pain from diabetic neuropathy..."
          0.71 "The diabetic complication..."

Combined Result:
├─ Keep all matches from both searches
├─ Sort by combined score
└─ Return top 30 (before reranking)
    Result: More comprehensive coverage
```

**Key Point**: Hybrid catches what pure semantic or pure keyword alone would miss.

---

### Model 6: The Reranker as a "Quality Inspector"

```
Top 30 Retrieved Chunks
└─→ Cross-Encoder Reranker
    └─→ "For each chunk, how good is it for THIS query?"
    
    Chunk A: "Pain from nerve damage"
    Query: "What causes pain?"
    Reranker score: 0.95 ✓ Excellent match
    
    Chunk B: "History of diabetic foot research"
    Query: "What causes pain?"
    Reranker score: 0.45 ✗ Weak match
    
    Chunk C: "Vascular complications"
    Query: "What causes pain?"
    Reranker score: 0.72 ✓ Good match
    
    Final Ranking:
    1. Chunk A (0.95)
    2. Chunk C (0.72)
    3. Chunk B (0.45)
    
Take Top 10 → Send to LLM
```

**Key Point**: Reranking is expensive but dramatically improves answer quality.

---

## Architecture Principles

### Principle 1: Separation of Concerns

Each layer handles ONE responsibility:

```
Frontend:     Display & User Interaction
              (Don't touch RAG logic)
                    ↓
Backend API:  HTTP Routes & State Management
              (Don't do inference)
                    ↓
RAG Pipeline: Retrieval & Chain Building
              (Don't manage HTTP)
                    ↓
Database:     Data Storage
              (Don't do inference)
                    ↓
Embeddings:   Vector Generation
              (Don't handle PDFs)
                    ↓
LLM:          Text Generation
              (Don't manage DBs)
```

**Benefit**: Each can be replaced independently. Want OpenAI instead of Ollama? Just change the LLM layer.

---

### Principle 2: Thread Safety with Background Workers

```
Request comes in for /ask
         ↓
Main thread handles HTTP
         ↓
Spawns background worker (ThreadPoolExecutor)
         ↓
Worker: retrieves, ranks, calls LLM
         ↓
Main thread returns immediately
         ↓
HTTP response sent to frontend
         ↓
Worker completes in background
         ↓
Result available when/if frontend polls
```

**Benefit**: Frontend never hangs waiting for LLM. Slow operations happen invisibly.

---

### Principle 3: Graceful Degradation

```
Ideal Scenario:
Request → Hybrid Search + Reranking + LLM → Perfect Answer

Degradation 1 (BM25 unavailable):
Request → Semantic Search Only + Reranking + LLM → Good Answer

Degradation 2 (Reranking fails):
Request → Hybrid Search + Original Scores + LLM → Decent Answer

Degradation 3 (Reranking + BM25 fail):
Request → Semantic Search + Original Scores + LLM → Acceptable Answer

Key: System never crashes. Always delivers something.
```

**Benefit**: More forgiving of environment issues, easier debugging.

---

## Data Consistency Model

### The Three Data Sources

```
1. File System (Source of Truth for PDFs)
   documents/
   ├── default/
   ├── diabetic_foot/    ← PDFs live here
   └── surgery/
   
2. PostgreSQL (Source of Truth for Vectors)
   langchain_pg_embedding    ← Vectors, chunks, metadata
   conversations             ← Chat history
   messages                  ← Individual messages
   
3. Frontend Memory (Temporary State)
   React useState             ← Conversations list
   useEffect                  ← Polling status
```

**Sync Rules**:
```
FS Upload → Backend sees files → Ingestion starts
                                        ↓
                            Vectors generated
                                        ↓
                            DB updated
                                        ↓
                            Frontend polls /status
                                        ↓
                            Frontend updates UI

Delete KB → Backend removes FS files
                                        ↓
                            Backend removes DB records
                                        ↓
                            Frontend polls /kb-list
                                        ↓
                            Frontend removes from UI
```

**Key Point**: File system is primary for PDFs. DB is primary for processing results.

---

## The Question-Answer Loop (Detailed)

### Stage 1: Embedding Phase (Ingestion)

```
Raw Text: "Diabetic foot complications include ulcers..."
     ↓
Token Analysis: [diabetic][foot][complications]...[ulcers]...
     ↓
Embedding Model:
Input:  31 tokens
Transform: BAAI/bge-small-en neural network
Output: 384-dimensional vector
        [0.23, -0.15, 0.89, ..., -0.34]
                (384 numbers)
     ↓
Store in PGVector:
embedding_vector: [0.23, -0.15, ..., -0.34]
document_text: "Diabetic foot complications..."
metadata: {source: "...", knowledge_base: "...", ...}
     ↓
Now this chunk is searchable by vector similarity
```

### Stage 2: Query Embedding (Same Process)

```
User Query: "What causes diabetic foot pain?"
     ↓
Token Analysis: [what][causes][diabetic]...[pain]?
     ↓
Embedding Model: (same model, same process)
Input:  6 tokens (shorter than document)
Output: 384-dimensional vector
        [0.21, -0.14, 0.91, ..., -0.33]
     ↓
Now both query and documents are in same vector space
```

### Stage 3: Vector Similarity Search

```
Query Vector:    [0.21, -0.14, 0.91, ..., -0.33]

Compare to Document Vectors:
Doc1:  [0.23, -0.15, 0.89, ..., -0.34]  → Similarity: 0.94 ✓
Doc2:  [0.05,  0.02, 0.10, ...,  0.01]  → Similarity: 0.23 ✗
Doc3:  [0.20, -0.13, 0.90, ..., -0.32]  → Similarity: 0.92 ✓
Doc4:  [-0.81,  0.99, -0.02,...,  0.88] → Similarity: 0.12 ✗

Rank by similarity and return top matches
```

### Stage 4: LLM Context Window

```
LLM Context Window: 8192 tokens available

Distribution:
├─ System Message: 150 tokens
│  "You are a medical assistant..."
├─ Retrieved Context: 4000 tokens
│  (Top 10 chunks: ~400 tokens each)
├─ User Question: 20 tokens
│  "What causes diabetic foot pain?"
├─ Instruction: 50 tokens
│  "Answer using ONLY the context..."
└─ Generation Space: 3782 tokens
   (Room for answer generation)
```

### Stage 5: LLM Generation

```
Prompt (8192 tokens):
"You are a medical assistant...
 
 Context: [Top 10 chunks about diabetic pain]
 
 Question: What causes diabetic foot pain?
 
Answer:"

Model (medgemma:4b) generates:
"Diabetic foot pain causes include:

1. Neuropathy (nerve damage)
   - Hyperglycemia damages blood vessels
   - Results in reduced sensation initially
   - Then progression to painful neuropathy

2. Vascular insufficiency
   - Poor circulation from vessel damage
   - Reduced oxygen to tissues
   - Causes cramping and pain

According to the source documents,
neuropathy is the most common cause..."

Token count: 150 tokens (out of 2048 max)
```

---

## Quality Metrics to Understand

### Retrieval Quality Metrics

| Metric | What It Means | Good Value |
|--------|--------------|-----------|
| **Mean Reciprocal Rank (MRR)** | How high is the correct answer ranked? | > 0.8 (in top 1-2) |
| **Normalized Discounted Cumulative Gain (NDCG)** | Are top results relevant? | > 0.7 |
| **Precision@K** | Of top K results, what % are relevant? | > 0.8 for K=10 |
| **Recall** | Of all relevant docs, what % did we find? | > 0.9 |

**Your System's Approach**:
```
hybrid_search + reranking targets high MRR and Precision
(Fewer results, but higher quality)

vs.

Just semantic search targets high Recall
(More results, but some low-quality)
```

### Model Quality Metrics

| Metric | What It Means | Your LLM |
|--------|--------------|----------|
| **Factuality** | Does answer match source? | medgemma optimized for this |
| **Hallucination Rate** | Does it make stuff up? | Lower with temp=0 |
| **Coherence** | Is answer well-structured? | Usually good |
| **Latency** | How fast is generation? | 5-15s (acceptable) |

---

## Common Misconceptions

### Misconception 1: "Vectorization = Understanding"

**False**: Vectors capture statistical patterns, not true comprehension.

```
Query: "What is a diabetic foot?"

Semantic Vector: [0.23, -0.15, 0.89, ...]
  ↓
Captures: Frequency patterns, word co-occurrence
  ↓
DOES NOT capture: True medical knowledge

LLM Generation: ACTUALLY provides understanding
  ↓
Combines: Retrieved vectors + trained medical knowledge
  ↓
Result: Coherent medical explanation
```

---

### Misconception 2: "Reranking Gets the Absolute Best Chunks"

**False**: Reranking improves relative ordering, not absolute truth.

```
Reranker scores:
Chunk A: 0.92 "Relevant"
Chunk B: 0.87 "Relevant"
Chunk C: 0.76 "Somewhat relevant"

Reranker correctly says: A > B > C

BUT: If the "truly best" chunk is ranked 50th by retrieval,
reranker only works with what it's given.
```

**Fix**: Improve retrieval FIRST (hybrid search helps).

---

### Misconception 3: "More Chunks Always Better"

**False**: More can introduce noise.

```
K=5: Answer from 5 high-quality chunks → Focused, clear
K=50: Answer from 5 good + 45 mediocre chunks → Diluted
```

**Trade-off**: Higher K catches more relevant info but adds noise.
Your system uses K=10 (sweet spot).

---

### Misconception 4: "LLM Temperature=0 = Perfect Answers"

**False**: Temperature=0 means deterministic, not correct.

```
Temperature=0:
├─ Same input → Always same output
├─ Good for: Consistency, no hallucination variability
└─ Risk: Can get "stuck" on plausible wrong answer

Temperature=0.7 (Typical):
├─ Same input → Different outputs
├─ Good for: Exploring different valid answers
└─ Risk: More variability, potential hallucinations
```

Your system (temp=0) prioritizes reliability over creativity. Good for medical context.

---

## Debugging Mental Model

When something goes wrong, think through this tree:

```
User says: "I get wrong answers"
         ↓
Is the question in a KB with documents?
├─ No → Upload docs and ingest
│
└─ Yes ↓
Document is relevant to question?
├─ No → Check KB selection, upload right docs
│
└─ Yes ↓
Does retrieval get the document?
├─ No → Hybrid search failing?
│       Try: use_hybrid_search=true
│       Check: Chunk size, embeddings
│
└─ Yes ↓
Is retrieval result ranked high?
├─ No → Reranking failing?
│       Try: Check reranker logs
│       Check: Similarity threshold
│
└─ Yes ↓
Does LLM ignore the context?
├─ Yes → LLM issue
│        Try: Adjust prompt template
│        Try: Lower temperature
│        Try: Different LLM model
│
└─ No → Other issue
        Check: Network, timeouts
```

---

## Performance Optimization Ladder

If your system is slow, try in this order:

```
Level 1: Easy, No Quality Loss
├─ Reduce K from 10 to 5 chunks
├─ Disable reranking (saves 1-2 seconds)
└─ Reduce chunk_overlap from 200 to 50

Level 2: Moderate Quality Loss
├─ Increase similarity_threshold from 0.5 to 0.7
├─ Use semantic search only (disable BM25)
└─ Smaller LLM model

Level 3: Significant Quality Loss
├─ Reduce chunk_size from 1024 to 512
├─ Use cheaper embeddings
└─ Higher LLM temperature (more random)

Level 4: Nuclear Option
└─ Use OpenAI (outsource inference, higher latency but better quality)
```

Default config aims for balance: Fast enough + Quality.

---

## Growth Path

As your system evolves:

```
Phase 1 (Now): Single server, ~5-10 KBs max
├─ File system storage
├─ Local PostgreSQL
└─ Local Ollama

Phase 2: Multiple documents per KB
├─ Implement hierarchical metadata (topic tags)
├─ Add hybrid search tuning
└─ Monitor query latency

Phase 3: Production scale
├─ Migrate to cloud PostgreSQL
├─ Use external embedding service
├─ Implement caching layer (Redis)
├─ Add query analytics

Phase 4: Advanced RAG
├─ Fine-tune embeddings on medical data
├─ Implement query expansion
├─ Add multi-turn reasoning
└─ Implement citation tracking

Phase 5: Enterprise
├─ Multi-tenant architecture
├─ Role-based access control
├─ Audit logs
└─ Compliance (HIPAA, etc.)
```

---

## Key Takeaways

1. **RAG = Retrieval + Generation**: Good retrieval is 80% of the battle
2. **Metadata is Power**: Enables isolation, filtering, quality control
3. **Graceful Degradation**: System works even if parts fail
4. **Context is King**: What you feed the LLM determines answer quality
5. **Vector Space = Language Space**: Similar vectors = similar meaning
6. **Reranking ≠ Magic**: It improves what it's given, not finding new stuff
7. **Temperature Matters**: For medicine, deterministic (0) > creative (0.7)
8. **Knowledge Bases are Silos**: Intentional, prevents contamination
9. **Metadata tags are invisible**: But they enable powerful filtering
10. **Everything is a tradeoff**: Speed vs accuracy, cost vs quality, etc.

