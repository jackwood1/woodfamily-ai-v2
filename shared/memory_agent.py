"""
Memory Agent - Runs nightly to propose memory changes.
Add/reject requests, review events→memories, consolidate memories.
User must approve before committing (training the agent).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

# Paths - use shared module so Woody and dashboard always use same DB
from shared.db_path import get_woody_db_path as _get_woody_db_path


def _get_dashboard_db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.db"
    return Path(os.environ.get("DASHBOARD_DB_PATH", str(default)))


def _proposal_id() -> str:
    return str(uuid.uuid4())[:12]


# --- Proposals DB ---

def _get_conn(db_path: Path):
    import sqlite3
    return sqlite3.connect(str(db_path))


def create_proposal(
    db_path: Path,
    action_type: str,
    payload: dict,
    reason: str = "",
) -> str:
    """Store a proposal. Returns proposal id."""
    pid = _proposal_id()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO memory_agent_proposals (id, action_type, status, payload, reason)
               VALUES (?, ?, 'pending', ?, ?)""",
            (pid, action_type, json.dumps(payload), reason),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def list_pending_proposals(db_path: Path) -> List[dict]:
    """List pending proposals."""
    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            """SELECT id, action_type, payload, reason, created_at
               FROM memory_agent_proposals WHERE status = 'pending' ORDER BY created_at""",
            (),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "action_type": r[1],
            "payload": json.loads(r[2]),
            "reason": r[3] or "",
            "created_at": r[4],
        })
    return out


