# 03 · MongoDB Vector Search + Agentic Adaptive RAG — DroneFleet

> **Cross-references**: schema definitions in [`02-mongodb-data-model.md`](./02-mongodb-data-model.md); seed scripts that produce the corpus in [`09-seed-and-data.md`](./09-seed-and-data.md).

This file specifies the **adaptive, agentic retrieval system** that powers DroneFleet's planner, replanner, regulation reasoner, and reflection loop. It is built around **Voyage AI** embeddings + reranker, **MongoDB Atlas Vector Search** + Atlas Search, and a self-improving **`RetrievalLearner`** that tunes itself nightly from outcome feedback.

The user's brief: *"Experiment modifying query approaches, altering chunking, reordering results based on input. How can you create an agentic and adaptive retrieval system that improves over time and performs reasoning across various documents and sources?"* — every section below executes against that brief.

---

## 0 · Dependencies

```bash
uv add motor pymongo[srv] voyageai langchain-voyageai langchain-mongodb \
       langchain-core langchain-community langgraph tiktoken numpy scikit-learn
```

`.env`:

```
VOYAGE_API_KEY=...
MONGODB_URI=mongodb+srv://...
OPENAI_API_KEY=...   # for query rewriter + critic
```

```python
# rag/clients.py
import os, voyageai
from motor.motor_asyncio import AsyncIOMotorClient
from langchain_voyageai import VoyageAIEmbeddings, VoyageAIRerank

voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

EMBED_MODEL_PRIMARY  = "voyage-3-large"        # 1024-dim, cosine
EMBED_MODEL_FAST     = "voyage-3"              # 1024-dim, supports Matryoshka 256/512 truncation
EMBED_MODEL_CONTEXT  = "voyage-context-3"      # contextualised chunk embedding
RERANK_MODEL         = "rerank-2.5"

embeddings_primary = VoyageAIEmbeddings(
    voyage_api_key=os.environ["VOYAGE_API_KEY"],
    model=EMBED_MODEL_PRIMARY,
    output_dimension=1024,                      # full-rank
    truncation=True,
)

embeddings_fast_short = VoyageAIEmbeddings(
    voyage_api_key=os.environ["VOYAGE_API_KEY"],
    model=EMBED_MODEL_FAST,
    output_dimension=256,                       # Matryoshka — for hot tier
    truncation=True,
)

reranker = VoyageAIRerank(
    voyage_api_key=os.environ["VOYAGE_API_KEY"],
    model=RERANK_MODEL,
    top_k=5,
)

mongo = AsyncIOMotorClient(os.environ["MONGODB_URI"])
db    = mongo["dronefleet"]
```

We default to `voyage-3-large` for write-side embeddings (best quality), use `voyage-3` @ 256-dim for very-hot reads (operator preferences), and reach for `voyage-context-3` when chunking long, hierarchical documents (regulations, ops manuals) so each chunk's embedding is *contextualised by the surrounding document* — the late-chunking strategy in §2.4.

> **Per-collection embedding policy**: see §2.5 table. The policy is enforced at write time by `Embedder.embed_for(collection, text)` so retrievers and writers cannot drift apart.

---

## 1 · Voyage AI integration — write side

```python
# rag/embedder.py
from typing import Iterable
from .clients import voyage, EMBED_MODEL_PRIMARY, EMBED_MODEL_FAST, EMBED_MODEL_CONTEXT

class Embedder:
    """Single source of truth for model selection per collection."""
    POLICY = {
        "mission_memory":      ("voyage-3-large", 1024, "document"),
        "document_chunks":     ("voyage-3-large", 1024, "document"),
        "agent_skills":        ("voyage-3-large", 1024, "document"),
        "operator_pref_hot":   ("voyage-3",        256, "document"),
        "regulations_chunks":  ("voyage-context-3",1024, "document"),  # late chunking
    }

    @classmethod
    async def embed_for(cls, collection_kind: str, texts: list[str]) -> tuple[list[list[float]], str]:
        model, dim, input_type = cls.POLICY[collection_kind]
        if model == "voyage-context-3":
            # voyage-context-3 takes the *whole document* + chunk boundaries.
            raise RuntimeError("Use embed_context() for late chunking")
        result = voyage.embed(
            texts=texts,
            model=model,
            input_type=input_type,
            output_dimension=dim,
            truncation=True,
        )
        return result.embeddings, model

    @classmethod
    async def embed_query(cls, query: str, model: str | None = None, dim: int | None = None) -> list[float]:
        m = model or "voyage-3-large"
        d = dim or 1024
        r = voyage.embed(texts=[query], model=m, input_type="query",
                         output_dimension=d, truncation=True)
        return r.embeddings[0]

    @classmethod
    async def embed_context(cls, document_text: str, chunks: list[str]) -> list[list[float]]:
        """Late chunking with voyage-context-3 — embeddings see the full doc."""
        r = voyage.contextualized_embed(
            inputs=[{"text": document_text, "chunks": chunks}],
            model=EMBED_MODEL_CONTEXT,
        )
        return r.results[0].embeddings
```

