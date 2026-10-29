"""
main.py
=======
FastAPI backend for IIT Faculty Search.

Start with:
    uvicorn backend.main:app --reload --port 8000
    (from the repo root)

Or from inside backend/:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import os
import pickle
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Path setup — works whether run from repo root or backend/
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
_INDICES_DIR = os.environ.get("INDICES_DIR", os.path.join(_REPO_ROOT, "indices"))
# Add repo root to sys.path so `from backend.search import ...` works when
# running from the backend/ directory.
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.search import (
    hybrid_search,
    keyword_search,
    semantic_search,
    structured_search,
)

# ---------------------------------------------------------------------------
# Module-level singletons (populated by lifespan)
# ---------------------------------------------------------------------------

_bm25_retriever = None
_faculty: list[dict] = []
_tantivy_index = None
_qdrant_client = None
_embed_model = None
_embed_model_lock = threading.Lock()


def _get_embed_model():
    global _embed_model
    with _embed_model_lock:
        if _embed_model is None:
            from sentence_transformers import SentenceTransformer

            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[startup] Sentence-transformer model loaded")
    return _embed_model


# ---------------------------------------------------------------------------
# Lifespan — load all indices once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bm25_retriever, _faculty, _tantivy_index, _qdrant_client, _embed_model

    # --- BM25s ---
    bm25_path = os.path.join(_INDICES_DIR, "bm25s.pkl")
    if not os.path.exists(bm25_path):
        raise RuntimeError(
            f"BM25s index not found at {bm25_path}. Run build_indices.py first."
        )
    with open(bm25_path, "rb") as fh:
        payload = pickle.load(fh)
    _bm25_retriever = payload["retriever"]
    _faculty = payload["faculty"]
    print(f"[startup] BM25s index loaded ({len(_faculty)} faculty)")

    # --- Tantivy (optional) ---
    tantivy_dir = os.path.join(_INDICES_DIR, "tantivy")
    try:
        import tantivy

        if os.path.isdir(tantivy_dir):
            schema_builder = tantivy.SchemaBuilder()
            schema_builder.add_integer_field("doc_id", stored=True, indexed=True)
            schema_builder.add_text_field("name", stored=True, tokenizer_name="en_stem")
            schema_builder.add_text_field("departments", stored=True, tokenizer_name="en_stem")
            schema_builder.add_text_field("research_interests", stored=True, tokenizer_name="en_stem")
            schema_builder.add_text_field("titles", stored=True, tokenizer_name="en_stem")
            schema_builder.add_text_field("profile", stored=False, tokenizer_name="en_stem")
            schema_builder.add_text_field("email", stored=True)
            schema = schema_builder.build()
            _tantivy_index = tantivy.Index(schema, path=tantivy_dir)
            print("[startup] Tantivy index loaded")
        else:
            print("[startup] Tantivy index directory not found — structured search will use BM25s fallback")
    except ImportError:
        print("[startup] tantivy not installed — structured search will use BM25s fallback")

    # --- Qdrant + SentenceTransformer ---
    qdrant_dir = os.path.join(_INDICES_DIR, "qdrant")
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_key = os.environ.get("QDRANT_API_KEY")

    from qdrant_client import QdrantClient
    if qdrant_url and qdrant_key:
        _qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
        print(f"[startup] Qdrant Cloud client connected ({qdrant_url})")
    else:
        if not os.path.isdir(qdrant_dir):
            raise RuntimeError(
                f"Qdrant index not found at {qdrant_dir}. Run build_indices.py first."
            )
        _qdrant_client = QdrantClient(path=qdrant_dir)
        print(f"[startup] Qdrant local client loaded ({qdrant_dir})")

    yield  # app runs here

    # Cleanup (nothing needed for these clients)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="IIT Faculty Search", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug_from_url(profile_url: str) -> str:
    return profile_url.rstrip("/").split("/")[-1]


def _all_departments() -> list[str]:
    dept_set: set[str] = set()
    for f in _faculty:
        for d in f.get("departments", []):
            if d:
                dept_set.add(d)
    return sorted(dept_set)


def _matches_faculty_type(record: dict, faculty_type: str | None) -> bool:
    if not faculty_type:
        return True
    titles = " ".join(record.get("titles", [])).casefold()
    if faculty_type == "Full Professor":
        return "professor" in titles and not any(
            modifier in titles
            for modifier in (
                "assistant professor",
                "associate professor",
                "teaching professor",
                "research professor",
                "adjunct",
            )
        )
    return faculty_type.casefold() in titles


def _filter_results(
    records: list[dict], dept: str | None, faculty_type: str | None
) -> list[dict]:
    return [
        record
        for record in records
        if (not dept or dept in record.get("departments", []))
        and _matches_faculty_type(record, faculty_type)
    ]


def _search_response(
    results: list[dict], mode: str, offset: int, limit: int
) -> dict:
    return {
        "results": results[offset : offset + limit],
        "total": len(results),
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/departments")
def get_departments():
    return {"departments": _all_departments()}


@app.get("/faculty/{slug}")
def get_faculty(slug: str):
    for f in _faculty:
        url = f.get("profile_url", "")
        if _slug_from_url(url) == slug:
            return f
    raise HTTPException(status_code=404, detail="Faculty member not found")


@app.get("/search/keyword")
def search_keyword(
    q: str,
    dept: str | None = None,
    faculty_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    results = _filter_results(
        keyword_search(q, len(_faculty), _bm25_retriever, _faculty), dept, faculty_type
    )
    return _search_response(results, "keyword", offset, limit)


@app.get("/search/semantic")
def search_semantic(
    q: str,
    dept: str | None = None,
    faculty_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    results = _filter_results(
        semantic_search(q, None, len(_faculty), _qdrant_client, _get_embed_model()),
        dept,
        faculty_type,
    )
    return _search_response(results, "semantic", offset, limit)


@app.get("/search/structured")
def search_structured(
    q: str = "",
    name: str | None = None,
    dept: str | None = None,
    faculty_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    results = _filter_results(
        structured_search(
            q, name, None, len(_faculty), _tantivy_index, _bm25_retriever, _faculty
        ),
        dept,
        faculty_type,
    )
    return _search_response(results, "structured", offset, limit)


@app.get("/search")
def search(
    q: str = "",
    dept: str | None = None,
    faculty_type: str | None = None,
    mode: str = Query("hybrid", pattern="^(hybrid|keyword|semantic|structured)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    if not q:
        results = _filter_results(_faculty, dept, faculty_type)
        return _search_response(results, mode, offset, limit)

    if mode == "keyword":
        results = keyword_search(q, len(_faculty), _bm25_retriever, _faculty)
    elif mode == "semantic":
        results = semantic_search(q, None, len(_faculty), _qdrant_client, _get_embed_model())
    elif mode == "structured":
        results = structured_search(
            q, None, None, len(_faculty), _tantivy_index, _bm25_retriever, _faculty
        )
    else:  # hybrid
        results = hybrid_search(
            q,
            None,
            len(_faculty),
            _bm25_retriever,
            _faculty,
            _tantivy_index,
            _qdrant_client,
            _get_embed_model(),
        )

    results = _filter_results(results, dept, faculty_type)
    return _search_response(results, mode, offset, limit)
