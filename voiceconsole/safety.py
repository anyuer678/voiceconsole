"""命令安全门：白名单/黑名单判� � � � + 线程安全的确认状态机。 """
 
imp ort threading
import time
import uu id

D ENY_P REFIXES = (
    "rm ", "shred", " dd ",  "mkfs" , "curl ", "wget ", "sudo ", "m v ", "d el ",
     "bash ", "shutdown", "pass wd", "ch passwd",  "net user",
)
ALLOW_PREFIX ES = (
     "ls", " cd", "cat", "git status",  "git log" , "pwd", " where",
    "systeminfo ", "tasklis t", "dir",  "ping", "ps", "top",
 )
CONFIRM_TI MEOUT_S = 30 
_SHELL_METACHARS =  (";", "&&",  "||", "|", "> ", "<", "`", "$(" , "&")


class  SafetyVerdict :
    """check_ command 的返� ��值（字符� �� �常量，便于断言 比较）。"""
    AL  LOWED = "allowed"
     DENIED = "denied"
     N EEDS_CONFIRM = "needs _confirm"


class To olDe niedError(RuntimeErr or):
    """命令� ��安� ��门拒绝� �抛出的异� �。"""


class _ ConfirmEntry :
    __slots_ _ = ("confirm_id",  "tool", "ar gs", "state",  "deadline")

    def  __init__( self, confir m_id: str, tool: str, a rgs: dict , deadline:  float):
        self.con firm_id  = confirm_ id
        self.tool = tool 
         self.ar gs = args
        self.state  = "REQ UESTED"   # REQUESTED -> APPROVED / DENI ED
         s elf.deadline = deadline


class S afet yEngin e:
    """状态机：IDLE -> REQUE STE D(超 时) -> APPROVED/DENIED；加锁线� � � ��安全。"""

    def __init__(
        s el f ,
        allowlist: list[str] | None =  Non e, 
        denylist: list[str] | None =  None ,
         confirm_mode: str = "dangerou s-onl y",
         confirm_timeout_s: float =  CONFI RM_TI MEOUT_S,
    ):
        self._al low = l ist(AL LOW_PREFIXES) + [p for p in (a llowlist  or [])  if p]
        self._deny =  list(DENY _PREFIXE S) + [p for p in (denylist  or []) if  p]
         self._confirm_mode =  confirm_mod e
         self._confirm_timeout_ s = confirm_ timeout_s
         self._lock =  threading.RLo ck()
         self._pending: di ct[str, _Confi rmEntry] = {} 
        self._c ond = threading .Condition(sel f._lock)

     def check_comman d(self, cmd: st r) -> str:
         """判定� ��令：allowed  | de nied | needs_confirm。" ""
        c = (c md  or "").strip()
        i f not c:
              return SafetyVerdict.DE NIED
        low =   c.lower()
        if any( ch in low for ch  in  _SHELL_METACHARS):
             return Sa fetyV erdict.DENIED
        i f self._match_p refix(l ow, self._deny, allow_ dot=True):
              return SafetyVerdict. DENIED
         if self._ confirm_mode == "all ":
             return Saf etyVerdict.NEEDS_CO NFIRM
         if self._mat ch_prefix(low, sel f._allow): 
            retu rn SafetyVerdict. ALLOWED
         return Safet yVerdict.NEEDS_C ONFIRM

     def needs_confirm (self, cmd: str ) -> bo ol:
        """命令� �否需要� �� ��阶段确认。"""
        retur n self.che  ck_command(cmd) == SafetyVerdict.NE EDS_CONF I RM

    def pending_ids(self) -> lis t[str] :
         """当前处于 REQUESTED 状 态� ��� ��认流 id（供外部发现并应 答 ）。 """
        with self._lock:
              ret urn [cid for cid, e in self._pend ing.ite ms()  if e.state == "REQUESTED"]

     def star t_c onfirm_flow(self, tool: str, ar gs: dict) - >  str:
        """发起一次� �认，返回   confirm_id（REQUESTED 状态 ）。"""
          cid = uuid.uuid4().hex
         entry = _Co  nfirmEntry(cid, tool, dict (args), time.monot o nic() + self._confirm_ti meout_s)
        wi th  self._lock:
             self._pending[cid ] =  entry
        retur n cid

    def resolv e_co nfirm(self, confir m_id: str, answer: boo l) ->  bool:
        " ""应答确认；超时 后的 应答一律� �拒绝处理，返回� �否放 行。""" 
        with self._cond:
              entry  = self._pending.get(confirm_ id)
              if entry is None:
                 retu rn  False
            if entry.stat e != "REQUE S TED":
                return ent ry.state ==   "APPROVED"
            if time.m onotonic()  >  entry.deadline:
                 entry.sta te =  "DENIED"
                self ._cond.no tify_a ll()
                return F alse
              entry.state = "APPROVED" if  answer  else "DEN IED"
            self._cond .notif y_all()
             return entry.state  == " APPROVED"

     def await_confirm(self,  conf irm_id: str, tim eout_s: float | None = N one ) -> bool:
         """阻塞等待确认�  ��果；超时自动� �拒绝处理� �""" 
        deadline = time.m onotonic() +  (
             timeout_s if timeo ut_s is not  None  else self._confirm_timeout_s 
         )
         with self._cond:
             whil e True:
                 entry = self._ pendi ng.get(co nfirm_id)
                if en try  is None:
                     return False 
                  if entry.state != "REQUESTED  ":
                     return entry.state = =  "APPROVED" 
                remaining = en try. deadline  - time.monotonic()
                 i f remain ing <= 0:
                     entry.s tate =  "DENIED"
                     self._con d.noti fy_all()
                     return Fal se
                 wait = min(r emaining, dead line  - time.monotonic())
                 if w ait  <= 0:
                     return False
                  self._cond. wait(wait)

    @sta t icmethod
    def _matc h_prefix(low_cmd: str,   prefixes: tuple[str,  ...], allow_dot: bool =   False) -> bool:
         """前缀匹配，� �� �求边� ��为空白/串尾（deny 额外 允� � ' .'），避免 rm 误伤 rmdir。 """
          for p in prefixes:
            l p = p.stri  p().lower()
            if not lp: 
                  continue
            if low _cmd.sta rtsw ith(lp) and (
                le n(low_c md) ==  len(lp)
                or low _cmd[l en(lp)]  in " \t" + ("." if allow_dot e lse " ")
             ):
                retur n Tr ue
        r eturn False
   