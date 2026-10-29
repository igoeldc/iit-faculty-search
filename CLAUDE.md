# IIT Faculty Search Engine — Claude Code Briefing

## Context
This is a faculty search and information retrieval system for Illinois Tech (IIT), built as a learning project exploring IR system architecture. The developer has prior experience building a similar system (https://github.com/igoeldc/ir_engine) using Scrapy, scikit-learn TF-IDF, FAISS, Sentence Transformers, and Flask. This project deliberately uses different technologies to explore alternatives.

---

## Current Status
- **Phase 1 (Scraping): COMPLETE.** `scraper.py` and `faculty.json` already exist.
- **Phase 2 (Indexing): START HERE.**

---

## Stack

| Layer | Tool |
|---|---|
| Scraping | `requests` + `BeautifulSoup` ✅ done |
| Keyword search | `bm25s` |
| Structured/field-aware search | `tantivy` (stretch goal — smoke test first) |
| Semantic search | `qdrant-client` (in-memory locally, Qdrant Cloud in prod) |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| Backend | `FastAPI` |
| Frontend | HTML/CSS/JS (static) |
| Frontend hosting | GitHub Pages (subpage of personal site) |
| Backend hosting | Streamlit Community Cloud (approach TBD at deploy time) |
| Vector DB (prod) | Qdrant Cloud (free 1GB cluster) |

---

## Data Model
`faculty.json` is a list of objects. Each looks like:
```json
{
  "name": "Jane Smith",
  "titles": ["Associate Professor of Computer Science"],
  "departments": ["Computer Science"],
  "profile_types": ["Faculty"],
  "email": "jsmith@iit.edu",
  "phone": "312-567-XXXX",
  "education": ["Ph.D. Computer Science, MIT, 2010"],
  "research_interests": ["NLP", "Machine Learning"],
  "professional_affiliations": ["IEEE Senior Member"],
  "publications": ["Title 1 (2023)", "Title 2 (2022)"],
  "books": [],
  "patents": [],
  "google_scholar_url": "https://scholar.google.com/...",
  "photo_url": "https://www.iit.edu/sites/...",
  "profile_url": "https://www.iit.edu/directory/people/jane-smith"
}
```

---

## Target Project Structure
```
iit-faculty-search/
├── scraper.py              # ✅ complete
├── faculty.json            # ✅ complete (run scraper.py to regenerate)
├── build_indices.py        # Phase 2 — build all indices from faculty.json
├── indices/
│   ├── bm25s.pkl           # BM25s index + faculty list (pickle)
│   └── tantivy/            # Tantivy index directory
├── backend/
│   ├── main.py             # FastAPI app (lifespan, CORS, routes)
│   ├── search.py           # Search logic (BM25s, Tantivy, Qdrant)
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

---

## Phase 2 — build_indices.py

Build three indices from `faculty.json`. This is a one-time local script. Its outputs (`indices/`) are committed to the repo and loaded at backend startup.

### 1. BM25s Index
- For each faculty record, build a searchable string: concatenate `name`, `titles`, `departments`, `research_interests`, `publications` (join list fields with spaces)
- Tokenize with `bm25s.tokenize()`
- Fit a `bm25s.BM25()` retriever
- Serialize with `pickle` to `indices/bm25s.pkl` as a dict: `{"retriever": retriever, "faculty": faculty_list, "corpus_tokens": corpus_tokens}`
- The `faculty` list must preserve original order so BM25s integer doc IDs map back to records

### 2. Tantivy Index
- **Smoke test first:** if `import tantivy` fails, skip gracefully and log a warning — BM25s covers all keyword search as fallback
- Schema fields:
  - `doc_id`: `INTEGER` (INDEXED, STORED) — position in faculty list
  - `name`: `TEXT` (INDEXED, STORED, tokenizer="en_stem") 
  - `departments`: `TEXT` (INDEXED, STORED)
  - `research_interests`: `TEXT` (INDEXED, STORED)
  - `titles`: `TEXT` (INDEXED, STORED)
  - `email`: `TEXT` (STORED)
- Build index to `indices/tantivy/`
- Field boosting is handled at query time in `search.py`, not at index time

### 3. Qdrant Semantic Index
- Load `all-MiniLM-L6-v2` from `sentence-transformers` (vector size: 384)
- For each faculty record, embed: `" | ".join(research_interests) + " " + " ".join(titles) + " " + " ".join(departments)`
- Use `QdrantClient(path="indices/qdrant/")` for a persistent local build that can be loaded without re-embedding at every startup
- Collection: `faculty`, distance: `COSINE`
- Store the **full faculty record as the Qdrant point payload** — no secondary lookup needed
- Use faculty list index as the point ID (integer)

---

## Phase 3 — FastAPI Backend

### backend/main.py
- Use `lifespan` context manager (NOT deprecated `@app.on_event`) to load all indices at startup into module-level singletons
- Enable CORS for all origins (frontend on GitHub Pages calls this cross-origin)
- Qdrant client logic:
  - If env vars `QDRANT_URL` and `QDRANT_API_KEY` are set → use Qdrant Cloud
  - Otherwise → use `QdrantClient(path="indices/qdrant/")` (local persistent)

### backend/search.py
Implement these functions:

**`keyword_search(q, limit) -> list[dict]`**
- Tokenize query with `bm25s.tokenize()`
- Retrieve top results from BM25s retriever
- Return list of faculty dicts with added `score` and `search_type: "keyword"` fields

**`structured_search(q, name, department, limit) -> list[dict]`**
- Build a Tantivy query boosting `name^5`, `departments^3`, `research_interests^2`, `titles^1`
- If Tantivy unavailable, fall back to `keyword_search()`
- Return list of faculty dicts with `score` and `search_type: "structured"` fields

**`semantic_search(q, department_filter, limit) -> list[dict]`**
- Embed query with the same `sentence-transformers` model used at index time
- If `department_filter` provided, use Qdrant payload filter: `{"must": [{"key": "departments", "match": {"any": [department_filter]}}]}`
- Return list of faculty dicts from Qdrant payload with `score` and `search_type: "semantic"` fields

**`hybrid_search(q, department, limit) -> list[dict]`**
- Run `keyword_search` + `structured_search` + `semantic_search` concurrently (use `asyncio.gather` or `concurrent.futures`)
- Merge with **Reciprocal Rank Fusion**: `score = sum(1 / (k + rank))` for each list, k=60
- Deduplicate by `profile_url`, keeping highest RRF score
- Apply department filter post-merge if not already applied in semantic leg
- Return top `limit` results sorted by RRF score

### API Endpoints

```
GET /search?q=...&dept=...&mode=hybrid&limit=10
    # mode: "hybrid" | "keyword" | "semantic" | "structured"
    # dept: optional department filter string

GET /search/keyword?q=...&limit=10
GET /search/semantic?q=...&dept=...&limit=10
GET /search/structured?q=...&name=...&dept=...&limit=10

GET /departments
    # Returns sorted list of all unique department strings from faculty.json

GET /faculty/{slug}
    # slug derived from profile_url: last path segment
    # e.g. "jane-smith" from ".../directory/people/jane-smith"
```

---

## Phase 4 — Frontend (HTML/CSS/JS)

Single-page app in `frontend/`. Will be hosted as a subpage of the developer's personal GitHub Pages site.

### app.js
- Store API base URL as a single constant at the top: `const API_BASE = "http://localhost:8000"` — easy to swap to production URL
- On page load: fetch `/departments` to populate the department dropdown
- On search submit: call `/search` with current query, department filter, and mode
- Render result cards

### UI Components
- **Search bar** with submit button
- **Department dropdown** (populated dynamically from `/departments`)
- **Mode toggle**: Hybrid / Keyword / Semantic / Structured (default: Hybrid)
- **Result cards** showing:
  - Name (linked to `profile_url`)
  - Title(s)
  - Department(s)
  - Research interests (as tags/chips)
  - Email
  - Search type badge (keyword / semantic / hybrid)
- **Loading state** while fetching
- **Empty state** if no results

### Design requirements
- Clean, professional aesthetic — not generic/template-looking
- Not Streamlit-like or dashboard-like — closer to a proper search engine results page
- Mobile responsive

---

## Key Implementation Notes

1. **Tantivy is a stretch goal** — always wrap in try/except, fall back to BM25s silently if unavailable
2. **Never re-embed at API request time** — embeddings happen once in `build_indices.py`; at runtime only the query gets embedded
3. **Qdrant local path vs cloud** — controlled entirely by env vars, no code changes needed between environments
4. **RRF k=60** is standard; don't tune this unless results are noticeably bad
5. **CORS** must be open (`allow_origins=["*"]`) — GitHub Pages origin will vary
6. **`lifespan` not `@app.on_event`** — the latter is deprecated in recent FastAPI versions

---

## Environment Variables
```
QDRANT_URL=https://your-cluster.qdrant.io   # only needed in production
QDRANT_API_KEY=your-api-key                 # only needed in production
```
Without these, the backend automatically uses local persistent Qdrant storage.

---

## Installation
```bash
pip install bm25s tantivy qdrant-client sentence-transformers fastapi uvicorn

# Build indices (run once after scraping)
python build_indices.py

# Run backend
uvicorn backend.main:app --reload --port 8000

# Frontend: open frontend/index.html in browser
# (or serve with: python -m http.server 3000 --directory frontend)
```
