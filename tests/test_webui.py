"""测试 Web 控制台：路由、指令链路、确认流（本地回环，不依赖外部网络）。"""

import json
import urllib.request

from voiceconsole import mcp_server, webui

CFG = {
    "tts_engine": "system",
    "timeout_ms": 3000,
    "confirm_mode": "dangerous-only",
    "allowlist": [],
    "denylist": [],
}


def _start():
    mcp_server.configure(CFG)
    server = webui.start_server(port=0)
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def _request(base, path, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        base + path, data=body,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def _post(base, path, data):
    return _request(base, path, data)


def test_index_html():
    server, base = _start()
    try:
        status, text = _request(base, "/")
        assert status == 200
        assert "语音指令控制台" in text
        assert "api/command" in text  # 前端 JS 已内嵌
    finally:
        server.shutdown()


def test_command_run_cli():
    server, base = _start()
    try:
        status, text = _post(base, "/api/command", {"text": "执行 dir"})
        assert status == 200
        data = json.loads(text)
        assert data["status"] == "ok"
        joined = "\n".join(l["text"] for l in data["lines"])
        assert "exit_code=0" in joined
    finally:
        server.shutdown()


def test_command_denied():
    server, base = _start()
    try:
        status, text = _post(base, "/api/command", {"text": "执行 rm -rf /"})
        data = json.loads(text)
        assert any("拒绝" in l["text"] for l in data["lines"])
    finally:
        server.shutdown()


def test_command_unknown_and_quit():
    server, base = _start()
    try:
        _, text = _post(base, "/api/command", {"text": "今天天气不错"})
        assert any("没听懂" in l["text"] for l in json.loads(text)["lines"])
        _, text = _post(base, "/api/command", {"text": "退出"})
        assert any("不支持退出指令" in l["text"] for l in json.loads(text)["lines"])
    finally:
        server.shutdown()


def test_confirm_flow_approve():
    server, base = _start()
    try:
        _, text = _post(base, "/api/command", {"text": "执行 echo hello"})
        data = json.loads(text)
        assert data["status"] == "need_confirm"
        cid = data["confirm_id"]
        assert cid
        # 批准
        _, text = _post(base, "/api/confirm", {"confirm_id": cid, "answer": True})
        data = json.loads(text)
        joined = "\n".join(l["text"] for l in data["lines"])
        assert "已确认" in joined
        assert "exit_code=0" in joined  # echo hello 已真实执行
    finally:
        server.shutdown()


def test_confirm_flow_reject():
    server, base = _start()
    try:
        _, text = _post(base, "/api/command", {"text": "执行 echo hello"})
        cid = json.loads(text)["confirm_id"]
        _, text = _post(base, "/api/confirm", {"confirm_id": cid, "answer": False})
        data = json.loads(text)
        assert any("已取消" in l["text"] for l in data["lines"])
        # 不应执行：pending 流已被拒绝
        assert not mcp_server.safety.pending_ids()
    finally:
        server.shutdown()
