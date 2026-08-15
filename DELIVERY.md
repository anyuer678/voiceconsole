# 交付清单 — 语音指令控制台 MCP

## 一、文件清单

```
main.py                      热键主循环（默认）+ --text 文本模式
voiceconsole/
  __init__.py                MCP server 入口（注册全部工具 + run()）
  __main__.py                python -m voiceconsole（stdio）
  config.py                  配置加载/校验（allowlist/denylist 别名、环境变量校验）
  safety.py                  安全门：黑/白名单 + 确认状态机（线程安全）
  actions.py                 真实执行体（CLI/FS/TTS 转调，唯一 subprocess 处）
  intent.py                  规则意图解析 + 工具映射 + 确认应答判断
  stt.py                     STTResult / init_stt(auto|local|api) / transcribe / record_until_release
  tts.py                     edge-tts 优先、系统 TTS 降级、尽力播报
  mcp_server.py              5 个 MCP 工具注册与编排
  webui.py                  本地 Web 控制台（标准库 http.server，零依赖）
tests/
  conftest.py + test_config.json   共享 fixture（禁用 TTS、隔离配置）
  test_safety.py             14 项：黑/白名单、注入、确认流、超时、线程安全
  test_intent.py             12 项：规则解析、工具映射、确认应答
  test_actions.py            10 项：CLI 执行/超时/cwd、搜索、打开、TTS 转调
  test_stt.py                 9 项：引擎判定、本地/API mock、录音 mock
  test_mcp.py                10 项：真实 stdio 子进程 + 确认流编排
  test_main.py                8 项：文本链路全分支（退出/帮助/未知/白名单/拒绝/确认/打开/搜索）
  test_webui.py               6 项：Web 路由、指令链路、确认流批准/拒绝
  test_conn.py                1 项：Phase 1 验收（connect + speak）
config.json                  默认配置
demo.py                      免麦克风演示脚本（可录屏）
README.md                    安装/热键/白名单/配置/安全说明
requirements.txt / pyproject.toml
```

## 二、验证结果（本机 Windows / Python 3.12.3）

- `python -m pytest tests/ -v` → **71 passed**（含 test_conn.py、test_mcp.py 真实 stdio 链路、test_main.py 文本链路、test_webui.py Web 链路）
- `python -m voiceconsole` stdio 握手 + `list_tools` 返回 5 工具：`run_cli / find_file / open_folder / speak / confirm`
- `speak("你好")` 返回 `{"ok": true}`；`run_cli("dir")` 返回 `exit_code: 0`；`run_cli("rm -rf /")` 被拒绝
- Web 端到端：`GET /` → 200；`执行 dir` → exit_code=0；`执行 rm -rf /` → 拒绝；`执行 echo hello` → need_confirm → 批准后 exit_code=0；`退出` → 面板内忽略
- `python main.py --text` 文本模式全链路可用（免麦克风）：`执行 dir`→执行+播报、`执行 rm -rf /`→拒绝播报、`找 voiceconsole`→找到 1 个；热键模式需管理员权限 + `keyboard`/`sounddevice` 已安装

## 三、接口核对清单（架构 §6，全部通过）

- [x] `record_audio → STTResult` 30s 内可用（本地模型 30s 内返回；测试 mock 验证结构）
- [x] `SafetyGate.check("rm -rf /") == denied` 必过测试（tests/test_safety.py::test_deny_blacklist）
- [x] 工具 description 含示例例句（5 个工具均带 demo 例句）
- [x] `confirm_state` 超时=取消（tests/test_safety.py::test_confirm_timeout_then_reject）

## 六、本轮修复（审计发现 + 前端新增）

**Bug 修复（main.py / safety.py）**

1. 文本模式确认会真实录音 15s 且强制初始化 STT（可能触发模型下载）→ `_ask_confirm` 在 `--text` 下改走 stdin，`run_text_loop` 不再调用 `init_stt`
2. 热键模式语音指令「退出」不生效（worker 线程抛 `KeyboardInterrupt` 只影响自身）→ 改 `_QUIT_EVENT` + 守护线程 `quit_watcher()`，`Ctrl+Shift+Q` 也走同一退出通道
3. `_handle_text` 的 `find_file` 未捕获 `NotADirectoryError`（目录不存在直接崩溃）→ 捕获并播报「目录不存在」
4. `SafetyEngine` 新增 `pending_ids()` 公共方法，供 Web 面板发现并应答确认流（非破坏性扩展）

