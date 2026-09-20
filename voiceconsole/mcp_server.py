"""MCP 工具层：工具注册与执行编排（safety → path sandbox → actions → audit）。"""

from mcp.server.mcpserver import MCPServer

from . import actions, audit as audit_mod, safety as safety_mod
from . import path_sandbox

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
    engine = _config.get("tts_engine", "system")
    # edge-tts 会出网：仅在显式配置时使用
    if engine == "edge" and not _config.get("tts_allow_network", False):
        engine = "system"
    actions.speak_text(text, engine=engine)


def _confirm_authority() -> str:
    """local-ui（默认）| mcp（显式 opt-in，不推荐）。"""
    return str(_config.get("confirm_authority", "local-ui")).lower()


def _path_roots() -> list[str] | None:
    roots = _config.get("path_roots")
    if roots is None:
        return path_sandbox.default_roots()
    if not isinstance(roots, list):
        return path_sandbox.default_roots()
    return [str(r) for r in roots if r]


def _audit(**fields) -> None:
    rec = {"source": fields.pop("source", "mcp")}
    rec.update(fields)
    audit_mod.append_audit(rec, _config.get("audit_path") or None)


@server.tool(
    name="run_cli",
    description=(
        "执行 shell 命令（白名单内直接执行，危险命令拒绝，其余需确认）。"
        "默认确认权在本机 UI：MCP 客户端不能用 confirm 自批。"
        "例句：run_cli(command='dir')"
    ),
)
def run_cli(command: str, cwd: str | None = None, wait_confirm: bool = True) -> dict:
    """白名单执行命令，返回 stdout/stderr/exit_code/elapsed_ms。"""
    verdict = safety.check_command(command)
    if verdict == safety_mod.SafetyVerdict.DENIED:
        _audit(tool="run_cli", command=command, gate="denied", source="mcp")
        raise safety_mod.ToolDeniedError(f"命令被安全策略拒绝: {command}")
    if verdict == safety_mod.SafetyVerdict.NEEDS_CONFIRM:
        cid = safety.start_confirm_flow("run_cli", {"command": command})
        _audit(tool="run_cli", command=command, gate="needs_confirm", confirm_id=cid, source="mcp")
        if not wait_confirm:
            # 返回 confirm_id 供展示/本地 UI 发现；MCP 侧 confirm 默认不能批准
            return {
                "needs_confirm": True,
                "confirm_id": cid,
                "confirm_authority": _confirm_authority(),
                "prompt": f"确认执行命令 {command}？（请在本机 UI/热键确认）",
                "timeout_s": 30,
            }
        _speak(f"确认执行命令 {command}？")
        if not safety.await_confirm(cid):
            _audit(tool="run_cli", command=command, gate="confirm_timeout_or_denied", confirm_id=cid, source="mcp")
            return {"stdout": "", "stderr": "用户未确认，已取消", "exit_code": 130, "elapsed_ms": 0}
    result = actions.run_cli_cmd(command, cwd=cwd, timeout_ms=_config.get("timeout_ms", 10000))
    _audit(
        tool="run_cli",
        command=command,
        gate=verdict,
        exit_code=result.exit_code,
        elapsed_ms=result.elapsed_ms,
        source="mcp",
    )
    return {
        "stdout": _summarize(result.stdout),
        "stderr": _summarize(result.stderr),
        "exit_code": result.exit_code,
        "elapsed_ms": result.elapsed_ms,
    }


@server.tool(
    name="find_file",
    description="按文件名模糊搜索文件（默认仅限配置的 path_roots / 用户主目录）。例句：find_file(pattern='报告')",
)
def find_file(pattern: str, directory: str = ".") -> dict:
    """搜索文件名，返回最多 20 条匹配。"""
    try:
        safe_dir = path_sandbox.resolve_allowed(directory, _path_roots())
    except path_sandbox.PathSandboxError as e:
        _audit(tool="find_file", directory=directory, gate="path_denied", error=str(e), source="mcp")
        return {"matches": [], "limit": 20, "error": str(e)}
    try:
        matches = actions.search_files(pattern, directory=safe_dir, max_hits=20)
    except NotADirectoryError as e:
        return {"matches": [], "limit": 20, "error": str(e)}
    _audit(tool="find_file", directory=safe_dir, pattern=pattern, hits=len(matches), gate="ok", source="mcp")
    return {"matches": matches, "limit": 20}


@server.tool(
    name="open_folder",
    description="在系统文件管理器中打开文件夹（默认仅限 path_roots）。例句：open_folder(path='~/Desktop')",
)
def open_folder(path: str) -> dict:
    """打开文件夹；confirm_mode=all 或路径越界时需确认/拒绝。"""
    try:
        safe_path = path_sandbox.resolve_allowed(path, _path_roots())
    except path_sandbox.PathSandboxError as e:
        _audit(tool="open_folder", path=path, gate="path_denied", error=str(e), source="mcp")
        return {"ok": False, "error": str(e)}
    if _config.get("confirm_mode") == "all":
        cid = safety.start_confirm_flow("open_folder", {"path": safe_path})
        _speak(f"确认打开文件夹 {safe_path}？")
        if not safety.await_confirm(cid):
            _audit(tool="open_folder", path=safe_path, gate="confirm_denied", source="mcp")
            return {"ok": False, "error": "用户未确认，已取消"}
    ok = actions.open_in_file_manager(safe_path)
    _audit(tool="open_folder", path=safe_path, gate="ok" if ok else "open_failed", source="mcp")
    if ok:
        return {"ok": True}
    return {"ok": False, "error": f"无法打开: {safe_path}"}


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
    description=(
        "发起语音确认提示，或（仅当 confirm_authority=mcp 时）应答既有确认流。"
        "默认 local-ui：MCP 客户端无法自批 run_cli 返回的 confirm_id。"
        "例句：confirm(prompt='确认执行该操作？')"
    ),
)
def confirm(prompt: str = "", confirm_id: str = "", answer: bool = True) -> dict:
    """应答已有确认流（受 confirm_authority 约束），或发起新确认并阻塞等待。"""
    if confirm_id:
        authority = _confirm_authority()
        if authority != "mcp":
            _audit(tool="confirm", confirm_id=confirm_id, gate="mcp_cannot_approve", source="mcp")
            return {
                "ok": False,
                "error": "confirm_authority=local-ui：MCP 客户端不能批准确认，请在本机 UI/热键确认",
                "confirm_authority": authority,
            }
        ok = safety.resolve_confirm(confirm_id, bool(answer))
        _audit(tool="confirm", confirm_id=confirm_id, answer=bool(answer), gate="resolved", source="mcp")
        return {"ok": ok}
    if not prompt:
        return {"ok": False, "error": "需要 prompt（发起新确认）或 confirm_id（应答既有确认）"}
    cid = safety.start_confirm_flow("confirm", {"prompt": prompt})
    _speak(prompt)
    ok = safety.await_confirm(cid)
    _audit(tool="confirm", prompt=prompt, gate="ok" if ok else "denied", confirm_id=cid, source="mcp")
    return {"ok": ok}
