"""命令安全门：白名单/黑名单判定 + 线程安全的确认状态机。"""

import re
import threading
import time
import uuid

DENY_PREFIXES = (
    "rm ", "shred", "dd ", "mkfs", "curl ", "wget ", "sudo ", "mv ", "del ",
    "bash ", "shutdown", "passwd", "chpasswd", "net user",
)
ALLOW_PREFIXES = (
    "ls", "cd", "git status", "git log", "pwd", "where",
    "systeminfo", "tasklist", "dir", "ping", "ps", "top",
)
CONFIRM_TIMEOUT_S = 30
_SHELL_METACHARS = (";", "&&", "||", "|", ">", "<", "`", "$(", "&")


class SafetyVerdict:
    """check_command 的返回值（字符串常量，便于断言比较）。"""
    ALLOWED = "allowed"
    DENIED = "denied"
    NEEDS_CONFIRM = "needs_confirm"


class ToolDeniedError(RuntimeError):
    """命令被安全门拒绝时抛出的异常。"""


class _ConfirmEntry:
    __slots__ = ("confirm_id", "tool", "args", "state", "deadline")

    def __init__(self, confirm_id: str, tool: str, args: dict, deadline: float):
        self.confirm_id = confirm_id
        self.tool = tool
        self.args = args
        self.state = "REQUESTED"  # REQUESTED -> APPROVED / DENIED
        self.deadline = deadline


class SafetyEngine:
    """状态机：IDLE -> REQUESTED(超时) -> APPROVED/DENIED；加锁线程安全。"""

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
        self._cond = threading.Condition(self._lock)

    def check_command(self, cmd: str) -> str:
        """判定命令：allowed | denied | needs_confirm。"""
        # 先把连续空白/制表符归一成单空格，防止 "net  user"、"del\t x" 绕过前缀匹配
        c = re.sub(r"\s+", " ", (cmd or "").strip())
        if not c:
            return SafetyVerdict.DENIED
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
        """当前处于 REQUESTED 状态的确认流 id（供外部发现并应答）。"""
        with self._lock:
            return [cid for cid, e in self._pending.items() if e.state == "REQUESTED"]

    def start_confirm_flow(self, tool: str, args: dict) -> str:
        """发起一次确认，返回 confirm_id（REQUESTED 状态）。"""
        cid = uuid.uuid4().hex
        entry = _ConfirmEntry(cid, tool, dict(args), time.monotonic() + self._confirm_timeout_s)
        with self._lock:
            self._pending[cid] = entry
        return cid

    def resolve_confirm(self, confirm_id: str, answer: bool) -> bool:
        """应答确认；超时后的应答一律按拒绝处理，返回是否放行。"""
        with self._cond:
            entry = self._pending.get(confirm_id)
            if entry is None:
                return False
            if entry.state != "REQUESTED":
                return entry.state == "APPROVED"
            if time.monotonic() > entry.deadline:
                entry.state = "DENIED"
                self._cond.notify_all()
                return False
            entry.state = "APPROVED" if answer else "DENIED"
            self._cond.notify_all()
            return entry.state == "APPROVED"

    def await_confirm(self, confirm_id: str, timeout_s: float | None = None) -> bool:
        """阻塞等待确认结果；超时自动按拒绝处理。"""
        deadline = time.monotonic() + (
            timeout_s if timeout_s is not None else self._confirm_timeout_s
        )
        with self._cond:
            while True:
                entry = self._pending.get(confirm_id)
                if entry is None:
                    return False
                if entry.state != "REQUESTED":
                    return entry.state == "APPROVED"
                remaining = entry.deadline - time.monotonic()
                if remaining <= 0:
                    entry.state = "DENIED"
                    self._cond.notify_all()
                    return False
                wait = min(remaining, deadline - time.monotonic())
                if wait <= 0:
                    return False
                self._cond.wait(wait)

    @staticmethod
    def _match_prefix(low_cmd: str, prefixes: tuple[str, ...], allow_dot: bool = False) -> bool:
        """前缀匹配，要求边界为空白/串尾（deny 额外允许 '.'），避免 rm 误伤 rmdir。"""
        for p in prefixes:
            lp = p.strip().lower()
            if not lp:
                continue
            if low_cmd.startswith(lp) and (
                len(low_cmd) == len(lp)
                or low_cmd[len(lp)] in " \t" + ("." if allow_dot else "")
            ):
                return True
        return False