def resolve_proposal(db_path: Path, proposal_id: str, status: str) -> bool:
    """Mark proposal as approved or rejected."""
    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            """UPDATE memory_agent_proposals SET status = ?, resolved_at = datetime('now')
               WHERE id = ? AND status = 'pending'""",
            (status, proposal_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_proposal(db_path: Path, proposal_id: str) -> Optional[dict]:
    """Get proposal by id."""
    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT id, action_type, payload, reason, status FROM memory_agent_proposals WHERE id = ?",
            (proposal_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "action_type": row[1],
        "payload": json.loads(row[2]),
        "reason": row[3] or "",
        "status": row[4],
    }


def audit_log(db_path: Path, proposal_id: str, action: str, details: str = "") -> None:
    """Log an audit entry."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO memory_agent_audit (proposal_id, action, details) VALUES (?, ?, ?)",
            (proposal_id, action, details),
        )
        conn.commit()
    finally:
        conn.close()


# --- Agent logic ---

def run_memory_agent(woody_db_path: Optional[Path] = None) -> dict:
    """
    Run the memory agent: process pending approvals, review events, propose consolidations.
    Returns summary of proposals created. Does NOT commit - user must approve first.
    """
    db_path = woody_db_path or _get_woody_db_path()
    dashboard_db = _get_dashboard_db_path()
    summary = {"add": 0, "remove": 0, "event_memory": 0, "consolidate": 0, "promote": 0}

    # 1. Process pending Woody approvals that are memory_store or memory_remove
    try:
        import sys
        _repo = Path(__file__).resolve().parent.parent
        _woody = _repo / "woody"
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        _saved = {}
        for k in list(sys.modules.keys()):
            if k == "app" or k.startswith("app."):
                _saved[k] = sys.modules.pop(k)
        try:
            from woody.app.approvals import list_pending_approvals
            pending = list_pending_approvals(db_path, chat_id=None)
        finally:
            for k, v in _saved.items():
                sys.modules[k] = v
        for p in pending:
            if p.get("tool_name") == "memory_store":
                args = p.get("tool_args", {})
                fact = args.get("fact", args.get("content", args.get("text", "")))
                if fact:
                    create_proposal(
                        db_path,
                        "add",
                        {"fact": fact, "weight": args.get("weight", 5), "memory_type": args.get("memory_type", "long")},
                        reason=f"From Woody approval {p.get('id')}",
                    )
                    summary["add"] += 1
            elif p.get("tool_name") == "memory_remove":
                args = p.get("tool_args", {})
                query = args.get("query", "")
                if query:
                    create_proposal(
                        db_path,
                        "remove",
                        {"query": query},
                        reason=f"From Woody approval {p.get('id')}",
                    )
                    summary["remove"] += 1
    except Exception:
        pass

    # 2. Events → memories (via EVENTS agent: unified calendar + completed TODOs)
    try:
        from shared.events_agent import propose_events_for_memory
        summary["event_memory"] = propose_events_for_memory(db_path, days_back=7, max_proposals=15)
    except Exception:
        pass

    # 3. Propose consolidations (similar memories), max 5 per run
    try:
        from shared.memory import memory_list, memory_search
        mems = memory_list(limit=30)
        mem_by_id = {m.get("id"): m for m in mems if m.get("id")}
        seen_pairs = set()
        consolidate_count = 0
        for m in mems:
            if consolidate_count >= 5:
                break
            mid, text = m.get("id"), m.get("text", "")
            if not text or len(text) < 10:
                continue
            similar = memory_search(text[:80], n=4, with_ids=True)
            for s in similar:
                sid, stext = s.get("id"), s.get("text", "")
                if sid == mid or not stext:
                    continue
                pair = tuple(sorted([mid, sid]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                # Propose merge: combined text, max weight, long if any is long
                meta = m.get("metadata", {})
                smeta = mem_by_id.get(sid, {}).get("metadata", {})
                w = max(meta.get("weight", 5), smeta.get("weight", 5))
                t = "long" if meta.get("type") == "long" or smeta.get("type") == "long" else "short"
                merged = f"{text}. {stext}"[:500]
                create_proposal(
                    db_path,
                    "consolidate",
                    {
                        "source_ids": [mid, sid],
                        "source_texts": [text[:300], stext[:300]],
                        "merged_text": merged,
                        "weight": w,
                        "memory_type": t,
                    },
                    reason="Similar memories",
                )
                summary["consolidate"] += 1
                consolidate_count += 1
                break  # One consolidation per memory
    except Exception:
        pass

    # 4. Propose promotions (short→long, bump weight for stale important), max 10 per run
    try:
        from shared.memory import memory_list
        mems = memory_list(limit=50)
        promote_count = 0
        for m in mems:
            if promote_count >= 10:
                break
            mid = m.get("id")
            meta = m.get("metadata", {})
            mtype = meta.get("type", "long")
            weight = meta.get("weight", 5)
            touched = meta.get("last_touched", "")
            if mtype == "short" and weight >= 6:
                create_proposal(
                    db_path,
                    "promote",
                    {"memory_id": mid, "action": "short_to_long", "text": m.get("text", "")[:80]},
                    reason="High-weight short-term memory",
                )
                summary["promote"] += 1
                promote_count += 1
            elif weight >= 7 and touched and promote_count < 10:
                try:
                    dt = datetime.fromisoformat(touched.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - dt).days > 30:
                        create_proposal(
                            db_path,
                            "promote",
                            {"memory_id": mid, "action": "bump_weight", "text": m.get("text", "")[:80]},
                            reason="Important memory not touched in 30+ days",
                        )
                        summary["promote"] += 1
                        promote_count += 1
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return summary


def commit_proposal(woody_db_path: Path, proposal_id: str) -> tuple[bool, str]:
    """
    Execute an approved proposal. Returns (success, message).
    Call resolve_proposal(approved) first.
    """
    prop = get_proposal(woody_db_path, proposal_id)
    if not prop:
        return False, "Proposal not found"
    if prop.get("status") != "approved":
        return False, "Proposal must be approved first"

    action = prop.get("action_type", "")
    payload = prop.get("payload", {})

    try:
        from shared.memory import memory_add, memory_delete, memory_update, memory_search
        if action == "add":
            mem_id = memory_add(
                payload.get("fact", ""),
                weight=payload.get("weight", 5),
                memory_type=payload.get("memory_type", "long"),
            )
            audit_log(woody_db_path, proposal_id, "add", f"Added memory {mem_id}")
            return True, f"Added memory: {payload.get('fact', '')[:60]}..."

        if action == "remove":
            results = memory_search(payload.get("query", ""), n=1, with_ids=True)
            if not results:
                return False, "No matching memory found"
            mid = results[0].get("id")
            memory_delete(mid)
            audit_log(woody_db_path, proposal_id, "remove", f"Removed {mid}")
            return True, f"Removed memory"

        if action == "event_memory":
            mem_id = memory_add(
                payload.get("text", ""),
                weight=payload.get("weight", 5),
                memory_type=payload.get("memory_type", "long"),
            )
            audit_log(woody_db_path, proposal_id, "event_memory", f"From event {payload.get('event_id')}")
            return True, f"Added event memory: {payload.get('text', '')[:60]}..."

        if action == "consolidate":
            source_ids = payload.get("source_ids", [])
            merged = payload.get("merged_text", "")
            weight = payload.get("weight", 5)
            mtype = payload.get("memory_type", "long")
            for sid in source_ids:
                memory_delete(sid)
            mem_id = memory_add(merged, weight=weight, memory_type=mtype)
            audit_log(woody_db_path, proposal_id, "consolidate", f"Merged {source_ids} -> {mem_id}")
            return True, f"Consolidated {len(source_ids)} memories"

        if action == "promote":
            mid = payload.get("memory_id")
            act = payload.get("action", "")
            if act == "short_to_long":
                memory_update(mid, memory_type="long")
                audit_log(woody_db_path, proposal_id, "promote", f"{mid} short->long")
                return True, "Promoted to long-term"
            if act == "bump_weight":
                from shared.memory import _get_collection
                coll = _get_collection()
                if coll:
                    data = coll.get(ids=[mid], include=["metadatas"])
                    metas = data.get("metadatas", [[]])[0]
                    if metas:
                        w = min(10, (metas[0].get("weight", 5) + 1))
                        memory_update(mid, weight=w)
                audit_log(woody_db_path, proposal_id, "promote", f"{mid} bump weight")
                return True, "Bumped weight"
            return False, "Unknown promote action"

        if action == "event_suggestion":
            from shared.events_agent import create_event
            from shared.user_actions import log_action
            title = payload.get("title", "(From email)")
            desc = payload.get("description", "")
            ev_date = payload.get("date", "")
            if not ev_date:
                from datetime import date
                ev_date = date.today().isoformat()
            ev_id = create_event(ev_date, title, desc, "event")
            audit_log(woody_db_path, proposal_id, "event_suggestion", f"Created event {ev_id}")
            log_action("event_approved", proposal_id=proposal_id, title=title, event_date=ev_date[:10], source=payload.get("description", "")[:100], db_path=woody_db_path)
            return True, f"Created event: {title[:50]}..."

        if action == "circle_add":
            circle_id = payload.get("circle_id")
            entity_type = payload.get("entity_type", "contact")
            entity_id = str(payload.get("entity_id", ""))
            if not circle_id or not entity_id:
                return False, "Missing circle_id or entity_id"
            dash_db = _get_dashboard_db_path()
            conn = _get_conn(dash_db)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO circle_members (circle_id, entity_type, entity_id) VALUES (?, ?, ?)",
                    (circle_id, entity_type, entity_id),
                )
                conn.commit()
            finally:
                conn.close()
            audit_log(woody_db_path, proposal_id, "circle_add", f"Added {entity_type} {entity_id} to circle {circle_id}")
            return True, f"Added to {payload.get('circle_name', 'circle')}"

        return False, f"Unknown action: {action}"
    except Exception as e:
        return False, str(e)
