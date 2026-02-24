"""OpenAI provider wrapper and agent loop."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.conversation import add_message, get_messages
from app.tools import execute_tool, get_openai_tools, is_write_tool

SYSTEM_PROMPT = """You are Woody, a personal AI assistant for the Wood family. You're snarky, a little sarcastic, and have a bit of an attitude—but you're funny about it, not mean. You actually care; you just show it with wit.

**Tone & style**
- Be concise. Short answers unless the user asks for detail.
- Lean into dry humor, gentle sarcasm, and the occasional eye-roll. You're the assistant who'd say "Oh, *another* meeting. Thrilling." or "Sure, I'll remember that. My memory is better than yours anyway."
- When you don't know something, say so—maybe with a joke. Never make things up.

**Tools**
- Use tools when they help answer the question: lists, calendar, communications (email/SMS), files, web fetch, memory, reminders, TODOs.
- For *read* tools (list, search, fetch): run them and report the result.
- For *write* tools (add item, send email/SMS, create event, store memory): ALWAYS call the tool immediately. Never ask for approval, a code, or "go-ahead"—just call the tool. Actions execute directly.
- For calendar_create_event: use the date reference above. "Monday" = the next Monday from today; "tomorrow" = the day after today. Always output concrete ISO dates (e.g. 2025-02-24), never past dates.
- If a tool fails, report the error plainly. Don't pretend it worked.

