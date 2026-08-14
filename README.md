# Voice Console —— 语音指令控制台 MCP

> 对着电脑说一句「打开桌面」或「执行 dir」，它就执行并播报结果——给 MCP / CLI 加一层本地语音入口。

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-71%20passed-brightgreen)](tests/)
[![MCP](https://img.shields.io/badge/MCP-Server-000000)](voiceconsole/)

本地语音控制台：STT 识别 → 意图解析 → 安全门 → 工具执行 → TTS 播报。以 MCP Server 形态提供 5 个工具，可被任意 MCP 客户端调用。

## 功能特性

| 能力 | 说明 |
|---|---|
| MCP Server | 标准 stdio 传输，5 个工具（`run_cli` / `find_file` / `open_folder` / `speak` / `confirm`） |
| 本地语音链路 | faster-whisper 本地 STT（无 key 可用）+ edge-tts 播报（自动降级系统 TTS） |
| 安全门 | 黑/白名单 + 注入字符拦截 + 二阶段语音确认（30s 超时自动拒绝） |
| 三种入口 | 热键语音循环 / `--text` 文本模式 / Web 控制台 |
| 零依赖 Web UI | 标准库 `http.server`，仅本机监听，不暴露密钥 |

## 快速开始

```bash
# 安装依赖（mcp / faster-whisper / edge-tts / keyboard / sounddevice ...）
pip install -r requirements.txt

# 方式 1：作为 MCP Server（任意 MCP 客户端 stdio 调用）
python -m voiceconsole

# 方式 2：本地热键语音循环（Windows 需管理员运行）
python main.py

# 方式 3：免麦克风/免管理员：交互文本模式
python main.py --text

# 方式 4：本地 Web 控制台（浏览器打开 http://127.0.0.1:8765）
python -m voiceconsole.webui --port 8765
```

热键：`Ctrl+Shift+Space` 开始/停止录音 · `Ctrl+Shift+Q` 退出。

## MCP 工具清单

| 工具 | 输入 | 说明 |
|---|---|---|
| `run_cli` | `command`, `cwd?` | 白名单执行；危险命令抛错，其余需语音确认 |
| `find_file` | `pattern`, `directory="."` | 按文件名模糊搜索 |
| `open_folder` | `path` | 系统文件管理器打开 |
| `speak` | `text` | TTS 播报 |
| `confirm` | `prompt` | 发起并等待语音确认，超时默认拒绝 |

## 项目结构

```
main.py               热键监听 + 全局循环
voiceconsole/
  __init__.py         MCP server 入口（register + run）
  __main__.py         python -m voiceconsole（stdio）
  mcp_server.py       MCP SDK 工具注册与执行编排
  safety.py           安全门：黑白名单 + 确认状态机（线程安全）
  actions.py          真实执行体（全项目唯一 subprocess 处）
  intent.py           规则意图解析 + 工具映射
  stt.py / tts.py     STT / TTS 引擎封装（含降级）
  webui.py            本地 Web 控制台（零依赖）
tests/                pytest 测试（71 例，含真实 stdio 子进程握手）
```

## 安全模型

1. 检查顺序：空命令/注入字符（`; && | > < $(` 等）→ 黑名单 → 白名单 → 其余需确认
2. 黑名单默认拒绝：`rm sudo curl wget dd mkfs mv del shutdown bash passwd net user` 等
3. 白名单默认放行：`ls cd cat pwd dir git status git log ping ps top` 等
4. 执行默认超时 10s 防挂起；密钥一律走环境变量，绝不硬编码

## 测试

```bash
python -m pytest tests/ -v
```

## 隐私与免责

- 语音与控制指令仅在本机处理；STT 使用本地模型或你配置的在线 API，TTS 使用本地/在线引擎。
- 工具可执行本机命令，请自行评估风险；确认门默认开启，危险操作需语音二次确认。
- 演示请运行 `python demo.py`（免麦克风，覆盖打开桌面/找文件/危险命令拒绝/退出全链路）。

## License

[GPL-3.0](LICENSE) — Copyright (C) 2026 anyuer678
