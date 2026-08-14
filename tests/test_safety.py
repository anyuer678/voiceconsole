"""测试安全门：黑/白名单、注入拒绝、确认状态机。"""

import threading
import time

from voiceconsole.safety import SafetyEngine, SafetyVerdict, ToolDeniedError


def test_deny_blacklist():
    e = SafetyEngine()
    for cmd in [
        "rm -rf /",
        "rm file.txt",
        "sudo rm x",
        "curl http://evil",
        "wget http://x",
        "del report.txt",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
        "mv secret out",
        "shutdown /s",
        "bash -c 'rm -rf /'",
        "passwd",
        "chpasswd",
        "net user hacker /add",
    ]:
        assert e.check_command(cmd) == SafetyVerdict.DENIED, cmd


def test_allow_whitelist():
    e = SafetyEngine()
    for cmd in [
        "ls",
        "ls -la",
        "cd C:/Users",
        "cat config.json",
        "git status",
        "git log --oneline",
        "pwd",
        "dir",
        "dir /b",
        "tasklist",
        "systeminfo",
        "where python",
        "ping 127.0.0.1",
        "ps aux",
        "top",
    ]:
        assert e.check_command(cmd) == SafetyVerdict.ALLOWED, cmd


def test_prefix_boundary_not_confused():
    e = SafetyEngine()
    assert e.check_command("rmdir junk") == SafetyVerdict.NEEDS_CONFIRM  # rm 前缀不误伤
    assert e.check_command("lsblk") == SafetyVerdict.NEEDS_CONFIRM  # ls 前缀不误伤


def test_deny_injection():
    e = SafetyEngine()
    for cmd in [
        "ls; rm -rf /",
        "cat a && rm b",
        "dir || del x",
        "dir | del x",
        "echo hi > file",
        "cat < file",
        "ls $(whoami)",
        "echo `id`",
    ]:
        assert e.check_command(cmd) == SafetyVerdict.DENIED, cmd


def test_empty_command_denied():
    assert SafetyEngine().check_command("") == SafetyVerdict.DENIED
    assert SafetyEngine().check_command("   ") == SafetyVerdict.DENIED


def test_needs_confirm():
    e = SafetyEngine()
    assert e.check_command("python main.py") == SafetyVerdict.NEEDS_CONFIRM
    assert e.needs_confirm("python main.py")
    assert not e.needs_confirm("ls")


def test_confirm_mode_all():
    e = SafetyEngine(confirm_mode="all")
    assert e.check_command("ls") == SafetyVerdict.NEEDS_CONFIRM


def test_config_allow_deny_override():
    e = SafetyEngine(allowlist=["myscript"], denylist=["ls"])
    assert e.check_command("myscript run") == SafetyVerdict.ALLOWED
    assert e.check_command("ls") == SafetyVerdict.DENIED


def test_confirm_flow_approve():
    e = SafetyEngine()
    cid = e.start_confirm_flow("run_cli", {"command": "python x.py"})
    assert e.resolve_confirm(cid, True)
    assert e.await_confirm(cid, timeout_s=1.0)


def test_confirm_flow_deny():
    e = SafetyEngine()
    cid = e.start_confirm_flow("run_cli", {})
    assert not e.resolve_confirm(cid, False)
    assert not e.await_confirm(cid, timeout_s=1.0)


def test_confirm_timeout_then_reject():
    e = SafetyEngine(confirm_timeout_s=0.2)
    cid = e.start_confirm_flow("run_cli", {})
    time.sleep(0.3)
    assert not e.resolve_confirm(cid, True)  # 超时后应答一律拒绝
    assert not e.await_confirm(cid, timeout_s=0.1)


def test_await_confirm_timeout():
    e = SafetyEngine(confirm_timeout_s=30)
    cid = e.start_confirm_flow("run_cli", {})
    start = time.monotonic()
    assert not e.await_confirm(cid, timeout_s=0.3)
    assert time.monotonic() - start >= 0.25


def test_resolve_unknown_id():
    e = SafetyEngine()
    assert not e.resolve_confirm("nope", True)
    assert not e.await_confirm("nope", timeout_s=0.1)


def test_confirm_thread_safe():
    e = SafetyEngine()
    cid = e.start_confirm_flow("run_cli", {})
    results = []

    def worker():
        results.append(e.await_confirm(cid))

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.1)
    assert e.resolve_confirm(cid, True)
    t.join(timeout=2)
    assert results == [True]
