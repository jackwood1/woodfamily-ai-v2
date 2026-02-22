"""Shared long-term memory (Chromadb). Used by Woody and Dashboard."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

# Default: repo root / chroma_db
_default = Path(__file__).resolve().parent.parent / "chroma_db"
MEMORY_DB_PATH = Path(os.environ.get("MEMORY_DB_PATH", str(_default)))

# Memory type: "short" = short-term, "long" = long-term (default)
# Weight: 1-10, default 5. Higher = more important, boosts ranking in search
# last_touched: ISO datetime. Refreshing a memory updates this; recently touched memories rank higher.


def _recency_boost(last_touched: Optional[str]) -> float:
    """Boost score for recently touched memories. 1.3x within 7 days, 1.1x within 30 days."""
    if not last_touched:
        return 1.0
    try:
        touched = datetime.fromisoformat(last_touched.replace("Z", "+00:00"))
        if touched.tzinfo is None:
            touched = touched.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - touched).days
        if delta <= 7:
            return 1.3
        if delta <= 30:
            return 1.1
    except (ValueError, TypeError):
        pass
    return 1.0


def _get_collection():
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        return None
    MEMORY_DB_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(MEMORY_DB_PATH), settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection("memory", metadata={"hnsw:space": "cosine"})


def memory_add(
    text: str,
    metadata: Optional[dict] = None,
    weight: int = 5,
    memory_type: str = "long",
) -> Optional[str]:
    """Store a fact in memory. weight 1-10, memory_type 'short' or 'long'. Returns memory id or None."""
    coll = _get_collection()
    if not coll:
        return None
    meta = dict(metadata) if metadata else {}
    meta["weight"] = max(1, min(10, weight))
    meta["type"] = "short" if memory_type == "short" else "long"
    meta["last_touched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if "source" not in meta:
        meta["source"] = "manual"
    mem_id = str(uuid.uuid4())
    coll.add(documents=[text], ids=[mem_id], metadatas=[meta])
    return mem_id


def memory_search(
    query: str,
    n: int = 5,
    memory_type: Optional[str] = None,
    use_weight: bool = True,
    with_ids: bool = False,
) -> Union[List[str], List[dict]]:
    """Search memory. memory_type filters to 'short' or 'long'. use_weight boosts by importance.
    If with_ids=True, returns list of {id, text}; otherwise returns list of str (backward compatible)."""
    coll = _get_collection()
    if not coll:
        return []
    where = {"type": memory_type} if memory_type in ("short", "long") else None
    # Fetch more if we'll re-rank by weight
    n_fetch = n * 3 if use_weight else n
    results = coll.query(
        query_texts=[query],
        n_results=min(n_fetch, 100),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]  # Chromadb always returns ids
    if not docs:
        return []
    if not use_weight or not dists:
        items = list(zip(ids, docs))[:n]
    else:
        # Re-rank: score = (1 - distance) * weight * recency_boost. Recently touched = more relevant.
        scored = []
        for d, m, dist, i in zip(docs, metas or [{}] * len(docs), dists, ids):
            w = (m or {}).get("weight", 5)
            boost = _recency_boost((m or {}).get("last_touched"))
            sim = 1.0 - dist
            scored.append((sim * w * boost, i, d))
        scored.sort(key=lambda x: -x[0])
        items = [(i, d) for _, i, d in scored[:n]]
    if with_ids:
        return [{"id": i, "text": d} for i, d in items]
    return [d for _, d in items]


def memory_refresh(query: str, bump_weight: bool = False) -> Optional[str]:
    """Refresh a memory by finding it with query. Updates last_touched; optionally bumps weight by 1.
    Returns the refreshed memory text, or None if not found."""
    coll = _get_collection()
    if not coll:
        return None
    results = coll.query(
        query_texts=[query],
        n_results=1,
        include=["documents", "metadatas"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]
    if not docs or not ids:
        return None
    doc, meta, doc_id = docs[0], (metas or [{}])[0] or {}, ids[0]
    meta = dict(meta)
    meta["last_touched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if bump_weight:
        w = meta.get("weight", 5)
        meta["weight"] = min(10, w + 1)
    coll.update(ids=[doc_id], metadatas=[meta])
    return doc


def memory_touch_on_search(query: str, n: int = 5) -> int:
    """Touch (refresh) memories returned by a search. Use when memories were successfully recalled.
    Returns count of memories touched."""
    coll = _get_collection()
    if not coll:
        return 0
    results = coll.query(
        query_texts=[query],
        n_results=n,
        include=["metadatas"],
    )
    ids = results.get("ids", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not ids:
        return 0
    touched = 0
    for doc_id, m in zip(ids, metas or [{}] * len(ids)):
        meta = dict(m or {})
        meta["last_touched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            coll.update(ids=[doc_id], metadatas=[meta])
            touched += 1
        except Exception:
            pass
    return touched


def memory_list(limit: int = 50) -> List[dict]:
    """List memories for dashboard display. Returns list of {id, text, metadata}."""
    coll = _get_collection()
    if not coll:
        return []
    try:
        data = coll.get(limit=limit, include=["documents", "metadatas"])
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or [{}] * len(docs)
        return [
            {"id": i, "text": d, "metadata": m or {}}
            for i, d, m in zip(ids, docs, metas)
        ]
    except Exception:
        return []


def memory_delete(memory_id: str) -> bool:
    """Delete a memory by id. Returns True if deleted."""
    coll = _get_collection()
    if not coll:
        return False
    try:
        coll.delete(ids=[memory_id])
        return True
    except Exception:
        return False


def memory_update(memory_id: str, weight: Optional[int] = None, memory_type: Optional[str] = None) -> bool:
    """Update a memory's weight and/or type. Returns True if updated."""
    coll = _get_collection()
    if not coll:
        return False
    try:
        data = coll.get(ids=[memory_id], include=["metadatas"])
        metas = data.get("metadatas") or []
        if not metas:
            return False
        meta = dict(metas[0] or {})
        if weight is not None:
            meta["weight"] = max(1, min(10, weight))
        if memory_type is not None:
            meta["type"] = "short" if memory_type == "short" else "long"
        meta["last_touched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        coll.update(ids=[memory_id], metadatas=[meta])
        return True
    except Exception:
        return False
