"""Tests for RAG grounding.

Retrieval is validated with a deterministic bag-of-words fake embedder, so no
API key is needed. The InMemory test always runs; the pgvector test runs only
if a Postgres+pgvector instance is reachable (it validates the real SQL path
using the same fake embeddings).
"""

from __future__ import annotations

import re

import pytest

from agentic_qa import rag
from agentic_qa.expected_behavior import EXPECTED_BEHAVIOR
from agentic_qa.flows import select as select_flows

VOCAB = ["transfer", "bill", "payment", "payee", "open", "savings", "account",
         "loan", "transaction", "transactions", "find", "search", "balance", "amount"]


async def fake_embed(texts: list[str]) -> list[list[float]]:
    """Count VOCAB word occurrences -> a deterministic, key-free embedding."""
    vecs = []
    for t in texts:
        words = re.findall(r"[a-z]+", t.lower())
        vecs.append([float(words.count(w)) for w in VOCAB])
    return vecs


async def test_inmemory_retrieves_relevant_doc():
    store = rag.InMemoryVectorStore()
    await rag.index_expected_behavior(store, fake_embed)

    transfer = select_flows(["transfer"])
    contexts = await rag.grounded_contexts(transfer, store, fake_embed, k=1)
    assert "transfer" in contexts
    assert "reduce the source account balance" in contexts["transfer"]


async def test_inmemory_billpay_query_ranks_billpay_doc():
    store = rag.InMemoryVectorStore()
    await rag.index_expected_behavior(store, fake_embed)
    billpay = select_flows(["billpay"])
    contexts = await rag.grounded_contexts(billpay, store, fake_embed, k=1)
    assert "Bill Payment Complete" in contexts["billpay"]


@pytest.mark.slow
async def test_pgvector_roundtrip():
    psycopg = pytest.importorskip("psycopg")
    dsn = "postgresql://postgres:postgres@localhost:5433/agentic_qa"
    try:
        psycopg.connect(dsn).close()
    except Exception:
        pytest.skip("pgvector Postgres not reachable on :5433")

    store = rag.PgVectorStore(dsn, dim=len(VOCAB))
    store.clear()
    await rag.index_expected_behavior(store, fake_embed)

    transfer = select_flows(["transfer"])
    contexts = await rag.grounded_contexts(transfer, store, fake_embed, k=1)
    store.close()
    assert "reduce the source account balance" in contexts["transfer"]
