# 语音指令控制台 MCP（Voice Console）

对着电脑说一句"打开桌面"或"执行 dir"，它就执行并播报结果——给 MCP / CLI 加一层本地语音入口。

```
短按热键说"打开 nginx 日志"
→ 本地 STT（faster-whisper 或在线 API）→ 意图解析 → MCP 工具调用
→ 安全门（白名单/黑名单/语音确认）→ 执行 → TTS 播报结果
```

## 架构

```
main.py          热键监听 + 全局循环（生命周期）
stt.py / intent.py / tts.py        语音转文本 / 意图→工具 / 文本转语音
mcp_server.py    MCP SDK 工具注册与执行编排（5 个工具）
safety.py        白名单/黑名单 + 确认状态机（线程安全）
actions.py       真实执行体（CLI/FS，唯一 subprocess 调用处）
webui.py         本地 Web 控制台（标准库 http.server，零依赖）
```

## 安装

```powershell
pip install -r requirements.txt
```

- 依赖：`mcp`（官方 SDK）、`faster-whisper`（STT）、`edge-tts`（TTS）、`keyboard`（热键）、`sounddevice`+`soundfile`（录音）
- 本地 STT 首次运行会下载 base 模型（约 150MB）；无模型/无 key 时自动提示
- `keyboard` 热键模式在 Windows 需以**管理员身份**运行；否则请用 `--text` 文本模式

## 快速开始

```powershell
# 1) 作为 MCP server（任意 MCP 客户端 / stdio 调用）
python -m voiceconsole

# 2) 本地热键语音循环（默认，管理员运行）
python main.py

# 3) 免麦克风/免管理员：交互文本模式
python main.py --text

# 4) 本地 Web 控制台（浏览器打开 http://127.0.0.1:8765）
python -m voiceconsole.webui --port 8765
```

热键：

| 热键 | 作用 |
|---|---|
| `Ctrl+Shift+Space` | 开始 / 停止录音（对讲机式） |
| `Ctrl+Shift+Q` | 退出 |

## Web 面板（前端）

`python -m voiceconsole.webui` 启动一个仅本机可访问（`127.0.0.1`）的 Web 控制台，用浏览器操作同一套指令链路：

- **指令输入**：自然语言 → `intent` → `safety`（白/黑名单 + 确认）→ `actions` 真实执行，全程复用 `mcp_server` 工具层
- **确认框**：危险/非白名单命令弹出「确认执行」对话框，批准后才执行，取消即终止
- **执行日志**：时间戳 + 判定（允许/拒绝/确认）+ 输出，实时滚动
- **快捷演示**：一键调用 5 个 MCP 工具（`dir` / 找文件 / 打开桌面 / `speak`）
- **语音录音**（可选）：点击 🎤 录音 5 秒 → STT 识别 → 按指令执行，需麦克风与 `sounddevice`
- 零第三方依赖（标准库 `http.server`），不暴露任何密钥；退出指令在 Web 面板中被忽略

## MCP 工具清单

| 工具 | 输入 | 返回 | 说明 |
|---|---|---|---|
| `run_cli` | `command: str`, `cwd?` | `{stdout, stderr, exit_code, elapsed_ms}` | 白名单执行；危险命令抛错；其余需语音确认 |
| `find_file` | `pattern: str`, `directory="."` | `{matches:[{path,is_dir,mtime}], limit:20}` | 按文件名模糊搜索 |
| `open_folder` | `path: str` | `{ok}` / `{ok:false, error}` | 资源管理器打开（`confirm_mode=all` 时需确认） |
| `speak` | `text: str` | `{ok}` | TTS 播报 |
| `confirm` | `prompt: str` | `{ok: bool}` | 发起并等待一次语音确认，超时默认拒绝 |

Python client 示例：

```python
import asyncio, sys
from mcp import ClientSession, StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "voiceconsole"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            res = await session.call_tool("speak", {"text": "你好"})
            print(res.content[0].text)

asyncio.run(main())
```

## 配置（config.json）

```json
{
  "stt_engine": "auto",          // auto|local|api（auto：有 OPENAI_API_KEY 走 api，否则本地）
  "tts_engine": "edge",          // edge|system（edge-tts 失败自动降级系统播报）
  "hotkey": "<ctrl>+<shift>+space",
  "allowlist": [],               // 追加白名单前缀（默认已含 ls/cd/cat/git status/ping 等）
  "denylist": [],                // 追加黑名单前缀（默认已含 rm/sudo/curl/shutdown 等）
  "confirm_mode": "dangerous-only", // dangerous-only|all
  "timeout_ms": 10000            // 命令执行超时
}
```

- 兼容别名：`whitelist`/`blacklist`（对应 allowlist/denylist）、`confirm: true`（等效 `confirm_mode: "all"`）
- 可用 `--config <路径>` 或环境变量 `VOICECONSOLE_CONFIG` 指定配置文件
- 可选环境变量：`OPENAI_API_KEY`（在线 STT）、`LLM_API_KEY`/`LLM_BASE_URL`（可选 LLM 意图模式，默认规则引擎）

## 安全模型

1. **检查顺序**：空命令/注入字符（`; && | > < $( \`` 等）→ 黑名单 → 白名单 → 其余需确认
2. **黑名单**（默认拒绝）：`rm sudo curl wget dd mkfs mv del shutdown bash passwd chpasswd net user`
3. **白名单**（默认放行）：`ls cd cat pwd where systeminfo tasklist dir git status git log ping ps top`
4. **二阶段确认**：白名单外命令 / `confirm_mode=all` 时的全部工具 → 播报"确认执行 xxx？" → 用户答"是/对/yes"才执行；**30 秒超时自动取消**
5. 所有执行默认 `timeout=10s`，防挂起；密钥一律走环境变量，绝不硬编码
6. 低置信（< 0.55）或未识别 → 播报"没听懂，请再说一次"，不执行

## 测试

```powershell
python -m pytest tests/ -v
```

覆盖：安全门（黑/白名单、注入、确认状态机、超时、线程安全）、意图解析与映射、执行体（CLI/搜索/打开）、STT（引擎判定、本地/API/录音 mock）、MCP 层（真实 stdio 子进程：握手、工具列表、`speak`、白名单执行、危险命令拒绝、确认流）、Web 控制台（路由、指令链路、确认流、拒绝/未知指令）。

## 演示

```powershell
python demo.py
```

免麦克风演示完整链路（打开桌面 / 找文件 / 白名单执行 / 危险命令拒绝 / 退出）。
