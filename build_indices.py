"""
build_indices.py
================
One-time script: builds BM25s, Tantivy (optional), and Qdrant semantic indices
from faculty.json.

Run after scraping:
    python build_indices.py

Outputs:
    indices/bm25s.pkl       — BM25s retriever + faculty list
    indices/tantivy/        — Tantivy index directory (if tantivy is installed)
    indices/qdrant/         — Qdrant persistent local collection
"""

import argparse
import json
import os
import pickle
import shutil
import sys

# ---------------------------------------------------------------------------
# Load faculty data
# ---------------------------------------------------------------------------

FACULTY_JSON = os.path.join(os.path.dirname(__file__), "faculty.json")
INDICES_DIR = os.path.join(os.path.dirname(__file__), "indices")


def load_faculty() -> list[dict]:
    if not os.path.exists(FACULTY_JSON):
        print(f"ERROR: {FACULTY_JSON} not found. Run the scraper first.")
        sys.exit(1)
    with open(FACULTY_JSON, encoding="utf-8") as f:
        return json.load(f)


def make_searchable(record: dict) -> str:
    """Build the shared retrieval text from all useful profile fields."""
    parts = [
        record.get("name", ""),
        " ".join(record.get("titles", [])),
        " ".join(record.get("departments", [])),
        " ".join(record.get("research_interests", [])),
        " ".join(record.get("publications", [])),
        " ".join(record.get("education", [])),
        " ".join(record.get("professional_affiliations", [])),
        " ".join(
            item
            for values in record.get("additional_sections", {}).values()
            for item in values
        ),
    ]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 1. BM25s Index
# ---------------------------------------------------------------------------

def build_bm25s(faculty: list[dict]) -> None:
    import bm25s

    print("Building BM25s index …")
    os.makedirs(INDICES_DIR, exist_ok=True)

    corpus = [make_searchable(f) for f in faculty]
    corpus_tokens = bm25s.tokenize(corpus)

    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    out_path = os.path.join(INDICES_DIR, "bm25s.pkl")
    with open(out_path, "wb") as fh:
        pickle.dump(
            {"retriever": retriever, "faculty": faculty, "corpus_tokens": corpus_tokens},
            fh,
        )
    print(f"  Saved → {out_path}")


# ---------------------------------------------------------------------------
# 2. Tantivy Index (optional stretch goal)
# ---------------------------------------------------------------------------

def build_tantivy(faculty: list[dict]) -> None:
    try:
        import tantivy
    except ImportError:
        print("tantivy not installed — skipping (BM25s covers keyword search).")
        return

    print("Building Tantivy index …")
    tantivy_dir = os.path.join(INDICES_DIR, "tantivy")
    if os.path.exists(tantivy_dir):
        shutil.rmtree(tantivy_dir)
    os.makedirs(tantivy_dir, exist_ok=True)

    try:
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_integer_field("doc_id", stored=True, indexed=True)
        schema_builder.add_text_field("name", stored=True, tokenizer_name="en_stem")
        schema_builder.add_text_field("departments", stored=True, tokenizer_name="en_stem")
        schema_builder.add_text_field("research_interests", stored=True, tokenizer_name="en_stem")
        schema_builder.add_text_field("titles", stored=True, tokenizer_name="en_stem")
        schema_builder.add_text_field("profile", stored=False, tokenizer_name="en_stem")
        schema_builder.add_text_field("email", stored=True)
        schema = schema_builder.build()

        index = tantivy.Index(schema, path=tantivy_dir)
        writer = index.writer()

        for i, f in enumerate(faculty):
            writer.add_document(tantivy.Document(
                doc_id=i,
                name=f.get("name", ""),
                departments=" ".join(f.get("departments", [])),
                research_interests=" ".join(f.get("research_interests", [])),
                titles=" ".join(f.get("titles", [])),
                profile=make_searchable(f),
                email=f.get("email", ""),
            ))

        writer.commit()
        index.reload()
        print(f"  Saved → {tantivy_dir}/")
    except Exception as exc:
        print(f"  Tantivy indexing failed: {exc} — falling back to BM25s only.")


# ---------------------------------------------------------------------------
# 3. Qdrant Semantic Index
# ---------------------------------------------------------------------------

def build_qdrant(faculty: list[dict]) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    from sentence_transformers import SentenceTransformer

    MODEL_NAME = "all-MiniLM-L6-v2"
    COLLECTION = "faculty"
    VECTOR_SIZE = 384
    qdrant_dir = os.path.join(INDICES_DIR, "qdrant")

    print(f"Building Qdrant semantic index (model: {MODEL_NAME}) …")
    print("  Loading sentence-transformers model …")
    model = SentenceTransformer(MODEL_NAME)

    texts = [make_searchable(f) for f in faculty]
    print(f"  Encoding {len(texts)} documents …")
    vectors = model.encode(texts, show_progress_bar=True, batch_size=64)

    os.makedirs(qdrant_dir, exist_ok=True)
    client = QdrantClient(path=qdrant_dir)

    # Re-create collection (idempotent)
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION in existing:
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )

    points = [
        PointStruct(id=i, vector=vectors[i].tolist(), payload=faculty[i])
        for i in range(len(faculty))
    ]

    # Upload in batches
    batch_size = 100
    for start in range(0, len(points), batch_size):
        client.upsert(collection_name=COLLECTION, points=points[start : start + batch_size])

    print(f"  Saved → {qdrant_dir}/  ({len(points)} vectors)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default=FACULTY_JSON)
    parser.add_argument('--indices-dir', default=INDICES_DIR)
    args = parser.parse_args()
    FACULTY_JSON = args.input
    INDICES_DIR = args.indices_dir
    faculty = load_faculty()
    if not faculty:
        sys.exit('No faculty records; refusing to build empty indices.')
    print(f"Loaded {len(faculty)} faculty records from {FACULTY_JSON}\n")

    build_bm25s(faculty)
    print()
    build_tantivy(faculty)
    print()
    build_qdrant(faculty)
    print("\nAll indices built successfully.")
