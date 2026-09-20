"""持久审计：JSONL 追加写，默认落在用户目录 ~/.voiceconsole/audit.jsonl。"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def default_audit_path() -> str:
    override = os.environ.get("VOICECONSOLE_AUDIT_PATH", "").strip()
    if override:
        return override
    return str(Path.home() / ".voiceconsole" / "audit.jsonl")


def append_audit(record: dict[str, Any], path: str | None = None) -> str | None:
    """追加一条审计记录；失败返回 None，不抛出（审计不应打断主流程）。"""
    target = path or default_audit_path()
    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        payload.setdefault("ts", time.time())
        line = json.dumps(payload, ensure_ascii=False)
        with _lock:
            with open(target, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return target
    except OSError:
        return None