**安全加固（消除 shell 注入面）**

1. `safety.py` 元字符表补 `&`：单 `&` 命令拼接（`dir & whoami`）此前被误放行 → 现拒绝
2. `actions.run_cli_cmd` 改为**不经 shell 执行**：外部命令拆分为 argv 后 `subprocess.run(args, shell=False)`；内建命令（`ls`/`dir`/`cd`/`pwd`/`cat`/`type`/`echo`）用 Python 原生实现（`os.listdir`/`os.chdir`/读文件/回显）。即使元字符检查被绕过，`;`/`&`/`|`/`$()`/`` ` `` 也仅是普通字符，无 shell 执行语义——命令注入面从根上消除（新增测试 `test_run_cli_builtin_no_shell` / `test_run_cli_external_argv_no_shell`）

**前端新增（webui.py，零新依赖）**

- 形态：标准库 `http.server`（`ThreadingHTTPServer`）起本地 Web 控制台，仅绑定 `127.0.0.1`，内嵌单页 HTML/JS（无外部 CDN，离线可用）
- 链路：页面 → `POST /api/command` → `intent` → `safety`（白/黑名单）→ `mcp_server` 工具层 → `actions` 执行，与语音/MCP 完全同一套安全门
- 确认：需要确认的命令返回 `need_confirm + confirm_id`，前端弹确认框，`POST /api/confirm` 应答；批准后直接走 `actions` 层重放（用户已授权，避免再次触发确认流）
- 功能：指令输入、执行日志（时间戳/判定/输出）、快捷演示按钮（5 工具）、🎤 录音 5s→STT→执行（可选）、退出指令在面板内被忽略
- 安全：仅回环地址、不暴露密钥、命令仍受白/黑名单与确认门控

**兼容性**：未修改任何文档契约（工具签名、JSON schema、CLI 参数、退出码）；`SafetyEngine.pending_ids` 与 `webui` 为纯新增。

## 七、文档矛盾裁定（已按优先级：架构设计 > 开发规范）

1. 确认工具名：规范 §3 为 `confirm_action(confirm: bool)`，架构 §3.2 为 `confirm(prompt) -> {'ok': bool}` —— **采用 `confirm`**
2. 测试文件：规范 §7 要求 `test_mcp.py`，规划 Phase 1 要求 `test_conn.py` —— **两者都保留**
3. 核对清单 `SafetyGate.check` —— 按架构正文 §3.3 实现为 `SafetyEngine.check_command`
4. 配置键：规范 §6 用 `whitelist/blacklist/confirm`，架构 §3.5 用 `allowlist/denylist/confirm_mode` —— **架构为准，并提供别名兼容规范**

## 八、对文档的补充说明（实现需要，未改契约）

| 项 | 说明 | 理由 |
|---|---|---|
| `sounddevice`+`soundfile` | 新增录音依赖（规范 §1 依赖名单外） | 契约要求 `record_until_release` 产出 wav bytes，标准库无录音 API |
| `record_until_release(..., stop_event=None)` | 契约签名外加可选参数 | main 热键循环需要"按键停止录音"；缺省行为与契约一致（录满 max_sec） |
| `SafetyEngine.await_confirm` | 新增辅助方法 | MCP 工具层需阻塞等待确认结果（resolve 仍按契约） |
| `is_affirmative(text)` | intent.py 新增 | 确认应答"是/对/yes"判定，供 main/确认流使用 |
| `VOICECONSOLE_NO_TTS` / `VOICECONSOLE_CONFIG` | 环境变量（可选） | 测试隔离与 CI 稳定性；不影响正常运行 |
| `confirm_mode=all` 时 `open_folder` 需确认 | 规范 §5"白名单外工具需确认"在 all 模式生效 | dangerous-only 下 open_folder 无害直接执行（可测试性 + 合理语义） |
| LLM 意图模式 | `config.get_env_llm()` 预留，默认规则引擎 | 契约"无 LLM key 也能跑"优先 |
| mcp SDK 2.0 | 官方 2.0 已移除 FastMCP，用 `MCPServer` + `@server.tool()` | 与文档"官方 SDK 装饰器"一致；客户端需显式 `session.initialize()` |
