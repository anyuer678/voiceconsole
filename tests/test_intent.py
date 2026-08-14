"""测试意图解析与工具映射。"""

from voiceconsole.intent import is_affirmative, map_to_tool, parse_intent


def test_open_folder():
    it = parse_intent("打开桌面")
    assert it.action == "open_folder"
    assert it.args["path"] == "桌面"
    assert map_to_tool(it) == ("open_folder", {"path": "桌面"})


def test_open_folder_english():
    it = parse_intent("open C:/Users")
    assert it.action == "open_folder"
    assert it.args["path"] == "C:/Users"


def test_find_file():
    it = parse_intent("找 nginx 日志")
    assert it.action == "find_file"
    assert it.args["pattern"] == "nginx 日志"


def test_find_file_variants():
    for t in ["查找 报告", "搜索 report", "find report"]:
        assert parse_intent(t).action == "find_file", t


def test_execute_cli_verb():
    it = parse_intent("执行 git status")
    assert it.action == "execute_cli"
    assert it.args["command"] == "git status"
    assert map_to_tool(it) == ("run_cli", {"command": "git status"})


def test_execute_cli_hint():
    for t in ["ls -la", "dir", "git log", "pwd"]:
        it = parse_intent(t)
        assert it.action == "execute_cli", t
        assert it.args["command"] == t


def test_quit_help():
    for t in ["退出", "再见", "quit", "exit"]:
        assert parse_intent(t).action == "quit", t
    for t in ["帮助", "help", "怎么用"]:
        assert parse_intent(t).action == "help", t


def test_unknown():
    it = parse_intent("今天天气怎么样")
    assert it.action == "unknown"
    assert map_to_tool(it) is None


def test_empty():
    it = parse_intent("")
    assert it.action == "unknown"


def test_map_to_tool_none():
    assert map_to_tool(parse_intent("随便说点什么")) is None


def test_affirmative():
    for t in ["是", "对", "好的", "确认", "可以", "yes", "ok", "确定"]:
        assert is_affirmative(t), t


def test_not_affirmative():
    for t in ["不是", "否", "不要", "no", "取消", "打开桌面"]:
        assert not is_affirmative(t), t
