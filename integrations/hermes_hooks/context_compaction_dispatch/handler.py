"""Hermes gateway hook: dispatch successful context-compression rollovers.

Install this directory under ``~/.hermes/hooks/``. Hermes loads it at
``gateway:startup`` and it monkey-patches the live compression function in the
running gateway process. The wrapper is deliberately fail-closed/no-op unless
``HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED`` is truthy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_PATCH_LOCK = threading.Lock()
_PATCHED = False
_ORIGINAL = None


def handle(event_type: str, context: dict[str, Any] | None = None) -> None:
    if event_type != "gateway:startup":
        return
    install_patch()


def install_patch() -> bool:
    """Patch ``agent.conversation_compression.compress_context`` once."""
    global _PATCHED, _ORIGINAL
    with _PATCH_LOCK:
        if _PATCHED:
            return False
        try:
            from agent import conversation_compression as cc
        except Exception:
            return False
        original = cc.compress_context
        _ORIGINAL = original

        def _wrapped_compress_context(agent: Any, messages: list, system_message: str, **kwargs: Any):
            old_session_id = str(getattr(agent, "session_id", "") or "")
            result = original(agent, messages, system_message, **kwargs)
            try:
                new_session_id = str(getattr(agent, "session_id", "") or "")
                if old_session_id and new_session_id and old_session_id != new_session_id:
                    _dispatch(agent, messages, result, old_session_id, new_session_id)
            except Exception as exc:
                # Hooks must never break live compression.
                try:
                    print(f"[hasystem-context-compaction] dispatch skipped: {exc}", file=sys.stderr, flush=True)
                except Exception:
                    pass
            return result

        cc.compress_context = _wrapped_compress_context
        _PATCHED = True
        print("[hasystem-context-compaction] installed compression lifecycle wrapper", flush=True)
        return True


def _dispatch(agent: Any, messages: list, result: Any, old_session_id: str, new_session_id: str) -> None:
    if not _enabled(os.environ.get("HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED")):
        return
    payload = _payload(agent, messages, result, old_session_id, new_session_id)
    command = os.environ.get("HERMES_CONTEXT_COMPACTION_HOOK_COMMAND", "").strip()
    if command:
        proc = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            shell=True,
            capture_output=True,
            timeout=float(os.environ.get("HERMES_CONTEXT_COMPACTION_HOOK_TIMEOUT", "30")),
            check=False,
        )
    else:
        proc = subprocess.run(
            [sys.executable, "-m", "hasystem.commands.context_compression_hook"],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=float(os.environ.get("HERMES_CONTEXT_COMPACTION_HOOK_TIMEOUT", "30")),
            check=False,
        )
    log_path = os.environ.get("HERMES_CONTEXT_COMPACTION_HOOK_LOG", "").strip()
    if log_path:
        _append_jsonl(log_path, {"payload": payload, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    if proc.returncode != 0:
        print(
            f"[hasystem-context-compaction] hook command failed rc={proc.returncode}: {proc.stderr[:500]}",
            file=sys.stderr,
            flush=True,
        )


def _payload(agent: Any, messages: list, result: Any, old_session_id: str, new_session_id: str) -> dict[str, Any]:
    source = _source_from_agent(agent)
    compressed_messages = result[0] if isinstance(result, tuple) and result else []
    summary = _compression_summary(compressed_messages)
    return {
        "hook_event_name": "context.compaction",
        "platform": source.get("platform") or getattr(agent, "platform", None) or "unknown",
        "discord": {
            "guild_id": source.get("guild_id") or os.environ.get("HERMES_SESSION_GUILD_ID", ""),
            "channel_id": source.get("parent_chat_id") or source.get("chat_id") or getattr(agent, "chat_id", None),
            "thread_id": source.get("thread_id") or getattr(agent, "thread_id", None),
        },
        "session": {"old_id": old_session_id, "new_id": new_session_id},
        "repository": os.environ.get("HASYSTEM_REPO_HINT") or _repo_hint(),
        "latest_goal": os.environ.get("HASYSTEM_LATEST_GOAL") or _latest_user_message(messages),
        "active_issue": _active_issue_from_env(),
        "compression": {
            "summary": os.environ.get("HASYSTEM_COMPRESSION_SUMMARY") or summary,
            "handoff_context": os.environ.get("HASYSTEM_HANDOFF_CONTEXT") or _handoff_context(messages),
        },
    }


def _source_from_agent(agent: Any) -> dict[str, Any]:
    source = getattr(agent, "_hasystem_gateway_source", None)
    if isinstance(source, dict):
        return source
    return {
        "platform": getattr(agent, "platform", None),
        "chat_id": getattr(agent, "chat_id", None),
        "thread_id": getattr(agent, "thread_id", None),
        "user_id": getattr(agent, "user_id", None),
    }


def _active_issue_from_env() -> dict[str, Any] | None:
    number = os.environ.get("HASYSTEM_ACTIVE_ISSUE_NUMBER", "").strip()
    title = os.environ.get("HASYSTEM_ACTIVE_ISSUE_TITLE", "").strip()
    if not number or not title:
        return None
    try:
        parsed_number = int(number)
    except ValueError:
        return None
    labels = [item.strip() for item in os.environ.get("HASYSTEM_ACTIVE_ISSUE_LABELS", "").split(",") if item.strip()]
    return {"number": parsed_number, "title": title, "labels": labels}


def _compression_summary(compressed_messages: Any) -> str:
    if not isinstance(compressed_messages, list):
        return ""
    for item in compressed_messages:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()[:4000]
    return ""


def _latest_user_message(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()[:1000]
    return ""


def _handoff_context(messages: Any) -> str:
    latest = _latest_user_message(messages)
    return f"Live Hermes compression lifecycle captured during gateway turn. Latest user message: {latest}" if latest else "Live Hermes compression lifecycle captured during gateway turn."


def _repo_hint() -> str:
    cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
    parts = Path(cwd).parts
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return cwd


def _append_jsonl(path: str, record: dict[str, Any]) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
