"""RAG grounding for the judge.

Before scoring a flow, retrieve the relevant documented expected-behavior notes
and hand them to the judge so its verdict is grounded in stated rules. Two
interchangeable backends sit behind one ``VectorStore`` protocol:

- ``PgVectorStore`` — Postgres + pgvector, the spec's intended backend (scales,
  persists across runs).
- ``InMemoryVectorStore`` — no infrastructure; used for offline tests and quick
  local runs.

Embeddings are injected as a callable, so retrieval can be tested with a
deterministic fake embedder (no API key, no network).
"""

from __future__ import annotations

import math
from typing import Awaitable, Callable, Protocol

from .expected_behavior import EXPECTED_BEHAVIOR, SpecDoc
from .schema import FlowSpec

# An embedder maps a batch of texts to a batch of vectors.
EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore(Protocol):
    def add(self, docs: list[SpecDoc], vectors: list[list[float]]) -> None: ...
    def search(self, query_vec: list[float], k: int) -> list[SpecDoc]: ...


class InMemoryVectorStore:
    """Cosine-similarity store kept in process memory."""

    def __init__(self) -> None:
        self._docs: list[SpecDoc] = []
        self._vecs: list[list[float]] = []

    def add(self, docs: list[SpecDoc], vectors: list[list[float]]) -> None:
        self._docs.extend(docs)
        self._vecs.extend(vectors)

    def search(self, query_vec: list[float], k: int) -> list[SpecDoc]:
        scored = sorted(
            zip(self._docs, self._vecs),
            key=lambda dv: _cosine(query_vec, dv[1]),
            reverse=True,
        )
        return [doc for doc, _ in scored[:k]]


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class PgVectorStore:
    """Postgres + pgvector backend. Requires the optional ``[rag]`` extras."""

    def __init__(self, dsn: str, dim: int = 1536) -> None:
        import psycopg  # local import so the core package has no hard dep

        self.dim = dim
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # If the table exists with a different embedding dimension (e.g. left by
        # a test or a model change), recreate it rather than fail on insert.
        existing = self._conn.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a JOIN pg_class c ON a.attrelid = c.oid "
            "WHERE c.relname = 'spec_docs' AND a.attname = 'embedding' AND a.attnum > 0"
        ).fetchone()
        if existing is not None and existing[0] != f"vector({dim})":
            self._conn.execute("DROP TABLE IF EXISTS spec_docs")
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS spec_docs ("
            f"  id SERIAL PRIMARY KEY,"
            f"  flow TEXT NOT NULL,"
            f"  text TEXT NOT NULL,"
            f"  embedding vector({dim}))"
        )

    def add(self, docs: list[SpecDoc], vectors: list[list[float]]) -> None:
        with self._conn.cursor() as cur:
            for doc, vec in zip(docs, vectors):
                cur.execute(
                    "INSERT INTO spec_docs (flow, text, embedding) "
                    "VALUES (%s, %s, %s::vector)",
                    (doc.flow, doc.text, _vec_literal(vec)),
                )

    def search(self, query_vec: list[float], k: int) -> list[SpecDoc]:
        rows = self._conn.execute(
            "SELECT flow, text FROM spec_docs "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (_vec_literal(query_vec), k),
        ).fetchall()
        return [SpecDoc(flow=r[0], text=r[1]) for r in rows]

    def clear(self) -> None:
        self._conn.execute("TRUNCATE spec_docs")

    def close(self) -> None:
        self._conn.close()


async def index_expected_behavior(
    store: VectorStore, embed: EmbedFn, docs: list[SpecDoc] | None = None
) -> None:
    """Embed the expected-behavior notes and load them into the store."""
    docs = docs or EXPECTED_BEHAVIOR
    vectors = await embed([d.text for d in docs])
    store.add(docs, vectors)


async def grounded_contexts(
    flows: list[FlowSpec],
    store: VectorStore,
    embed: EmbedFn,
    *,
    k: int = 2,
) -> dict[str, str]:
    """Pre-compute retrieved context per flow (sync-usable in the graph).

    The graph's judge hook is synchronous, but embedding/retrieval is async, so
    we resolve all contexts up front (flows are known) and return a plain dict.
    """
    queries = [f.goal for f in flows]
    query_vecs = await embed(queries)
    contexts: dict[str, str] = {}
    for flow_spec, qv in zip(flows, query_vecs):
        docs = store.search(qv, k)
        contexts[flow_spec.flow] = "\n".join(f"- {d.text}" for d in docs)
    return contexts