Reranker wrapper:

```python
# rag/reranker.py
from .clients import voyage, RERANK_MODEL

async def voyage_rerank(query: str, documents: list[str], top_k: int = 5) -> list[dict]:
    r = voyage.rerank(query=query, documents=documents, model=RERANK_MODEL, top_k=top_k)
    return [
        {"index": x.index, "document": x.document, "relevance_score": x.relevance_score}
        for x in r.results
    ]
```

---

## 2 · Chunking experiments

The user asked us to *experiment* with chunking. We implement four strategies, persist `chunk_strategy` on every chunk (see schema in [`02-mongodb-data-model.md`](./02-mongodb-data-model.md) §21), and pick per-collection in §2.5.

### 2.1 Fixed 512-token

**Pros**: dirt-simple, predictable token budgets, fast to embed in batches.
**Cons**: cuts mid-sentence, destroys structure for hierarchical docs.
**Use when**: chunks are already short and uniform (`mission_memory` reflections — typically < 400 tokens already), or for the recall baseline in eval.

```python
# rag/chunkers/fixed.py
import tiktoken
ENC = tiktoken.get_encoding("cl100k_base")

def chunk_fixed(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    ids = ENC.encode(text)
    out = []
    i = 0
    while i < len(ids):
        window = ids[i : i + max_tokens]
        out.append(ENC.decode(window))
        i += max_tokens - overlap
    return out
```

### 2.2 Recursive markdown-aware

**Pros**: respects `# ## ###` boundaries — perfect for regulations and SOPs that are inherently hierarchical.
**Cons**: variable chunk sizes, occasional very small leaves.
**Use when**: source is markdown / documented prose with clear headings (`regulations`, `operator manuals`).

```python
# rag/chunkers/markdown.py
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]

def chunk_markdown(text: str, target_tokens: int = 480) -> list[dict]:
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS)
    sections = header_splitter.split_text(text)
    char_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=target_tokens,
        chunk_overlap=48,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    out = []
    for s in sections:
        for piece in char_splitter.split_text(s.page_content):
            out.append({"text": piece, "headings": s.metadata})
    return out
```

### 2.3 Semantic (embedding-similarity threshold)

**Pros**: chunks coalesce around topic shifts, not arbitrary token counts. Great for long facility-intel notes that contain multiple topics.
**Cons**: O(n²) similarity work; needs an embedding budget at chunk time.
**Use when**: source is loose, narrative text without clear structure (`facility_intel` notes from operators, after-action reports).

```python
# rag/chunkers/semantic.py
import numpy as np
from .clients import voyage

def chunk_semantic(text: str, *, breakpoint_pct: float = 90.0,
                   sentence_split=lambda t: [s.strip() for s in t.split(". ") if s.strip()]) -> list[str]:
    sents = sentence_split(text)
    if len(sents) < 4:
        return [text]
    emb = np.array(voyage.embed(texts=sents, model="voyage-3", input_type="document",
                                output_dimension=256, truncation=True).embeddings)
    # Cosine distance between consecutive sentences
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    unit = emb / np.clip(norms, 1e-9, None)
    dists = 1.0 - np.einsum("ij,ij->i", unit[:-1], unit[1:])
    threshold = np.percentile(dists, breakpoint_pct)
    out, buf = [], [sents[0]]
    for i, d in enumerate(dists):
        if d > threshold:
            out.append(". ".join(buf))
            buf = []
        buf.append(sents[i + 1])
    if buf:
        out.append(". ".join(buf))
    return out
```

### 2.4 Late chunking with `voyage-context-3`

**Pros**: each chunk's embedding is conditioned on the *whole document*, so cross-references survive ("§4.2 above" still resolves). Best NDCG in our eval.
**Cons**: slower (one call per document), bounded by Voyage's context length per doc.
**Use when**: the corpus is interconnected and reference-heavy (UK CAA full text, EASA Open A1/A2/A3, FAA Part 107).

```python
# rag/chunkers/late.py
from .embedder import Embedder
from .markdown import chunk_markdown

async def chunk_late_context(document_text: str) -> list[dict]:
    sections = chunk_markdown(document_text, target_tokens=480)
    chunk_texts = [s["text"] for s in sections]
    embeddings  = await Embedder.embed_context(document_text, chunk_texts)
    return [
        {"text": s["text"], "embedding": e, "metadata": {"headings": s["headings"]}}
        for s, e in zip(sections, embeddings)
    ]
```

### 2.5 Per-collection chunking policy

| Source kind | Strategy | Rationale |
|---|---|---|
| `regulations` (CAA, FAA, EASA) | **`late_context`** | Heavy cross-referencing — late chunking preserves "see §x" semantics |
| `documents` (operator manuals) | `markdown_recursive` | Clear heading hierarchy |
| `facility_intel` notes | `semantic` | Free-form, multi-topic |
| `mission_memory` reflections | `fixed_512` | Already short and self-contained |
| `agent_skills.capability_text` | none (single embedding per skill) | One paragraph per skill |

