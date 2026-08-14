"""配置加载与校验（config.json + 环境变量）。"""

import json
import os
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "stt_engine": "auto",
    "tts_engine": "edge",
    "hotkey": "<ctrl>+<shift>+space",
    "allowlist": [],
    "denylist": [],
    "confirm_mode": "dangerous-only",
    "timeout_ms": 10000,
}

_KEY_ALIASES = {"whitelist": "allowlist", "blacklist": "denylist"}


def load_config(path: str | None = None) -> dict[str, Any]:
    """加载 config.json（缺省字段用默认值），校验后返回 dict。"""
    cfg: dict[str, Any] = dict(DEFAULT_CONFIG)
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config.json 顶层必须是对象")
        for k, v in data.items():
            cfg[_KEY_ALIASES.get(k, k)] = v
        if "confirm" in data and "confirm_mode" not in data:
            cfg["confirm_mode"] = "all" if data["confirm"] else "dangerous-only"
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict[str, Any]) -> None:
    """校验配置字段类型与枚举，非法即抛 ValueError。"""
    if cfg.get("stt_engine") not in ("auto", "local", "api"):
        raise ValueError("stt_engine 必须是 auto|local|api")
    if cfg.get("tts_engine") not in ("edge", "system"):
        raise ValueError("tts_engine 必须是 edge|system")
    if cfg.get("confirm_mode") not in ("dangerous-only", "all"):
        raise ValueError("confirm_mode 必须是 dangerous-only|all")
    if not isinstance(cfg.get("allowlist"), list) or not isinstance(cfg.get("denylist"), list):
        raise ValueError("allowlist/denylist 必须是数组")
    if not isinstance(cfg.get("timeout_ms"), int) or cfg.get("timeout_ms") <= 0:
        raise ValueError("timeout_ms 必须是正整数")
    if not isinstance(cfg.get("hotkey"), str) or not cfg.get("hotkey"):
        raise ValueError("hotkey 必须是非空字符串")
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "OPENAI_API_KEY"):
        val = os.environ.get(key)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"环境变量 {key} 必须是字符串")


def get_env_llm() -> tuple[str | None, str | None]:
    """读取可选 LLM 意图模式的 key 与 base_url。"""
    key = (os.environ.get("LLM_API_KEY") or "").strip() or None
    base = (os.environ.get("LLM_BASE_URL") or "").strip() or None
    return key, base
