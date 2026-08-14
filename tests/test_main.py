"""测试 main.py 文本处理链路（_handle_text 全分支）。"""

import main as main_mod
from voiceconsole.actions import CLIResult


def _cfg():
    return {
        "tts_engine": "system",
        "timeout_ms": 1000,
        "confirm_mode": "dangerous-only",
        "allowlist": [],
        "denylist": [],
    }


def _no_speak(monkeypatch):
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda *a, **k: None)


def test_handle_quit(monkeypatch):
    _no_speak(monkeypatch)
    assert main_mod._handle_text(_cfg(), "退出") == "quit"


def test_handle_help(monkeypatch):
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    assert main_mod._handle_text(_cfg(), "帮助") is None
    assert any("可用指令" in s for s in spoken)


def test_handle_unknown(monkeypatch):
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    assert main_mod._handle_text(_cfg(), "今天天气不错") is None
    assert spoken == ["没听懂，请再说一次"]


def test_handle_run_cli_whitelist(monkeypatch):
    calls = []
    _no_speak(monkeypatch)

    def fake_run(cmd, timeout_ms=1000):
        calls.append(cmd)
        return CLIResult("hello-out", "", 0, 5)

    monkeypatch.setattr(main_mod.actions, "run_cli_cmd", fake_run)
    assert main_mod._handle_text(_cfg(), "执行 dir") is None
    assert calls == ["dir"]


def test_handle_run_cli_denied(monkeypatch):
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    assert main_mod._handle_text(_cfg(), "执行 rm -rf /") is None
    assert any("拒绝" in s for s in spoken)


def test_handle_run_cli_confirm_all_mode(monkeypatch):
    from voiceconsole import mcp_server

    cfg = {**_cfg(), "confirm_mode": "all"}
    mcp_server.configure(cfg)
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    monkeypatch.setattr(
        main_mod.actions,
        "run_cli_cmd",
        lambda cmd, timeout_ms=1000: CLIResult("", "", 0, 0),
    )

    def fake_ask(cfg2, prompt):
        spoken.append(prompt)
        return True

    monkeypatch.setattr(main_mod, "_ask_confirm", fake_ask)
    assert main_mod._handle_text(cfg, "执行 dir") is None
    assert any("确认执行" in s for s in spoken)


def test_handle_open_folder(monkeypatch):
    cfg = {**_cfg(), "confirm_mode": "dangerous-only"}
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    monkeypatch.setattr(main_mod.actions, "open_in_file_manager", lambda p: True)
    assert main_mod._handle_text(cfg, "打开桌面") is None
    assert "已打开" in spoken


def test_handle_find_file(monkeypatch):
    spoken = []
    monkeypatch.setattr(main_mod.actions, "speak_text", lambda t, engine="edge": spoken.append(t))
    assert main_mod._handle_text(_cfg(), "找 report") is None
    assert spoken  # 找到或没找到都会播报