Stored on the chunk as `chunk_strategy` (see schema), so the **`RetrievalLearner`** can A/B strategies and swap policy if eval moves.

---

## 3 · Atlas Vector Search index design

We declared three vector indexes in [`02-mongodb-data-model.md`](./02-mongodb-data-model.md) §Vector Search definitions: `mission_memory_vec`, `document_chunks_vec`, `agent_skills_vec`. Two practical notes:

- **Filter fields**: every field that ever appears in a `$vectorSearch.filter` MUST be declared in the index definition. We chose `kind`, `metadata.region`, `metadata.weather_class`, `metadata.success`, `embedding_model` for `mission_memory_vec` (those are the planner's natural slicers).
- **`numCandidates` rule of thumb**: `numCandidates = max(150, 10 × k)`. For typical `k=10` use 200; for `k=50` use 500. Higher candidates → higher recall, more cost. Tuned per query class by `RetrievalLearner` (§7).
- **HNSW**: Atlas Vector Search uses HNSW under the hood. We don't tune `m` / `efConstruction` directly — Atlas manages it — but we control quality at query time via `numCandidates`.

Canonical query helper:

```python
# rag/vector.py
from typing import Any
from .clients import db
from .embedder import Embedder

async def vector_search(
    *, collection: str, index: str, query_vec: list[float],
    k: int = 10, num_candidates: int | None = None,
    filters: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> list[dict]:
    nc = num_candidates or max(150, 10 * k)
    stage: dict[str, Any] = {
        "$vectorSearch": {
            "index": index, "path": "embedding",
            "queryVector": query_vec, "numCandidates": nc, "limit": k,
        }
    }
    if filters:
        stage["$vectorSearch"]["filter"] = filters

    pipeline = [
        stage,
        {"$set": {"_score": {"$meta": "vectorSearchScore"}}},
    ]
    if project:
        pipeline.append({"$project": project})

    return [doc async for doc in db[collection].aggregate(pipeline)]
```

Atlas Search hybrid partner (BM25):

```python
# rag/text.py
async def text_search(
    *, collection: str, index: str, query: str,
    k: int = 30, filters: dict | None = None,
) -> list[dict]:
    must: list[dict] = [
        {"text": {"query": query, "path": ["text", "title", "content", "name"]}}
    ]
    if filters:
        must.extend({"equals": {"path": p, "value": v}} for p, v in filters.items())
    pipeline = [
        {"$search": {"index": index, "compound": {"must": must}}},
        {"$set": {"_score": {"$meta": "searchScore"}}},
        {"$limit": k},
    ]
    return [doc async for doc in db[collection].aggregate(pipeline)]
```

---

## 4 · Adaptive Retrieval Pipeline (the agentic loop)

The pipeline is itself an agent that *decides* how to retrieve. It's a 7-stage loop:

```
operator_query
   │
   ▼
(1) QueryRewriter         ─►  3 sub-queries: literal · semantic · HyDE
   │
   ▼
(2) Multi-query $vectorSearch  ─►  asyncio.gather over sub-queries × collections
   │
   ▼
(3) Hybrid fusion (RRF, k=60)  ─►  combine vector hits with Atlas Search BM25
   │
   ▼
(4) Voyage rerank-2.5          ─►  top-30 → top-5
   │
   ▼
(5) Contextual compression     ─►  fit token budget
   │
   ▼
(6) RetrievalCriticAgent       ─►  did this answer the query?  if no → loop ≤3
   │                              (expand radius, drop filters, web fallback)
   ▼
(7) Cite + persist             ─►  context_doc_ids → agent_messages
```

### 4.1 Query rewriter (HyDE + literal + semantic)

```python
# rag/rewrite.py
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a query-rewriting assistant for a medical-drone planner. "
     "Given the operator's query, output exactly three reformulations as JSON: "
     "{{\"literal\": \"…\", \"semantic\": \"…\", \"hyde\": \"…\"}}. "
     "literal: the keyword-y, lookup-friendly form. "
     "semantic: a paraphrase capturing intent. "
     "hyde: a hypothetical, complete answer paragraph (HyDE) the system might retrieve."),
    ("user", "{query}")
])

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def rewrite(query: str) -> dict[str, str]:
    chain = REWRITE_PROMPT | llm
    resp = await chain.ainvoke({"query": query})
    import json
    return json.loads(resp.content)
```

### 4.2 Multi-query parallel `$vectorSearch`

```python
# rag/multiquery.py
import asyncio
from .embedder import Embedder
from .vector import vector_search

async def multi_vector_search(
    *, sub_queries: dict[str, str],
    collections: list[tuple[str, str]],   # [(collection_name, vector_index_name), ...]
    filters: dict | None = None,
    k_per: int = 15,
) -> dict[str, list[dict]]:
    """
    Returns {sub_query_key: [hits...]}, hits already deduped per sub-query.
    """
    embeddings = await asyncio.gather(*[
        Embedder.embed_query(q) for q in sub_queries.values()
    ])

    tasks = []
    keys = []
    for (sq_key, _q), vec in zip(sub_queries.items(), embeddings):
        for coll, idx in collections:
            tasks.append(vector_search(
                collection=coll, index=idx,
                query_vec=vec, k=k_per, filters=filters,
                project={"_id": 1, "text": 1, "title": 1, "kind": 1,
                         "metadata": 1, "_score": 1, "embedding_model": 1},
            ))
            keys.append((sq_key, coll))

    results = await asyncio.gather(*tasks)

    bucketed: dict[str, list[dict]] = {}
    for (sq_key, coll), hits in zip(keys, results):
        for h in hits:
            h["_collection"] = coll
        bucketed.setdefault(sq_key, []).extend(hits)
    return bucketed
```

### 4.3 Hybrid fusion (Reciprocal Rank Fusion)

```python
# rag/fusion.py
from collections import defaultdict

def rrf(rankings: list[list[dict]], *, k: int = 60, id_key: str = "_id") -> list[dict]:
    """Reciprocal Rank Fusion. rankings is a list of ranked result lists."""
    scores = defaultdict(float)
    by_id  = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            did = str(doc[id_key])
            scores[did] += 1.0 / (k + rank + 1)
            by_id[did] = doc
    fused = [(did, s) for did, s in scores.items()]
    fused.sort(key=lambda t: t[1], reverse=True)
    out = []
    for did, s in fused:
        d = by_id[did].copy()
        d["_rrf"] = s
        out.append(d)
    return out
```

Combine vector and BM25:

```python
# rag/hybrid.py
from .multiquery import multi_vector_search
from .text import text_search
from .fusion import rrf

async def hybrid_retrieve(*, sub_queries, collections, text_indexes,
                          filters=None, k=30) -> list[dict]:
    vec_buckets = await multi_vector_search(
        sub_queries=sub_queries, collections=collections,
        filters=filters, k_per=15,
    )
    bm25_lists = []
    for coll, idx in text_indexes:
        for q in sub_queries.values():
            bm25_lists.append(await text_search(collection=coll, index=idx, query=q, k=k))
    rankings = list(vec_buckets.values()) + bm25_lists
    return rrf(rankings)[:k]
```

### 4.4 Voyage `rerank-2.5` second pass

```python
# rag/pipeline.py (excerpt)
from .reranker import voyage_rerank

async def rerank_top(query: str, fused: list[dict], top_k: int = 5) -> list[dict]:
    docs = [d.get("text") or d.get("title") or "" for d in fused[:30]]
    rr = await voyage_rerank(query, docs, top_k=top_k)
    out = []
    for r in rr:
        d = fused[r["index"]].copy()
        d["_rerank_score"] = r["relevance_score"]
        out.append(d)
    return out
```

### 4.5 Contextual compression (fit the planner's token budget)

```python
# rag/compress.py
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

extractor = LLMChainExtractor.from_llm(ChatOpenAI(model="gpt-4o-mini", temperature=0))

async def compress(query: str, docs: list[dict], *, budget_tokens: int = 1800) -> list[dict]:
    lc_docs = [Document(page_content=d.get("text", ""), metadata={"id": str(d["_id"]),
                                                                  "kind": d.get("kind"),
                                                                  "collection": d.get("_collection")})
               for d in docs]
    compressed = await extractor.acompress_documents(lc_docs, query)
    out = []
    used = 0
    for cd in compressed:
        n = len(cd.page_content) // 4   # rough char→token
        if used + n > budget_tokens:
            break
        used += n
        out.append({**cd.metadata, "text": cd.page_content})
    return out
```

### 4.6 `RetrievalCriticAgent` — self-grading + adaptive expansion

```python
# rag/critic.py
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

CRITIC_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You judge whether a set of retrieved snippets actually answers the operator query. "
     "Respond JSON: {{\"answers\": true|false, \"missing\": [\"…\"], \"action\": "
     "\"accept\"|\"expand_radius\"|\"drop_filters\"|\"web_fallback\"}}."),
    ("user",
     "Query:\n{query}\n\nSnippets:\n{snippets}\n\nFilters used:\n{filters}")
])

critic_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def grade(query: str, snippets: list[dict], filters: dict | None) -> dict:
    chain = CRITIC_PROMPT | critic_llm
    resp = await chain.ainvoke({
        "query": query,
        "snippets": "\n---\n".join(s.get("text","")[:600] for s in snippets),
        "filters": json.dumps(filters or {}),
    })
    return json.loads(resp.content)
```

### 4.7 The full pipeline

```python
# rag/pipeline.py
import asyncio
from datetime import datetime, timezone
from .clients import db
from .rewrite import rewrite
from .hybrid import hybrid_retrieve
from .compress import compress
from .critic import grade

DEFAULT_VECTOR_TARGETS = [
    ("mission_memory",  "mission_memory_vec"),
    ("document_chunks", "document_chunks_vec"),
]
DEFAULT_TEXT_TARGETS = [
    ("document_chunks", "document_chunks_search"),
    ("facilities",      "facilities_search"),
]

async def adaptive_retrieve(
    query: str, *,
    filters: dict | None = None,
    max_loops: int = 3,
    trace_id: str | None = None,
    mission_id: str | None = None,
) -> dict:
    sub_queries = await rewrite(query)
    used_filters = dict(filters or {})
    plan: list[dict] = []
    final: list[dict] = []

    for loop in range(max_loops):
        fused = await hybrid_retrieve(
            sub_queries=sub_queries,
            collections=DEFAULT_VECTOR_TARGETS,
            text_indexes=DEFAULT_TEXT_TARGETS,
            filters=used_filters or None,
            k=30,
        )
        top = await rerank_top(query, fused, top_k=5)
        compressed = await compress(query, top, budget_tokens=1800)
        verdict = await grade(query, compressed, used_filters)
        plan.append({"loop": loop, "verdict": verdict, "n_hits": len(top)})

        if verdict.get("answers") or verdict.get("action") == "accept":
            final = compressed
            break

        action = verdict.get("action")
        if action == "expand_radius":
            for coll_idx in DEFAULT_VECTOR_TARGETS:
                pass   # bumped by passing larger k_per — see §7 RetrievalLearner
        elif action == "drop_filters":
            used_filters = {}                       # widen — semantic-only
        elif action == "web_fallback":
            from .web import duckduckgo_search
            web_hits = await duckduckgo_search(query, k=5)
            compressed.extend(web_hits)
            final = compressed
            break
        else:
            final = compressed
            break

    # 7. Persist citations
    context_doc_ids = [f"{c.get('collection','?')}:{c['id']}" for c in final if "id" in c]
    if mission_id and trace_id:
        await db.agent_messages.insert_one({
            "mission_id": mission_id, "trace_id": trace_id,
            "from_agent":"AdaptiveRetriever","to_agent":"Planner",
            "role":"tool_result",
            "content":{"query": query, "n_results": len(final), "plan": plan},
            "context_doc_ids": context_doc_ids,
            "ts": datetime.now(timezone.utc),
        })
    return {"results": final, "plan": plan, "context_doc_ids": context_doc_ids}
```

---

## 5 · Reasoning across sources — `MultiSourceSynthesizer`

When the planner asks "Can I fly Drone1 from Depot to Royal London right now?", the synthesizer pulls top-k from **`mission_memory`** (past attempts), **`regulations`** (UK CAA), **`facility_intel`** (Royal London helipad rules), **`weather_observations`** (last 30 minutes), and structures them into a Markdown context block with **provenance tags** so every claim is citable.

```python
# rag/synthesizer.py
from datetime import datetime, timedelta, timezone
from .pipeline import adaptive_retrieve
from .clients import db

async def fetch_recent_weather(location_ids: list[str], *, minutes: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    cur = db.weather_observations.find(
        {"location_id": {"$in": location_ids}, "ts": {"$gte": since}},
        {"_id": 0, "ts": 1, "location_id": 1, "wind_speed_ms": 1,
         "gust_ms": 1, "precipitation_mm_h": 1, "condition": 1, "flyable": 1},
    ).sort("ts", -1).limit(50)
    return [d async for d in cur]

class MultiSourceSynthesizer:
    async def synthesize(self, *, query: str, region: str, location_ids: list[str],
                         mission_id: str | None = None, trace_id: str | None = None) -> str:
        memory_task = adaptive_retrieve(
            query, filters={"kind": "reflection", "metadata.region": region},
            mission_id=mission_id, trace_id=trace_id,
        )
        regs_task = adaptive_retrieve(
            query + " UK CAA Article 16 CAP 722 max altitude BVLOS",
            filters={"kind": "regulation"},
            mission_id=mission_id, trace_id=trace_id,
        )
        intel_task = adaptive_retrieve(
            f"facility intel for {' '.join(location_ids)}",
            filters={"kind": "facility_intel"},
            mission_id=mission_id, trace_id=trace_id,
        )
        weather_task = fetch_recent_weather(location_ids)

        memory, regs, intel, weather = await asyncio.gather(
            memory_task, regs_task, intel_task, weather_task,
        )

        def fmt(tag: str, hits: list[dict]) -> str:
            lines = []
            for h in hits:
                ident = h.get("id") or h.get("_id") or "?"
                lines.append(f"- [{tag}:#{ident}] {h.get('text','')[:400]}")
            return "\n".join(lines) if lines else "_(none)_"

        weather_md = "\n".join(
            f"- [wx:{w['location_id']}@{w['ts'].isoformat()}] "
            f"wind={w['wind_speed_ms']:.1f}m/s "
            f"gust={(w.get('gust_ms') or 0):.1f} "
            f"precip={w.get('precipitation_mm_h',0):.1f}mm/h "
            f"cond={w.get('condition','?')} flyable={w.get('flyable',True)}"
            for w in weather
        ) or "_(no recent observations)_"

        return f"""# Retrieval context for: {query}

## Past mission lessons
{fmt('mem', memory['results'])}

## Applicable regulations
{fmt('reg', regs['results'])}

## Facility intel
{fmt('intel', intel['results'])}

## Recent weather (last 30 min)
{weather_md}
"""
```

The output is dropped verbatim into the planner's user message. Every citation `[mem:#…]`, `[reg:#…]`, `[intel:#…]`, `[wx:…]` is grep-able in the audit trail.

---

## 6 · Reranking experiments — offline eval

Goal: keep `RetrievalLearner` honest. We curate a **50-query golden set** stored in `eval/golden_set.jsonl`:

```json
{"id":"q01","query":"safest corridor to Royal London at night with 8 m/s wind",
 "must_cite":["mem:#wind_shear_west_corridor","reg:#UK_CAA_night"]}
```

```python
# eval/run_eval.py
import json, math, asyncio
from rag.pipeline import adaptive_retrieve

async def evaluate(strategy_name: str) -> dict:
    qs = [json.loads(l) for l in open("eval/golden_set.jsonl")]
    ndcg5, mrr = 0.0, 0.0
    for q in qs:
        res = await adaptive_retrieve(q["query"])
        cited = [c for c in res["context_doc_ids"]]
        rels  = [1 if c in q["must_cite"] else 0 for c in cited[:5]]
        # NDCG@5
        dcg  = sum(r / math.log2(i + 2) for i, r in enumerate(rels))
        idcg = sum(1 / math.log2(i + 2) for i in range(min(5, len(q["must_cite"]))))
        ndcg5 += (dcg / idcg) if idcg else 0
        # MRR
        for i, c in enumerate(cited):
            if c in q["must_cite"]:
                mrr += 1.0 / (i + 1)
                break
    n = len(qs)
    return {"strategy": strategy_name, "ndcg@5": ndcg5 / n, "mrr": mrr / n, "n": n}

async def main():
    # A/B harness — toggle env vars and re-run.
    print(await evaluate("baseline_fixed_512_no_rerank"))
    print(await evaluate("markdown_recursive_rerank_2_5"))
    print(await evaluate("late_context_rerank_2_5"))

if __name__ == "__main__":
    asyncio.run(main())
```

Toggling chunking / reranker is via env (read in `clients.py` & `embedder.py`):

```bash
RAG_CHUNK_STRATEGY=late_context RAG_RERANK_MODEL=rerank-2.5 uv run python eval/run_eval.py
```

Results we expect (baseline observation; `RetrievalLearner` confirms or refutes):

| Strategy | NDCG@5 | MRR |
|---|---|---|
| fixed_512, no rerank | 0.51 | 0.46 |
| markdown_recursive, rerank-2.5 | 0.71 | 0.63 |
| **late_context, rerank-2.5** | **0.79** | **0.71** |

---

## 7 · `RetrievalLearner` — improvement-over-time loop

Every retrieval logs a row to `agent_messages` and an outcome row to `reflection_eval`-adjacent state. A nightly job re-tunes per-collection knobs:

- `numCandidates` per query class
- chunking strategy weight (when ties exist)
- filter weights (which filters help vs hurt recall)

```python
# rag/learner.py
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from statistics import mean
from .clients import db

class RetrievalLearner:
    """Reads outcomes, writes tuned config back to mission_memory + a config doc."""

    CONFIG_DOC_ID = "rag_runtime_config"

    async def collect_outcomes(self, *, hours: int = 24) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        # Join: each agent_messages row from AdaptiveRetriever paired with the
        # mission outcome it informed.
        pipeline = [
          {"$match": {"from_agent": "AdaptiveRetriever", "ts": {"$gte": since},
                      "mission_id": {"$ne": None}}},
          {"$lookup": {"from": "missions", "localField": "mission_id",
                       "foreignField": "_id", "as": "m"}},
          {"$unwind": "$m"},
          {"$project": {
            "mission_id": 1,
            "context_doc_ids": 1,
            "n_hits": "$content.n_results",
            "loops": {"$size": "$content.plan"},
            "outcome": "$m.status",
            "failed_reason": "$m.failed_reason",
          }},
        ]
        return [r async for r in db.agent_messages.aggregate(pipeline)]

    async def update_memory_scores(self, outcomes: list[dict]) -> None:
        # EMA: positive outcomes boost score_ema; negative outcomes decay it.
        ALPHA = 0.2
        contributions = defaultdict(list)
        for o in outcomes:
            reward = 1.0 if o["outcome"] == "completed" else (0.0 if o["outcome"] == "failed" else 0.5)
            for cid in o.get("context_doc_ids", []):
                if cid.startswith("mission_memory:"):
                    _, oid = cid.split(":", 1)
                    contributions[oid].append(reward)
        for oid, rewards in contributions.items():
            r = mean(rewards)
            await db.mission_memory.update_one(
                {"_id": oid},
                {"$set": {"last_used_at": datetime.now(timezone.utc)},
                 "$inc": {"use_count": len(rewards)},
                 "$mul": {"score_ema": (1 - ALPHA)},
                },
            )
            await db.mission_memory.update_one(
                {"_id": oid},
                {"$inc": {"score_ema": ALPHA * r}},
            )

    async def retune_num_candidates(self, outcomes: list[dict]) -> dict:
        """If avg loops > 1.5 we're under-retrieving; bump numCandidates."""
        avg_loops = mean([o["loops"] for o in outcomes]) if outcomes else 1.0
        cur = await db.runtime_config.find_one({"_id": self.CONFIG_DOC_ID}) or {}
        nc  = cur.get("num_candidates", 200)
        if avg_loops > 1.5:
            nc = min(int(nc * 1.25), 1000)
        elif avg_loops < 1.05:
            nc = max(int(nc * 0.9), 150)
        await db.runtime_config.update_one(
            {"_id": self.CONFIG_DOC_ID},
            {"$set": {"num_candidates": nc, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return {"avg_loops": avg_loops, "num_candidates": nc}

    async def synthesize_failed_lessons(self, outcomes: list[dict]) -> int:
        """Failed retrievals → synthetic training rows for ReflectionAgent."""
        failed = [o for o in outcomes if o["outcome"] == "failed"]
        if not failed:
            return 0
        rows = [{
            "mission_id": o["mission_id"],
            "failed_reason": o.get("failed_reason"),
            "context_doc_ids": o.get("context_doc_ids", []),
            "created_at": datetime.now(timezone.utc),
            "consumed": False,
        } for o in failed]
        await db.reflection_training_queue.insert_many(rows)
        return len(rows)

    async def run_nightly(self) -> dict:
        outcomes = await self.collect_outcomes(hours=24)
        await self.update_memory_scores(outcomes)
        nc_report = await self.retune_num_candidates(outcomes)
        seeded = await self.synthesize_failed_lessons(outcomes)
        return {"outcomes": len(outcomes), "tuned": nc_report, "synthetic_rows": seeded}

if __name__ == "__main__":
    asyncio.run(RetrievalLearner().run_nightly())
```

Schedule via Atlas Trigger (cron) `0 2 * * *`:

```javascript
// functions/nightly_rag_tune.js
exports = async function() {
  const url = context.values.get("BACKEND_BASE_URL") + "/api/internal/rag/nightly";
  return await context.http.post({ url, headers:{"X-Internal-Token":[context.values.get("INTERNAL_API_TOKEN")]} });
};
```

The endpoint:

```python
@app.post("/api/internal/rag/nightly")
async def rag_nightly(x_internal_token: str = Header(...)):
    if x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(401)
    return await RetrievalLearner().run_nightly()
```

---

## 8 · `langchain-mongodb` integration (for the chat agent)

For conversational memory we use `MongoDBChatMessageHistory`; for vector memory `MongoDBAtlasVectorSearch`. This lets every LangChain chain "just work" against our `mission_memory` index.

```python
# rag/langchain_bindings.py
from langchain_mongodb import MongoDBAtlasVectorSearch, MongoDBChatMessageHistory
from .clients import mongo, embeddings_primary

mission_memory_vs = MongoDBAtlasVectorSearch(
    collection=mongo["dronefleet"]["mission_memory"],
    embedding=embeddings_primary,
    index_name="mission_memory_vec",
    text_key="text",
    embedding_key="embedding",
    relevance_score_fn="cosine",
)

def chat_history_for(operator_id: str, session_id: str) -> MongoDBChatMessageHistory:
    return MongoDBChatMessageHistory(
        connection_string=mongo.address[0] if False else __import__("os").environ["MONGODB_URI"],
        database_name="dronefleet",
        collection_name="chat_messages",
        session_id=f"{operator_id}:{session_id}",
    )
```

Use it as a retriever in LangGraph:

```python
retriever = mission_memory_vs.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 5,
        "pre_filter": {"kind": {"$in": ["reflection","incident"]}},
    },
)
```

---

## 9 · ContextualCompressionRetriever with Voyage rerank

```python
# rag/lc_compression.py
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import DocumentCompressorPipeline
from langchain_voyageai import VoyageAIRerank
from .langchain_bindings import mission_memory_vs

base = mission_memory_vs.as_retriever(search_kwargs={"k": 30})
voyage_rr = VoyageAIRerank(model="rerank-2.5", top_k=5,
                           voyage_api_key=__import__("os").environ["VOYAGE_API_KEY"])
ccr = ContextualCompressionRetriever(
    base_retriever=base,
    base_compressor=DocumentCompressorPipeline(transformers=[voyage_rr]),
)
```

Now `ccr.ainvoke("safe corridor for Royal London at night")` returns a reranked, compressed top-5 directly.

---

## 10 · Failure modes & mitigations

| Failure | Symptom | Mitigation |
|---|---|---|
| **Stale embeddings** (model upgrade, doc revised) | `embedding_model` mismatch with retriever; weird relevance | Background `EmbeddingRefreshWorker` re-embeds anything older than **30 days** OR with `embedding_model != current_default`. Index by `(embedding_model, created_at)`. |
| **Vector drift** (Voyage upgrades a model server-side) | Eval NDCG drops without code change | Nightly `vector_drift_eval.py` re-runs the 50-query golden set; opens a GitHub issue if NDCG@5 drops > 5 pts week-over-week. |
| **Cold start** (empty `mission_memory` on first deploy) | Retrieval returns nothing; planner has no priors | Seed scripts in [`09-seed-and-data.md`](./09-seed-and-data.md) write 4 regulation profiles + 50 synthetic past missions before first run. |
| **Filter explosion** (every query gets unique filter combo, no candidate pool) | Recall craters | `RetrievalCriticAgent` triggers `drop_filters` action on second loop; `RetrievalLearner` flags filters whose presence drops MRR. |
| **HyDE hallucinations** | Sub-query #3 retrieves an alternate-reality doc | Cap HyDE rewrite at one sentence; weight HyDE rankings 0.7× in RRF (configurable in `runtime_config`). |
| **PII leakage in chunks** | Operator names appearing in retrieved snippets | `chunk_redactor.py` regex-masks NHS numbers, postcodes, and bare names before embedding. Run as part of every chunker. |
| **Reranker quota exhausted** | Voyage 429s | Local fallback: skip rerank, return RRF top-5; emit `agent_messages` entry `role:"broadcast"` so operators see degraded mode. |
| **Time-series weather lag** | Atlas Trigger fires reroute before backend has indexed the obs | The trigger waits 250 ms (`utils.sleep`) and re-reads to confirm; idempotent on `tool_call_log.idempotency_key`. |

`vector_drift_eval.py`:

```python
# eval/vector_drift_eval.py
import asyncio, json, math
from rag.embedder import Embedder
from rag.vector import vector_search

async def main():
    qs = [json.loads(l) for l in open("eval/golden_set.jsonl")]
    drops = []
    for q in qs:
        v = await Embedder.embed_query(q["query"])
        hits = await vector_search(collection="mission_memory", index="mission_memory_vec",
                                    query_vec=v, k=5)
        cited = [f"mission_memory:{str(h['_id'])}" for h in hits]
        hit = any(c in cited for c in q["must_cite"])
        if not hit:
            drops.append(q["id"])
    print(f"misses: {len(drops)}/{len(qs)}: {drops}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 11 · End-to-end smoke test

```python
# scripts/smoke_rag.py
import asyncio
from rag.pipeline import adaptive_retrieve
from rag.synthesizer import MultiSourceSynthesizer

async def main():
    res = await adaptive_retrieve(
        "Can I deliver a blood pack from Depot to Royal London right now if winds are 9 m/s?",
        filters={"metadata.region": "London"},
    )
    print(f"retrieved {len(res['results'])} docs in {len(res['plan'])} loops")
    for r in res["results"]:
        print("-", r.get("kind"), r.get("text", "")[:120])

    md = await MultiSourceSynthesizer().synthesize(
        query="safe corridor and rules for Royal London approach now",
        region="London",
        location_ids=["Royal London", "Depot"],
    )
    print(md[:1500])

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
uv run python scripts/smoke_rag.py
```

Expected: ≥1 reflection cited, ≥1 regulation cited, recent weather lines, plan with ≤2 loops on a healthy index.

---

## 12 · Summary cheat-sheet

- **Embedding default**: `voyage-3-large` 1024-dim, cosine.
- **Hot-tier embedding**: `voyage-3` 256-dim Matryoshka — for operator preferences re-embedded on every change.
- **Long-doc embedding**: `voyage-context-3` (late chunking) — for regulations.
- **Reranker**: `rerank-2.5`, top-30 → top-5.
- **Hybrid**: vector × BM25 RRF (k=60).
- **Filters declared in vector index**: `kind`, `metadata.region`, `metadata.weather_class`, `metadata.success`, `embedding_model`.
- **`numCandidates`**: `max(150, 10×k)`, tuned nightly by `RetrievalLearner`.
- **Loop cap**: 3 (critic-driven).
- **Provenance tags**: `[mem:#…]`, `[reg:#…]`, `[intel:#…]`, `[wx:…]`.
- **Self-evolution**: outcomes feed back into `mission_memory.score_ema`, into `runtime_config.num_candidates`, and into `reflection_training_queue` for the ReflectionAgent.

You now have an agentic, adaptive, source-aware RAG system that *measurably* improves over time. Continue to [`09-seed-and-data.md`](./09-seed-and-data.md) for the runnable seed pipeline.
