"""
search.py
=========
Search logic: keyword (BM25s), structured (Tantivy), semantic (Qdrant), hybrid (RRF).

All functions are synchronous and called from FastAPI route handlers.
Index singletons are passed in by main.py (loaded once at startup).
"""

from __future__ import annotations

import concurrent.futures

# ---------------------------------------------------------------------------
# Keyword search (BM25s)
# ---------------------------------------------------------------------------

def keyword_search(
    q: str,
    limit: int,
    retriever,
    faculty: list[dict],
) -> list[dict]:
    import bm25s

    query_tokens = bm25s.tokenize(q)
    results, scores = retriever.retrieve(query_tokens, k=min(limit, len(faculty)))

    out = []
    for i in range(results.shape[1]):
        doc_idx = int(results[0, i])
        score = float(scores[0, i])
        if score <= 0:
            continue
        record = dict(faculty[doc_idx])
        record["score"] = score
        record["search_type"] = "keyword"
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# Structured search (Tantivy) — falls back to keyword_search if unavailable
# ---------------------------------------------------------------------------

def structured_search(
    q: str,
    name: str | None,
    department: str | None,
    limit: int,
    tantivy_index,   # tantivy.Index or None
    retriever,
    faculty: list[dict],
    fallback_to_keyword: bool = True,
) -> list[dict]:
    if tantivy_index is None:
        if not fallback_to_keyword:
            return []
        results = keyword_search(q, limit, retriever, faculty)
        for r in results:
            r["search_type"] = "structured"
        return results

    try:
        import tantivy

        searcher = tantivy_index.searcher()

        # Build per-field queries
        parser_fields = {
            "research_interests": 2.0,
            "titles": 1.0,
            "departments": 3.0,
            "name": 5.0,
            "profile": 0.5,
        }

        text = q or ""
        if name:
            text = name

        # Build a BooleanQuery with per-field boosts
        subqueries = []
        for field, boost in parser_fields.items():
            try:
                parser = tantivy.QueryParser.for_index(tantivy_index, [field])
                sub = parser.parse_query(text)
                subqueries.append(
                    (tantivy.Occur.Should, tantivy.Query.boost_query(sub, boost))
                )
            except Exception:
                pass

        if department:
            try:
                dept_parser = tantivy.QueryParser.for_index(tantivy_index, ["departments"])
                dept_q = dept_parser.parse_query(department)
                subqueries.append((tantivy.Occur.Must, dept_q))
            except Exception:
                pass

        if not subqueries:
            if not fallback_to_keyword:
                return []
            results = keyword_search(q, limit, retriever, faculty)
            for r in results:
                r["search_type"] = "structured"
            return results

        combined = tantivy.Query.boolean_query(subqueries)
        top_docs = searcher.search(combined, limit).hits

        out = []
        for score, addr in top_docs:
            doc = searcher.doc(addr)
            doc_id = doc["doc_id"][0]
            record = dict(faculty[doc_id])
            record["score"] = float(score)
            record["search_type"] = "structured"
            out.append(record)
        return out

    except Exception as exc:
        # Tantivy failed at query time — use BM25s outside hybrid search.
        import warnings
        if not fallback_to_keyword:
            warnings.warn(f"Tantivy query failed ({exc}), omitting structured results")
            return []
        warnings.warn(f"Tantivy query failed ({exc}), falling back to BM25s")
        results = keyword_search(q, limit, retriever, faculty)
        for r in results:
            r["search_type"] = "structured"
        return results


# ---------------------------------------------------------------------------
# Semantic search (Qdrant)
# ---------------------------------------------------------------------------

def semantic_search(
    q: str,
    department_filter: str | None,
    limit: int,
    qdrant_client,
    embed_model,
    min_score: float = 0.25,
) -> list[dict]:
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    vector = embed_model.encode([q])[0].tolist()

    qdrant_filter = None
    if department_filter:
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="departments",
                    match=MatchAny(any=[department_filter]),
                )
            ]
        )

    response = qdrant_client.query_points(
        collection_name="faculty",
        query=vector,
        query_filter=qdrant_filter,
        score_threshold=min_score,
        limit=limit,
        with_payload=True,
    )

    out = []
    for hit in response.points:
        record = dict(hit.payload)
        record["score"] = float(hit.score)
        record["search_type"] = "semantic"
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# Hybrid search (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def hybrid_search(
    q: str,
    department: str | None,
    limit: int,
    retriever,
    faculty: list[dict],
    tantivy_index,
    qdrant_client,
    embed_model,
    k: int = 60,
) -> list[dict]:
    fetch_n = max(limit * 3, 30)

    def _kw():
        return keyword_search(q, fetch_n, retriever, faculty)

    def _st():
        return structured_search(
            q,
            None,
            department,
            fetch_n,
            tantivy_index,
            retriever,
            faculty,
            fallback_to_keyword=False,
        )

    def _sem():
        return semantic_search(q, department, fetch_n, qdrant_client, embed_model)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        kw_fut = ex.submit(_kw)
        st_fut = ex.submit(_st)
        sem_fut = ex.submit(_sem)
        kw_results = kw_fut.result()
        st_results = st_fut.result()
        sem_results = sem_fut.result()

    # RRF merge
    rrf_scores: dict[str, float] = {}
    best_record: dict[str, dict] = {}

    def _apply_rrf(ranked_list: list[dict]) -> None:
        for rank, record in enumerate(ranked_list, start=1):
            key = record.get("profile_url") or record.get("name", "")
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in best_record:
                best_record[key] = record

    _apply_rrf(kw_results)
    _apply_rrf(st_results)
    _apply_rrf(sem_results)

    # Sort by RRF score descending
    sorted_keys = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    out = []
    for key in sorted_keys[:limit]:
        record = dict(best_record[key])
        record["score"] = rrf_scores[key]
        record["search_type"] = "hybrid"

        # Post-merge department filter (catches BM25s/Tantivy legs)
        if department:
            depts = record.get("departments", [])
            if isinstance(depts, list) and department not in depts:
                continue

        out.append(record)

    return out[:limit]
