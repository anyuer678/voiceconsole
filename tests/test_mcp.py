"""测试 MCP 层：真实 stdio 子进程工具调用 + 单元级确认流。"""

import asyncio
import os
import sys
import threading
import time

from mcp import ClientSession, StdioServerParameters, stdio_client

from voiceconsole import mcp_server
from voiceconsole.actions import CLIResult

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_TOOLS = {"run_cli", "find_file", "open_folder", "speak", "confirm"}


def _run(coro):
    return asyncio.run(coro)


def _params(env):
    return StdioServerParameters(
        command=sys.executable, args=["-m", "voiceconsole"], env=env
    )


# ---------- 真实 stdio 子进程 ----------

def test_list_tools(server_env):
    async def main():
        async with stdio_client(_params(server_env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = await session.list_tools()
                return {t.name for t in tools.tools}

    assert _run(main()) == EXPECTED_TOOLS


def test_call_speak(server_env):
    async def main():
        async with stdio_client(_params(server_env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool("speak", {"text": "你好"})
                return res

    res = _run(main())
    assert not res.is_error
    text = res.content[0].text if res.content else ""
    assert '"ok": true' in text


def test_call_run_cli_whitelist(server_env):
    async def main():
        async with stdio_client(_params(server_env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool("run_cli", {"command": "dir"})
                return res

    res = _run(main())
    assert not res.is_error
    text = res.content[0].text if res.content else ""
    assert '"exit_code": 0' in text
    assert '"stdout"' in text


def test_call_run_cli_denied(server_env):
    async def main():
        async with stdio_client(_params(server_env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                try:
                    res = await session.call_tool("run_cli", {"command": "rm -rf /"})
                    return res
                except Exception:
                    return None

    res = _run(main())
    if res is None:
        return  # 拒绝以异常上报也视为通过（未执行）
    assert res.is_error  # 拒绝以 error 结果返回
    text = "".join(c.text for c in res.content) if res.content else ""
    assert "拒绝" in text or "denied" in text.lower()


def test_call_find_file(server_env, tmp_path):
    (tmp_path / "demo_report.txt").write_text("x", encoding="utf-8")
    (tmp_path / "other.log").write_text("y", encoding="utf-8")

    async def main():
        async with stdio_client(_params(server_env)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool(
                    "find_file", {"pattern": "demo", "directory": str(tmp_path)}
                )
                return res

    res = _run(main())
    assert not res.is_error
    text = res.content[0].text if res.content else ""
    assert "demo_report.txt" in text
    assert "other.log" not in text


# ---------- 单元级：确认流与工具编排 ----------

def _configure_all_confirm():
    mcp_server.configure(
        {
            "confirm_mode": "all",
            "tts_engine": "system",
            "timeout_ms": 2000,
            "allowlist": [],
            "denylist": [],
        }
    )
    mcp_server.actions.speak_text = lambda text, engine="system": None


def _resolve_pending(answer: bool):
    def worker():
        time.sleep(0.1)
        for cid in list(mcp_server.safety._pending):
            mcp_server.safety.resolve_confirm(cid, answer)

    threading.Thread(target=worker, daemon=True).start()


def test_run_cli_confirm_approved(monkeypatch):
    monkeypatch.setattr(
        mcp_server.actions,
        "run_cli_cmd",
        lambda command, cwd=None, timeout_ms=2000: CLIResult("ok", "", 0, 5),
    )
    _configure_all_confirm()
    _resolve_pending(True)
    r = mcp_server.run_cli("dir")
    assert r["exit_code"] == 0
    assert r["stdout"] == "ok"


def test_run_cli_confirm_rejected(monkeypatch):
    monkeypatch.setattr(mcp_server.actions, "run_cli_cmd", lambda **k: None)
    _configure_all_confirm()
    _resolve_pending(False)
    r = mcp_server.run_cli("dir")
    assert r["exit_code"] == 130


def test_open_folder_confirm_approved(monkeypatch):
    monkeypatch.setattr(mcp_server.actions, "open_in_file_manager", lambda p: True)
    _configure_all_confirm()
    _resolve_pending(True)
    assert mcp_server.open_folder("C:/tmp") == {"ok": True}


def test_open_folder_confirm_rejected(monkeypatch):
    monkeypatch.setattr(mcp_server.actions, "open_in_file_manager", lambda p: False)
    _configure_all_confirm()
    _resolve_pending(False)
    r = mcp_server.open_folder("C:/tmp")
    assert r == {"ok": False, "error": "用户未确认，已取消"}


def test_confirm_tool_blocking_resolve(monkeypatch):
    _configure_all_confirm()
    _resolve_pending(True)
    assert mcp_server.confirm("确认？") == {"ok": True}
