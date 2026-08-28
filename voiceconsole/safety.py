"""命令安全门：白名单/黑名单判断 + 线程安全的确认状态机。"""

import re
import threading
import time
import uuid

DENY_PREFIXES = (
    "rm ", "shred", " dd ", "mkfs", "curl ", "wget ", "sudo ", "mv ", "del ",
    "bash ", "shutdown", "passwd", "chpasswd", "net user",
)
ALLOW_PREFIXES = (
    "ls", "cd", "git status", "git log", "pwd", "where",
    "systeminfo", "tasklist", "dir", "ping", "ps", "top",
)
CONFIRM_TIMEOUT_S = 30

_SHELL_METACHARS = (";", "&&", "||", "|", ">", "<", "`", "$(", "&")


class SafetyVerdict:
    ALLOWED = "allowed"
    DENIED = "denied"
    NEEDS_CONFIRM = "needs_confirm"


class ToolDeniedError(RuntimeError):
    """命令被安全门拒绝时抛出的异常。"""


class _ConfirmEntry:
    __slots__ = ("confirm_id", "tool", "args", "state", "deadline")

    def __init__(self, confirm_id: str, tool: str, args: dict):
        self.confirm_id = confirm_id
        self.tool = tool
        self.args = args
        self.state = "pending"
        self.deadline = time.time() + CONFIRM_TIMEOUT_S


class SafetyGate:
    def __init__(
        self,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        confirm_mode: str = "dangerous-only",
        confirm_timeout_s: float = CONFIRM_TIMEOUT_S,
    ):
        self._allow = list(ALLOW_PREFIXES) + [p for p in (allowlist or []) if p]
        self._deny = list(DENY_PREFIXES) + [p for p in (denylist or []) if p]
        self._confirm_mode = confirm_mode
        self._confirm_timeout_s = confirm_timeout_s
        self._lock = threading.RLock()
        self._pending: dict[str, _ConfirmEntry] = {}

    def check_command(self, cmd: str) -> str:
        """判定命令：allowed | denied | needs_confirm。"""
        c = (cmd or "").strip()
        if not c:
            return SafetyVerdict.DENIED
        # 归一化连续空白为单空格，防止双空格绕过前缀匹配
        c = re.sub(r"\s+", " ", c)
        low = c.lower()
        if any(ch in low for ch in _SHELL_METACHARS):
            return SafetyVerdict.DENIED
        if self._match_prefix(low, self._deny, allow_dot=True):
            return SafetyVerdict.DENIED
        if self._confirm_mode == "all":
            return SafetyVerdict.NEEDS_CONFIRM
        if self._match_prefix(low, self._allow):
            return SafetyVerdict.ALLOWED
        return SafetyVerdict.NEEDS_CONFIRM

    def needs_confirm(self, cmd: str) -> bool:
        """命令是否需要二阶段确认。"""
        return self.check_command(cmd) == SafetyVerdict.NEEDS_CONFIRM

    def pending_ids(self) -> list[str]:
        with self._lock:
            now = time.time()
            self._pending = {k: v for k, v in self._pending.items() if v.deadline > now}
            return list(self._pending.keys())

    @staticmethod
    def _match_prefix(low_cmd: str, prefixes: tuple[str, ...], allow_dot: bool = False) -> bool:
        """前缀匹配，要求边界为空白/串尾（deny 额外允许 '.'），避免 rm 误伤 rmdir。"""
        for p in prefixes:
            lp = p.strip().lower()
            if not lp:
                continue
            if low_cmd == lp or low_cmd.startswith(lp + " ") or low_cmd.startswith(lp + "\t") or (
                allow_dot and low_cmd.startswith(lp + ".")
            ):
                return True
        return False