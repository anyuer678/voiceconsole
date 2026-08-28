"""命令安全门：白名单/黑名单判� � + 线程安全的确认状态机。"""

imp ort threading
import time
import uuid

DENY_P REFIXES = (
    "rm ", "shred", "dd ", "mkfs" , "curl ", "wget ", "sudo ", "mv ", "del ",
     "bash ", "shutdown", "passwd", "chpasswd",  "net user",
)
ALLOW_PREFIXES = (
    "ls", " cd", "cat", "git status", "git log", "pwd", " where",
    "systeminfo", "tasklist", "dir",  "ping", "ps", "top",
)
CONFIRM_TIMEOUT_S = 30 
_SHELL_METACHARS = (";", "&&", "||", "|", "> ", "<", "`", "$(", "&")


class SafetyVerdict :
    """check_command 的返回值（字符� ��常量，便于断言比较）。"""
    AL LOWED = "allowed"
    DENIED = "denied"
    N EEDS_CONFIRM = "needs_confirm"


class ToolDe niedError(RuntimeError):
    """命令被安� ��门拒绝时抛出的异常。"""


class _ ConfirmEntry:
    __slots__ = ("confirm_id",  "tool", "args", "state", "deadline")

    def  __init__(self, confirm_id: str, tool: str, a rgs: dict, deadline: float):
        self.con firm_id = confirm_id
        self.tool = tool 
        self.args = args
        self.state  = "REQUESTED"  # REQUESTED -> APPROVED / DENI ED
        self.deadline = deadline


class S afetyEngine:
    """状态机：IDLE -> REQUE STED(超时) -> APPROVED/DENIED；加锁线� �安全。"""

    def __init__(
        self ,
        allowlist: list[str] | None = None, 
        denylist: list[str] | None = None,
         confirm_mode: str = "dangerous-only",
         confirm_timeout_s: float = CONFIRM_TI MEOUT_S,
    ):
        self._allow = list(AL LOW_PREFIXES) + [p for p in (allowlist or [])  if p]
        self._deny = list(DENY_PREFIXE S) + [p for p in (denylist or []) if p]
         self._confirm_mode = confirm_mode
         self._confirm_timeout_s = confirm_timeout_s
         self._lock = threading.RLock()
         self._pending: dict[str, _ConfirmEntry] = {} 
        self._cond = threading.Condition(sel f._lock)

    def check_command(self, cmd: st r) -> str:
        """判定命令：allowed  | denied | needs_confirm。"""
        c = (c md or "").strip()
        if not c:
             return SafetyVerdict.DENIED
        low =  c.lower()
        if any(ch in low for ch in  _SHELL_METACHARS):
            return SafetyV erdict.DENIED
        if self._match_prefix(l ow, self._deny, allow_dot=True):
             return SafetyVerdict.DENIED
        if self._ confirm_mode == "all":
            return Saf etyVerdict.NEEDS_CONFIRM
        if self._mat ch_prefix(low, self._allow):
            retu rn SafetyVerdict.ALLOWED
        return Safet yVerdict.NEEDS_CONFIRM

    def needs_confirm (self, cmd: str) -> bool:
        """命令� �否需要二阶段确认。"""
        retur n self.check_command(cmd) == SafetyVerdict.NE EDS_CONFIRM

    def pending_ids(self) -> lis t[str]:
        """当前处于 REQUESTED 状 态的确认流 id（供外部发现并应答 ）。"""
        with self._lock:
             return [cid for cid, e in self._pending.ite ms() if e.state == "REQUESTED"]

    def star t_confirm_flow(self, tool: str, args: dict) - > str:
        """发起一次确认，返回  confirm_id（REQUESTED 状态）。"""
         cid = uuid.uuid4().hex
        entry = _Co nfirmEntry(cid, tool, dict(args), time.monoto nic() + self._confirm_timeout_s)
        with  self._lock:
            self._pending[cid] =  entry
        return cid

    def resolve_co nfirm(self, confirm_id: str, answer: bool) ->  bool:
        """应答确认；超时后的 应答一律按拒绝处理，返回是否放 行。"""
        with self._cond:
             entry = self._pending.get(confirm_id)
             if entry is None:
                retu rn False
            if entry.state != "REQUE STED":
                return entry.state ==  "APPROVED"
            if time.monotonic() >  entry.deadline:
                entry.state =  "DENIED"
                self._cond.notify_a ll()
                return False
             entry.state = "APPROVED" if answer else "DEN IED"
            self._cond.notify_all()
             return entry.state == "APPROVED"

     def await_confirm(self, confirm_id: str, tim eout_s: float | None = None) -> bool:
         """阻塞等待确认结果；超时自动� �拒绝处理。"""
        deadline = time.m onotonic() + (
            timeout_s if timeo ut_s is not None else self._confirm_timeout_s 
        )
        with self._cond:
             while True:
                entry = self._ pending.get(confirm_id)
                if en try is None:
                    return False 
                if entry.state != "REQUESTED ":
                    return entry.state ==  "APPROVED"
                remaining = entry. deadline - time.monotonic()
                i f remaining <= 0:
                    entry.s tate = "DENIED"
                    self._con d.notify_all()
                    return Fal se
                wait = min(remaining, dead line - time.monotonic())
                if w ait <= 0:
                    return False
                 self._cond.wait(wait)

    @sta ticmethod
    def _match_prefix(low_cmd: str,  prefixes: tuple[str, ...], allow_dot: bool =  False) -> bool:
        """前缀匹配，� �求边界为空白/串尾（deny 额外允� � '.'），避免 rm 误伤 rmdir。"""
         for p in prefixes:
            lp = p.stri p().lower()
            if not lp:
                 continue
            if low_cmd.startsw ith(lp) and (
                len(low_cmd) ==  len(lp)
                or low_cmd[len(lp)]  in " \t" + ("." if allow_dot else "")
             ):
                return True
        r eturn False
 