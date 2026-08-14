"""本地 Web 控制台：标准库 http.server 实现，零第三方依赖。

设计：网页 → /api/command → intent → mcp_server 工具函数（复用安全门与执行链路）。
确认流程：工具阻塞 await_confirm 期间，前端经 /api/confirm 应答。
仅绑定 127.0.0.1，不暴露任何密钥；退出指令在 Web 面板中被忽略。
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import actions, intent, mcp_server, safety as safety_mod, stt

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>语音指令控制台 · Web 面板</title>
<style>
/* ============ 设计令牌（kb-ui 风格） ============ */
:root {
  --kb-color-primary:#22c55e; --kb-color-success:#4ade80; --kb-color-warning:#facc15;
  --kb-color-danger:#f87171; --kb-color-info:#38bdf8;
  --kb-color-bg:#0a0f0a; --kb-color-bg-elevated:#101810; --kb-color-border:#1f3d23;
  --kb-color-text-1:#86efac; --kb-color-text-2:#4ade80; --kb-color-text-3:#22c55e;
  --kb-radius-sm:0; --kb-radius-md:0; --kb-radius-lg:0; --kb-radius-round:0;
  --kb-shadow-1:none; --kb-shadow-2:none;
  --kb-font:"Cascadia Code","Consolas","Courier New",ui-monospace,monospace;
  --kb-mono:"Cascadia Code","Consolas","Courier New",monospace;
  --kb-space-1:4px; --kb-space-2:8px; --kb-space-3:12px; --kb-space-4:16px; --kb-space-5:20px; --kb-space-6:24px;
}
/* ============ 组件基座 ============ */
* { box-sizing:border-box; }
body { margin:0; background:var(--kb-color-bg); color:var(--kb-color-text-1);
       font:15px/1.6 var(--kb-font); padding:var(--kb-space-6); transition:background .2s,color .2s; }
.wrap { max-width:860px; margin:0 auto; }
.topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:var(--kb-space-4); flex-wrap:wrap; }
h1 { font-size:21px; margin:0; font-weight:600; letter-spacing:.5px; }
.sub { color:var(--kb-color-text-3); font-size:13px; margin:6px 0 0; }
.panel { background:var(--kb-color-bg-elevated); border:1px solid var(--kb-color-border);
         border-radius:var(--kb-radius-lg); padding:var(--kb-space-4); margin-bottom:var(--kb-space-4); }
.row { display:flex; gap:10px; align-items:center; }
input[type=text] { flex:1; background:var(--kb-color-bg); color:var(--kb-color-text-1);
  border:1px solid var(--kb-color-border); border-radius:var(--kb-radius-md);
  padding:10px 12px; font-size:14px; font-family:inherit; transition:border-color .15s; }
input[type=text]:focus { outline:none; border-color:var(--kb-color-primary); }
button { background:var(--kb-color-bg-elevated); color:var(--kb-color-text-1);
  border:1px solid var(--kb-color-border); border-radius:var(--kb-radius-md);
  padding:9px 16px; cursor:pointer; font-size:13.5px; font-family:inherit;
  transition:border-color .15s,background .15s; }
button:hover { border-color:var(--kb-color-primary); }
button:disabled { opacity:.45; cursor:not-allowed; }
button.primary { background:var(--kb-color-primary); color:var(--kb-color-bg); border-color:var(--kb-color-primary); font-weight:600; }
button.primary:hover { filter:brightness(1.08); }
button.danger { background:var(--kb-color-danger); color:#fff; border-color:var(--kb-color-danger); }
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chip { font-size:12.5px; padding:6px 12px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; vertical-align:middle; }
.dot.off { background:var(--kb-color-text-3); } .dot.rec { background:var(--kb-color-danger); animation:blink 1s infinite; }
@keyframes blink { 50% { opacity:.2; } }
#log { font-family:var(--kb-mono); font-size:12.5px; max-height:340px; overflow-y:auto;
       background:var(--kb-color-bg); border:1px solid var(--kb-color-border); border-radius:var(--kb-radius-md); }
.line { padding:5px 10px; border-bottom:1px solid var(--kb-color-border); white-space:pre-wrap; word-break:break-all; }
.t { color:var(--kb-color-text-3); margin-right:8px; }
.ok { color:var(--kb-color-success); } .warn { color:var(--kb-color-warning); } .err { color:var(--kb-color-danger); } .info { color:var(--kb-color-primary); }
#modal { position:fixed; inset:0; background:color-mix(in srgb,var(--kb-color-bg) 60%,transparent);
         display:none; align-items:center; justify-content:center; z-index:100; }
#modal .box { background:var(--kb-color-bg-elevated); border:1px solid var(--kb-color-warning);
              border-radius:var(--kb-radius-lg); padding:22px; width:440px; max-width:92vw;
              box-shadow:var(--kb-shadow-2); }
#modal .q { margin-bottom:14px; font-size:14.5px; }
.muted { color:var(--kb-color-text-3); font-size:12px; }
.panel-head { font-size:12.5px; color:var(--kb-color-text-3); letter-spacing:1px;
              text-transform:uppercase; margin-bottom:10px; font-weight:500; }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <h1>语音指令控制台 <span style="color:var(--kb-color-text-3);font-weight:400;font-size:13px">Web 面板</span></h1>
      <div class="sub">本地控制台（127.0.0.1）。输入自然语言指令，如「执行 dir」「找 report」「打开桌面」。</div>
    </div>
      </div>

  <div class="panel">
    <div class="row">
      <input type="text" id="cmd" placeholder="输入指令…（Enter 发送）" autocomplete="off">
      <button class="primary" id="send">执行</button>
      <button id="rec" title="录音 5 秒并识别（需麦克风与 sounddevice）">录音</button>
    </div>
    <div class="muted" style="margin-top:10px" id="recHint"><span class="dot off" id="dot"></span>录音按钮需安装 sounddevice/soundfile 且有麦克风</div>
  </div>

  <div class="panel">
    <div class="panel-head">快捷演示</div>
    <div class="chips" id="chips">
      <button class="chip">执行 dir</button>
      <button class="chip">找 voiceconsole</button>
      <button class="chip">打开桌面</button>
      <button class="chip">speak 你好</button>
    </div>
  </div>

  <div class="panel">
    <div class="panel-head">执行日志</div>
    <div id="log"><div class="line muted">等待指令…</div></div>
  </div>
</div>

<div id="modal">
  <div class="box">
    <div class="q" id="modalQ">确认执行该操作？</div>
    <div class="row">
      <button class="danger" style="flex:1" id="no">取消</button>
      <button class="primary" style="flex:1" id="yes">确认执行</button>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const log = $("log");
let pendingCid = null, pendingResolve = null;

function stamp(){ const d=new Date(); return d.toTimeString().slice(0,8); }
function addLine(kind, text){
  const div=document.createElement("div");
  div.className="line";
  div.innerHTML = `<span class="t">${stamp()}</span><span class="${kind}">${escapeHtml(text)}</span>`;
  log.appendChild(div); log.scrollTop = log.scrollHeight;
}
function escapeHtml(s){ return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

async function post(url, body){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
                              body: JSON.stringify(body||{})});
  return r.json();
}

async function runCommand(text){
  if(!text.trim()) return;
  $("cmd").value="";
  const t0 = Date.now();
  try{
    const res = await post("/api/command", {text});
    const ms = Date.now()-t0;
    if(res.status === "need_confirm"){
      pendingCid = res.confirm_id;
      $("modalQ").textContent = res.prompt;
      $("modal").style.display = "flex";
      addLine("warn", `[需要确认] ${res.prompt}`);
      return;
    }
    res.lines.forEach(l => addLine(l.kind, l.text + (l.kind==="ok" ? `（${ms}ms）` : "")));
  }catch(e){ addLine("err", "请求失败: " + e.message); }
}

async function answerConfirm(yes){
  $("modal").style.display = "none";
  if(pendingCid === null) return;
  const cid = pendingCid; pendingCid = null;
  const res = await post("/api/confirm", {confirm_id: cid, answer: yes});
  addLine(yes ? "ok" : "err", yes ? "已确认，继续执行" : "已取消");
  if(yes && res.continue_text){ runCommand(res.continue_text); }
}

$("send").onclick = () => runCommand($("cmd").value);
$("cmd").addEventListener("keydown", e => { if(e.key==="Enter") runCommand($("cmd").value); });
$("yes").onclick = () => answerConfirm(true);
$("no").onclick  = () => answerConfirm(false);

$("chips").addEventListener("click", e => {
  if(e.target.tagName === "BUTTON") runCommand(e.target.textContent.replace(/^(执行|找|打开|speak)\s*/, m => m));
});

$("rec").onclick = async () => {
  $("rec").disabled = true; $("dot").className = "dot rec";
  addLine("info", "录音 5 秒…");
  try{
    const res = await post("/api/record", {});
    $("dot").className = "dot off";
    addLine("info", `识别: ${res.text || "(无)"}`);
    if(res.text && res.result) res.result.lines.forEach(l => addLine(l.kind, l.text));
    if(res.error) addLine("err", res.error);
  }catch(e){ $("dot").className="dot off"; addLine("err", "录音失败: " + e.message); }
  $("rec").disabled = false;
};
</script>
</body>
</html>

"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "VoiceConsole/1.0"

    def log_message(self, fmt, *args):  # 安静日志
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        body = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/":
            self._html()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        try:
            if path == "/api/command":
                self._json(_api_command(data))
            elif path == "/api/confirm":
                self._json(_api_confirm(data))
            elif path == "/api/record":
                self._json(_api_record())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # 服务端兜底，不泄露堆栈
            self._json({"error": str(e)}, 500)


# ---------- API 逻辑（可在测试中直接调用） ----------

def _log(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text}


def _tool_result_to_lines(result) -> list[dict]:
    """把工具返回（dict 或 CLIResult）转成日志行。"""
    lines = []
    if not isinstance(result, dict):
        # CLIResult 等 dataclass
        result = {
            "stdout": getattr(result, "stdout", ""),
            "stderr": getattr(result, "stderr", ""),
            "exit_code": getattr(result, "exit_code", None),
            "elapsed_ms": getattr(result, "elapsed_ms", None),
        }
    for k in ("stdout", "stderr"):
        v = (result.get(k) or "").strip()
        if v:
            lines.append(_log("ok" if k == "stdout" else "err", v[:500]))
    if "exit_code" in result:
        code = result["exit_code"]
        lines.append(_log("ok" if code == 0 else "err", f"exit_code={code} elapsed={result.get('elapsed_ms', '?')}ms"))
    if "matches" in result:
        hits = result["matches"]
        lines.append(_log("ok", f"找到 {len(hits)} 个") if hits else _log("warn", "未找到匹配文件"))
        for m in hits[:5]:
            lines.append(_log("info", m["path"]))
    if result.get("ok") is True and "exit_code" not in result:
        lines.append(_log("ok", "完成"))
    if result.get("error"):
        lines.append(_log("err", result["error"]))
    return lines


def _api_command(data: dict) -> dict:
    """处理一条文本指令：intent → 工具调用；需要确认时返回 need_confirm。"""
    text = (data.get("text") or "").strip()
    if not text:
        return {"status": "error", "lines": [_log("err", "指令为空")]}
    it = intent.parse_intent(text)
    if it.action == intent.ACTION_QUIT:
        return {"status": "ok", "lines": [_log("warn", "Web 面板不支持退出指令（请关闭本页/进程）")]}
    if it.action == intent.ACTION_HELP:
        return {"status": "ok", "lines": [_log("info", "可用：执行 <命令> / 找 <文件名> / 打开 <路径> / speak <文本>")]}
    if it.action == intent.ACTION_UNKNOWN:
        return {"status": "ok", "lines": [_log("err", "没听懂，请换一种说法")]}
    mapped = intent.map_to_tool(it)
    if mapped is None:
        return {"status": "ok", "lines": [_log("err", "暂不支持该操作")]}
    tool, args = mapped
    before = set(mcp_server.safety.pending_ids())
    # 危险命令直接拒绝（与 MCP 工具一致）
    if tool == "run_cli":
        verdict = mcp_server.safety.check_command(args["command"])
        if verdict == safety_mod.SafetyVerdict.DENIED:
            return {"status": "ok", "lines": [_log("err", f"危险命令被拒绝：{args['command']}")]}
        if verdict == safety_mod.SafetyVerdict.NEEDS_CONFIRM:
            return _request_confirm("run_cli", args, f"确认执行 {args['command']}？")
    if tool == "open_folder" and mcp_server._config.get("confirm_mode") == "all":
        return _request_confirm("open_folder", args, f"确认打开 {args['path']}？")
    try:
        fn = {"run_cli": mcp_server.run_cli, "find_file": mcp_server.find_file,
              "open_folder": mcp_server.open_folder, "speak": mcp_server.speak}[tool]
        result = fn(**args)
    except Exception as e:
        return {"status": "ok", "lines": [_log("err", f"执行失败: {e}")]}
    return {"status": "ok", "lines": _tool_result_to_lines(result)}


def _request_confirm(tool: str, args: dict, prompt: str) -> dict:
    """发起确认流并立即返回 need_confirm（前端应答后重发原指令）。"""
    cid = mcp_server.safety.start_confirm_flow(tool, args)
    return {"status": "need_confirm", "confirm_id": cid, "prompt": prompt,
            "tool": tool, "args": args}


def _api_confirm(data: dict) -> dict:
    """应答确认流；批准则同步重放原工具调用。"""
    cid = (data.get("confirm_id") or "").strip()
    answer = bool(data.get("answer", False))
    if not cid:
        return {"status": "error", "lines": [_log("err", "缺少 confirm_id")]}
    ok = mcp_server.safety.resolve_confirm(cid, answer)
    if not ok:
        return {"status": "ok", "lines": [_log("err", "已取消")]}
    lines = [_log("ok", "已确认")]
    # 批准后重放（用户已授权，直接走 actions 层，避免再次触发确认流）
    tool, args = _pending_tool_args(cid)
    if tool == "run_cli":
        try:
            result = actions.run_cli_cmd(args.get("command", ""),
                                         timeout_ms=mcp_server._config.get("timeout_ms", 10000))
            lines.extend(_tool_result_to_lines(result))
        except Exception as e:
            lines.append(_log("err", f"执行失败: {e}"))
    elif tool == "open_folder":
        ok_open = actions.open_in_file_manager(args.get("path", ""))
        lines.append(_log("ok", "已打开") if ok_open else _log("err", "打开失败"))
    return {"status": "ok", "lines": lines}


def _pending_tool_args(cid: str) -> tuple[str, dict] | None:
    """从 pending 记录还原工具与参数（resolve 后条目仍在 _pending）。"""
    with mcp_server.safety._lock:
        entry = mcp_server.safety._pending.get(cid)
    if entry is None:
        return None
    return entry.tool, entry.args


def _api_record() -> dict:
    """录音 5 秒 → 识别 → 按指令执行；返回识别文本与执行结果。"""
    try:
        wav = stt.record_until_release(max_sec=5)
    except RuntimeError as e:
        return {"error": str(e)}
    if not wav:
        return {"text": "", "error": "未捕捉到声音"}
    stt.init_stt(mcp_server._config.get("stt_engine", "auto"))
    res = stt.transcribe(wav)
    if not res.text or res.confidence < stt.CONFIDENCE_THRESHOLD:
        return {"text": res.text, "error": "识别置信度不足"}
    result = _api_command({"text": res.text})
    return {"text": res.text, "result": result}


def start_server(port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """启动 Web 控制台（127.0.0.1，仅本机可访问）。"""
    server = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    import argparse

    from . import config as config_mod

    parser = argparse.ArgumentParser(description="语音指令控制台 Web 面板")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    import voiceconsole

    cfg = config_mod.load_config(args.config or voiceconsole.default_config_path())
    mcp_server.configure(cfg)
    server = start_server(args.port)
    print(f"Web 控制台已启动：http://127.0.0.1:{args.port}  （Ctrl+C 停止）")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
