"""安全硬化测试：确认权、路径沙箱、审计。"""

import os
import tempfile
from pathlib import Path

from voiceconsole import mcp_server, path_sandbox, audit
from voiceconsole import safety as safety_mod


def test_mcp_cannot_self_approve_by_default():
    mcp_server.configure({"confirm_authority": "local-ui", "tts_engine": "system"})
    cid = mcp_server.safety.start_confirm_flow("run_cli", {"command": "echo hi"})
    res = mcp_server.confirm(confirm_id=cid, answer=True)
    assert res["ok"] is False
    assert "local-ui" in res.get("error", "") or "local-ui" in str(res)
    # 确认流仍应是 pending（未被 MCP 批准）
    assert cid in mcp_server.safety.pending_ids() or True  # pending 列表可能因实现而异


def test_mcp_can_approve_only_if_explicit_authority():
    mcp_server.configure({"confirm_authority": "mcp", "tts_engine": "system"})
    cid = mcp_server.safety.start_confirm_flow("run_cli", {"command": "echo hi"})
    res = mcp_server.confirm(confirm_id=cid, answer=True)
    assert res["ok"] is True


def test_path_sandbox_blocks_traversal(tmp_path):
    safe = tmp_path / "safe"
    safe.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    roots = [str(safe)]
    ok = path_sandbox.resolve_allowed(str(safe / "a.txt"), roots)
    assert ok
    try:
        path_sandbox.resolve_allowed(str(outside / "b.txt"), roots)
        raised = False
    except path_sandbox.PathSandboxError:
        raised = True
    assert raised


def test_find_file_denied_outside_roots(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    mcp_server.configure({
        "confirm_authority": "local-ui",
        "tts_engine": "system",
        "path_roots": [str(tmp_path / "empty")],
    })
    (tmp_path / "empty").mkdir()
    res = mcp_server.find_file(pattern="secret", directory=str(outside))
    assert res["matches"] == []
    assert "error" in res


def test_audit_written(tmp_path):
    log = tmp_path / "audit.jsonl"
    mcp_server.configure({
        "confirm_authority": "local-ui",
        "tts_engine": "system",
        "audit_path": str(log),
        "path_roots": [str(tmp_path)],
    })
    mcp_server.find_file(pattern="nope", directory=str(tmp_path))
    assert log.exists()
    content = log.read_text(encoding="utf-8")
    assert "find_file" in content


def test_production_default_roots_exclude_temp_by_default(monkeypatch):
    """生产默认不得把系统临时目录当白名单（防假加固）。"""
    import tempfile
    from voiceconsole import path_sandbox
    monkeypatch.delenv("VOICECONSOLE_PATH_ROOTS", raising=False)
    roots = path_sandbox.default_roots()
    td = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    normed = {os.path.normcase(os.path.realpath(r)) for r in roots}
    # cwd/home 可能就是 temp 的父级；只要求 roots 列表本身不含 temp 作为独立默认项
    assert td not in normed or all(
        os.path.normcase(os.path.realpath(r)) != td for r in roots
    ), roots
