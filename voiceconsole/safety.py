"""命令安全门：白名单/黑名单判� � � + 线程安全的确认状态机。"""
 
imp ort threading
import time
import uuid

D ENY_P REFIXES = (
    "rm ", "shred", "dd ",  "mkfs" , "curl ", "wget ", "sudo ", "mv ", "d el ",
     "bash ", "shutdown", "passwd", "ch passwd",  "net user",
)
ALLOW_PREFIXES = (
     "ls", " cd", "cat", "git status", "git log" , "pwd", " where",
    "systeminfo", "tasklis t", "dir",  "ping", "ps", "top",
)
CONFIRM_TI MEOUT_S = 30 
_SHELL_METACHARS = (";", "&&",  "||", "|", "> ", "<", "`", "$(", "&")


class  SafetyVerdict :
    """check_command 的返� ��值（字符� ��常量，便于断言 比较）。"""
    AL LOWED = "allowed"
     DENIED = "denied"
    N EEDS_CONFIRM = "needs _confirm"


class ToolDe niedError(RuntimeErr or):
    """命令被安� ��门拒绝� �抛出的异常。"""


class _ ConfirmEntry :
    __slots__ = ("confirm_id",  "tool", "ar gs", "state", "deadline")

    def  __init__( self, confirm_id: str, tool: str, a rgs: dict , deadline: float):
        self.con firm_id  = confirm_id
        self.tool = tool 
         self.args = args
        self.state  = "REQ UESTED"  # REQUESTED -> APPROVED / DENI ED
         self.deadline = deadline


class S afet yEngine:
    """状态机：IDLE -> REQUE STE D(超时) -> APPROVED/DENIED；加锁线� � ��安全。"""

    def __init__(
        sel f ,
        allowlist: list[str] | None = Non e, 
        denylist: list[str] | None = None ,
         confirm_mode: str = "dangerous-onl y",
         confirm_timeout_s: float = CONFI RM_TI MEOUT_S,
    ):
        self._allow = l ist(AL LOW_PREFIXES) + [p for p in (allowlist  or [])  if p]
        self._deny = list(DENY _PREFIXE S) + [p for p in (denylist or []) if  p]
         self._confirm_mode = confirm_mod e
         self._confirm_timeout_s = confirm_ timeout_s
         self._lock = threading.RLo ck()
         self._pending: dict[str, _Confi rmEntry] = {} 
        self._cond = threading .Condition(sel f._lock)

    def check_comman d(self, cmd: st r) -> str:
        """判定� ��令：allowed  | denied | needs_confirm。" ""
        c = (c md or "").strip()
        i f not c:
             return SafetyVerdict.DE NIED
        low =  c.lower()
        if any( ch in low for ch in  _SHELL_METACHARS):
             return SafetyV erdict.DENIED
        i f self._match_prefix(l ow, self._deny, allow_ dot=True):
             return SafetyVerdict. DENIED
        if self._ confirm_mode == "all ":
            return Saf etyVerdict.NEEDS_CO NFIRM
        if self._mat ch_prefix(low, sel f._allow):
            retu rn SafetyVerdict. ALLOWED
        return Safet yVerdict.NEEDS_C ONFIRM

    def needs_confirm (self, cmd: str ) -> bool:
        """命令� �否需要� ��阶段确认。"""
        retur n self.che ck_command(cmd) == SafetyVerdict.NE EDS_CONFI RM

    def pending_ids(self) -> lis t[str]:
         """当前处于 REQUESTED 状 态的� ��认流 id（供外部发现并应答 ）。 """
        with self._lock:
             ret urn [cid for cid, e in self._pending.ite ms()  if e.state == "REQUESTED"]

    def star t_c onfirm_flow(self, tool: str, args: dict) - >  str:
        """发起一次确认，返回   confirm_id（REQUESTED 状态）。"""
          cid = uuid.uuid4().hex
        entry = _Co  nfirmEntry(cid, tool, dict(args), time.monot o nic() + self._confirm_timeout_s)
        wi th  self._lock:
            self._pending[cid ] =  entry
        return cid

    def resolv e_co nfirm(self, confirm_id: str, answer: boo l) ->  bool:
        """应答确认；超时 后的 应答一律按拒绝处理，返回� �否放 行。"""
        with self._cond:
              entry = self._pending.get(confirm_ id)
             if entry is None:
                 retu rn False
            if entry.stat e != "REQUE STED":
                return ent ry.state ==  "APPROVED"
            if time.m onotonic() >  entry.deadline:
                 entry.state =  "DENIED"
                self ._cond.notify_a ll()
                return F alse
             entry.state = "APPROVED" if  answer else "DEN IED"
            self._cond .notify_all()
             return entry.state  == "APPROVED"

     def await_confirm(self,  confirm_id: str, tim eout_s: float | None = N one) -> bool:
         """阻塞等待确认� ��果；超时自动� �拒绝处理。""" 
        deadline = time.m onotonic() + (
             timeout_s if timeo ut_s is not None  else self._confirm_timeout_s 
        )
         with self._cond:
             while True:
                 entry = self._ pending.get(co nfirm_id)
                if en try is None:
                     return False 
                 if entry.state != "REQUESTED ":
                     return entry.state ==  "APPROVED" 
                remaining = entry. deadline  - time.monotonic()
                i f remain ing <= 0:
                    entry.s tate =  "DENIED"
                    self._con d.noti fy_all()
                    return Fal se
                 wait = min(remaining, dead line  - time.monotonic())
                if w ait  <= 0:
                    return False
                  self._cond.wait(wait)

    @sta t icmethod
    def _match_prefix(low_cmd: str,   prefixes: tuple[str, ...], allow_dot: bool =   False) -> bool:
        """前缀匹配，� �� �求边界为空白/串尾（deny 额外 允� � '.'），避免 rm 误伤 rmdir。 """
         for p in prefixes:
            l p = p.stri p().lower()
            if not lp: 
                 continue
            if low _cmd.startsw ith(lp) and (
                le n(low_cmd) ==  len(lp)
                or low _cmd[len(lp)]  in " \t" + ("." if allow_dot e lse "")
             ):
                retur n True
        r eturn False
  