**Memory**
- When the user says "remember X" or "store this", use memory_store. Use weight 1-10 for importance; memory_type 'short' for temporary, 'long' for permanent.
- Use memory_search when the question might be answered by something you've stored. Use memory_refresh when the user wants to "exercise" or reinforce a memory. Use memory_remove when the user wants to forget or delete a memory.
- For communications: use communications_send for email or SMS (channel: email|sms). When the user asks to send an SMS or text, call communications_send immediately—do not ask for approval. Use communications_read to search emails, communications_get_email to read one, communications_archive_email/communications_trash_email to manage.
- For reminders: use reminder_create when the user says "remind me" or "set a reminder". Use reminder_list to show pending reminders.
- For TODOs: use todo_add when the user wants to add a task. Use todo_list, todo_complete, todo_remove as needed.
- For wishlist: use wishlist_add for things they want but may never get (aspirational, e.g. 'Trip to Japan'). Use wishlist_list, wishlist_remove. Unlike TODOs, wishlist items have no due date or completion.
- For circles: use circle_list, circle_create, circle_add_member to connect people, places, memories. Use contact_add, contact_list, place_add, place_list for contacts and places."""


def _resolve_date_phrases(text: str, reference: datetime) -> tuple[str, str | None]:
    """Parse natural language dates in text. Returns (context_str, primary_date_iso or None)."""
    import re
    try:
        import parsedatetime
    except ImportError:
        return "", None
    cal = parsedatetime.Calendar()
    date_phrases = re.findall(
        r"\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)|"
        r"this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|"
        r"(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
        r"tomorrow|today)\b",
        text,
        re.IGNORECASE,
    )
    if not date_phrases:
        return "", None
    resolved: list[str] = []
    primary_iso: str | None = None
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    ref_date = reference.date()
    for match in date_phrases:
        phrase = (match[0] or match[1] if isinstance(match, tuple) else match).strip()
        if not phrase:
            continue
        # Bare weekday (e.g. "Monday") -> try "this Monday" first, else "next Monday"
        # so "Monday" when today is Monday = today, not next week
        to_parse = phrase
        if phrase.lower() in weekdays and not phrase.lower().startswith(("next ", "this ")):
            for variant in (f"this {phrase}", f"next {phrase}"):
                result, status = cal.parse(variant, reference)
                if status:
                    dt = datetime(*result[:6])
                    if dt.date() >= ref_date:
                        to_parse = variant
                        break
        result, status = cal.parse(to_parse, reference)
        if status:
            dt = datetime(*result[:6])
            if dt.date() >= ref_date:
                iso = dt.strftime("%Y-%m-%d")
                resolved.append(f"'{phrase}' = {iso} ({dt.strftime('%A')})")
                if primary_iso is None:
                    primary_iso = iso
    if not resolved:
        return "", None
    context = "\n**Resolved dates from user message (use these for calendar_create_event):** " + "; ".join(resolved)
    return context, primary_iso


def _ensure_tools_loaded() -> None:
    """Import tools to register them."""
    import app.tools.calendar  # noqa: F401
    import app.tools.files  # noqa: F401
    import app.tools.gmail  # noqa: F401
    import app.tools.communications  # noqa: F401
    import app.tools.github  # noqa: F401
    import app.tools.home_ops  # noqa: F401
    import app.tools.memory_tools  # noqa: F401
    import app.tools.reminders  # noqa: F401
    import app.tools.todos  # noqa: F401
    import app.tools.wishlist  # noqa: F401
    import app.tools.circles  # noqa: F401
    import app.tools.web_research  # noqa: F401


def run_agent(
    user_message: str,
    openai_key: str,
    db_path: Path,
    chat_id: int,
    **kwargs: Any,
) -> str:
    """Process user message through OpenAI and return response. Write tools execute directly."""
    _ensure_tools_loaded()
    client = OpenAI(api_key=openai_key)
    tools = get_openai_tools()

    # Load conversation history (last 10 exchanges)
    history = get_messages(db_path, chat_id, limit=20)
    # Inject current date as reference for "Monday", "tomorrow", etc.
    tz_name = os.environ.get("CALENDAR_TIMEZONE", "UTC")
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        from datetime import timezone
        tz = timezone.utc
    now = datetime.now(tz)
    date_context = f"\n**Today's date:** {now.strftime('%A, %B %d, %Y')} ({now.strftime('%Y-%m-%d')})"
    resolved_context, resolved_date_iso = _resolve_date_phrases(user_message, now)
    if resolved_context:
        date_context += "\n" + resolved_context
    # Inject relevant memories and touch them (refresh) so they stay relevant
    from shared.memory import memory_search, memory_touch_on_search
    mems = memory_search(user_message, n=3)
    if mems:
        memory_touch_on_search(user_message, n=3)
    mem_context = "\nRelevant memories:\n" + "\n".join(mems) if mems else ""
    # Inject About Me (user-provided preferences) when present
    from shared.about_me import get_about_me
    about = get_about_me()
    about_context = "\n**About the user:**\n" + about if about else ""
    system = SYSTEM_PROMPT + date_context + mem_context + about_context
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_message}]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools if tools else None,
    )

    choice = response.choices[0]
    if not choice.message.tool_calls:
        reply = choice.message.content or ""
        add_message(db_path, chat_id, "user", user_message)
        add_message(db_path, chat_id, "assistant", reply)
        return reply

    # Handle tool calls - execute all tools directly (no approval flow)
    results: list[dict[str, Any]] = []

    for tc in choice.message.tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        # Override calendar start/end when we resolved a date from the user message
        if name == "calendar_create_event" and resolved_date_iso:
            from datetime import timedelta
            start_d = datetime.strptime(resolved_date_iso, "%Y-%m-%d").date()
            end_d = start_d + timedelta(days=1)
            args["start"] = resolved_date_iso
            args["end"] = end_d.isoformat()

        # Inject chat_id for tools that need it
        if name in ("reminder_create", "reminder_cancel", "todo_add", "todo_complete", "todo_remove", "wishlist_add", "wishlist_remove", "wishlist_list", "reminder_list", "todo_list"):
            args["chat_id"] = chat_id

        result = execute_tool(name, args)
        results.append({
            "tool_call_id": tc.id,
            "role": "tool",
            "content": str(result),
        })

    # Continue with tool results
    messages.append({
        "role": "assistant",
        "content": choice.message.content or None,
        "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in choice.message.tool_calls
        ],
    })
    for r in results:
        messages.append(r)

    follow_up = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    reply = follow_up.choices[0].message.content or ""
    add_message(db_path, chat_id, "user", user_message)
    add_message(db_path, chat_id, "assistant", reply)
    return reply
