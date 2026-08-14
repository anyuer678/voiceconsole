"""意图解析：规则 + 落字典（无 LLM key 也能跑）。"""

import re
from dataclasses import dataclass, field

ACTION_EXECUTE_CLI = "execute_cli"
ACTION_FIND_FILE = "find_file"
ACTION_OPEN_FOLDER = "open_folder"
ACTION_QUIT = "quit"
ACTION_HELP = "help"
ACTION_UNKNOWN = "unknown"


@dataclass
class Intent:
    raw_text: str
    action: str
    args: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0


_VERB_RULES = [
    (re.compile(r"^(?:打开|开启|open)\s*(.+)$", re.IGNORECASE), ACTION_OPEN_FOLDER, "path"),
    (re.compile(r"^(?:找|查找|搜索|搜寻|find|search)\s*(.+)$", re.IGNORECASE), ACTION_FIND_FILE, "pattern"),
    (re.compile(r"^(?:执行|运行|run)\s+(.+)$", re.IGNORECASE), ACTION_EXECUTE_CLI, "command"),
]

_COMMAND_HINTS = (
    "ls", "dir", "cd", "cat", "pwd", "git", "where", "type",
    "systeminfo", "tasklist", "del", "copy", "move",
)

_QUIT_WORDS = ("退出", "再见", "拜拜", "quit", "exit", "q")
_HELP_WORDS = ("帮助", "help", "怎么用", "?")


def parse_intent(text: str) -> Intent:
    """把一句话解析为 Intent；规则匹配失败返回 action=unknown。"""
    raw = (text or "").strip()
    if not raw:
        return Intent(raw_text=raw, action=ACTION_UNKNOWN)
    low = raw.lower()
    if low in _QUIT_WORDS:
        return Intent(raw_text=raw, action=ACTION_QUIT, confidence=0.95)
    if low in _HELP_WORDS:
        return Intent(raw_text=raw, action=ACTION_HELP, confidence=0.95)
    for pattern, action, arg in _VERB_RULES:
        m = pattern.match(raw)
        if m:
            return Intent(raw_text=raw, action=action, args={arg: m.group(1).strip()}, confidence=0.9)
    first = low.split()[0] if low.split() else ""
    if first in _COMMAND_HINTS:
        return Intent(raw_text=raw, action=ACTION_EXECUTE_CLI, args={"command": raw}, confidence=0.9)
    return Intent(raw_text=raw, action=ACTION_UNKNOWN)


def map_to_tool(intent: Intent) -> tuple[str, dict] | None:
    """Intent -> (mcp_tool_name, tool_args)；不支持的 action 返回 None。"""
    if intent.action == ACTION_EXECUTE_CLI:
        return ("run_cli", {"command": intent.args.get("command", "")})
    if intent.action == ACTION_FIND_FILE:
        return ("find_file", {"pattern": intent.args.get("pattern", ""), "directory": "."})
    if intent.action == ACTION_OPEN_FOLDER:
        return ("open_folder", {"path": intent.args.get("path", "")})
    return None


def is_affirmative(text: str) -> bool:
    """确认应答判断："是/对/yes" 等。"""
    low = (text or "").strip().lower()
    return low in ("是", "对", "好的", "确认", "可以", "yes", "y", "yeah", "ok", "okay", "确定")
