"""MCP 工具层：工具注册与执行编排（safety → actions）。"""

from mcp.server.mcpserver import MCPServer

from . import actions, safety as safety_mod

server = MCPServer("voice-console")
safety: safety_mod.SafetyEngine = safety_mod.SafetyEngine()
_config: dict = {}

_OUTPUT_CAP = 2000


def configure(cfg: dict) -> None:
    """用配置重建安全引擎（工具调用前必须先 configure）。"""
    global safety, _config
    _config = cfg
    safety = safety_mod.SafetyEngine(
        allowlist=cfg.get("allowlist"),
        denylist=cfg.get("denylist"),
        confirm_mode=cfg.get("confirm_mode", "dangerous-only"),
    )


def _summarize(text: str) -> str:
    return (text or "").strip()[: _OUTPUT_CAP]


def _speak(text: str) -> None:
    actions.speak_text(text, engine=_config.get("tts_engine", "edge"))


@server.tool(
    name="run_cli",
    description="执行 shell 命令（白名单内直接执行，危险命令拒绝，其余需语音确认）。例句：run_cli(command='dir')",
)
def run_cli(command: str, cwd: str | None = None) -> dict:
    """白名单执行命令，返回 stdout/stderr/exit_code/elapsed_ms。"""
    verdict = safety.check_command(command)
    if verdict == safety_mod.SafetyVerdict.DENIED:
        raise safety_mod.ToolDeniedError(f"命令被安全策略拒绝: {command}")
    if verdict == safety_mod.SafetyVerdict.NEEDS_CONFIRM:
        cid = safety.start_confirm_flow("run_cli", {"command": command})
        _speak(f"确认执行命令 {command}？")
        if not safety.await_confirm(cid):
            return {"stdout": "", "stderr": "用户未确认，已取消", "exit_code": 130, "elapsed_ms": 0}
    result = actions.run_cli_cmd(command, cwd=cwd, timeout_ms=_config.get("timeout_ms", 10000))
    return {
        "stdout": _summarize(result.stdout),
        "stderr": _summarize(result.stderr),
        "exit_code": result.exit_code,
        "elapsed_ms": result.elapsed_ms,
    }


@server.tool(
    name="find_file",
    description="按文件名模糊搜索文件。例句：find_file(pattern='报告', directory='C:/Users/xxx/Desktop')",
)
def find_file(pattern: str, directory: str = ".") -> dict:
    """搜索文件名，返回最多 20 条匹配。"""
    try:
        matches = actions.search_files(pattern, directory=directory, max_hits=20)
    except NotADirectoryError as e:
        return {"matches": [], "limit": 20, "error": str(e)}
    return {"matches": matches, "limit": 20}


@server.tool(
    name="open_folder",
    description="在系统文件管理器中打开文件夹。例句：open_folder(path='C:/Users/xxx/Desktop')",
)
def open_folder(path: str) -> dict:
    """打开文件夹；confirm_mode=all 时需语音确认。"""
    if _config.get("confirm_mode") == "all":
        cid = safety.start_confirm_flow("open_folder", {"path": path})
        _speak(f"确认打开文件夹 {path}？")
        if not safety.await_confirm(cid):
            return {"ok": False, "error": "用户未确认，已取消"}
    ok = actions.open_in_file_manager(path)
    if ok:
        return {"ok": True}
    return {"ok": False, "error": f"无法打开: {path}"}


@server.tool(
    name="speak",
    description="TTS 播报一段文本（供工具回读结果）。例句：speak(text='已打开文件夹')",
)
def speak(text: str) -> dict:
    """播报文本，尽力而为。"""
    _speak(text)
    return {"ok": True}


@server.tool(
    name="confirm",
    description="发起并等待一次语音安全确认，超时默认拒绝。例句：confirm(prompt='确认执行该操作？')",
)
def confirm(prompt: str) -> dict:
    """发起确认流程并阻塞等待应答（语音线程 resolve），返回 {'ok': bool}。"""
    cid = safety.start_confirm_flow("confirm", {"prompt": prompt})
    _speak(prompt)
    ok = safety.await_confirm(cid)
    return {"ok": ok}
