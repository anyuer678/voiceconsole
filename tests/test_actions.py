"""测试执行体：CLI 运行、文件搜索、打开文件夹、TTS 转调。"""

import pytest

from voiceconsole import actions


def test_run_cli_echo():
    r = actions.run_cli_cmd('python -c "print(\'hello\')"')
    assert r.exit_code == 0
    assert "hello" in r.stdout
    assert isinstance(r.elapsed_ms, int) and r.elapsed_ms >= 0


def test_run_cli_chinese_output():
    """中文输出（GBK/UTF-8 混合编码）不应导致解码崩溃。"""
    r = actions.run_cli_cmd('python -c "print(\'你好世界\')"')
    assert r.exit_code == 0
    assert r.stdout  # 至少完整返回不崩


def test_run_cli_timeout():
    r = actions.run_cli_cmd('python -c "import time; time.sleep(5)"', timeout_ms=200)
    assert r.exit_code == 124


def test_run_cli_cwd(tmp_path):
    r = actions.run_cli_cmd('python -c "import os; print(os.getcwd())"', cwd=str(tmp_path))
    assert str(tmp_path) in r.stdout


def test_search_files(tmp_path):
    (tmp_path / "report2026.txt").write_text("x", encoding="utf-8")
    (tmp_path / "other.log").write_text("y", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "report_old.txt").write_text("z", encoding="utf-8")
    hits = actions.search_files("report", str(tmp_path), max_hits=10)
    names = [h["path"] for h in hits]
    assert any("report2026.txt" in n for n in names)
    assert any("report_old.txt" in n for n in names)
    assert not any("other.log" in n for n in names)
    for h in hits:
        assert set(h) == {"path", "is_dir", "mtime"}


def test_search_files_max_hits(tmp_path):
    for i in range(10):
        (tmp_path / f"a{i}.txt").write_text("x", encoding="utf-8")
    hits = actions.search_files("a", str(tmp_path), max_hits=3)
    assert len(hits) == 3


def test_search_files_wildcard(tmp_path):
    (tmp_path / "abc.txt").write_text("x", encoding="utf-8")
    hits = actions.search_files("*.txt", str(tmp_path), max_hits=10)
    assert any("abc.txt" in h["path"] for h in hits)


def test_search_files_bad_dir():
    with pytest.raises(NotADirectoryError):
        actions.search_files("x", "Z:/no_such_dir_xyz")


def test_open_in_file_manager_mock(monkeypatch):
    calls = []

    def fake_popen(args, **kw):
        calls.append(args)

    monkeypatch.setattr(actions.subprocess, "Popen", fake_popen)
    assert actions.open_in_file_manager("C:/") is True
    assert calls and calls[0][0] == "explorer"


def test_open_in_file_manager_error(monkeypatch):
    def boom(args, **kw):
        raise OSError("no explorer")

    monkeypatch.setattr(actions.subprocess, "Popen", boom)
    assert actions.open_in_file_manager("C:/") is False


def test_speak_text_delegates(monkeypatch):
    from voiceconsole import tts as tts_mod

    calls = []

    def fake(text, engine):
        calls.append((text, engine))

    monkeypatch.setattr(tts_mod, "speak_text", fake)
    actions.speak_text("你好", engine="edge")
    assert calls == [("你好", "edge")]
