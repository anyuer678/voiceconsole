# 威胁模型 — voiceconsole

> 状态：`local-tool` · 本机语音指令 MCP · **仅可信宿主**

## 资产

| 资产 | 说明 |
|---|---|
| 本机命令执行能力 | run_cli → subprocess |
| 文件系统可见性 | find_file / open_folder |
| 麦克风/音频 | STT；TTS 可能出网 |

## 信任边界

```text
[不可信] 恶意/被注入的 MCP 客户端 · 同机其他进程
    |
[边界] 安全门 · 确认权 local-ui · 路径沙箱 · 审计
    |
[TCB] 本机用户 + 热键/本地 Web 确认通道 + SafetyEngine
    |
[资产] 本机命令与文件
```

## 关键控制（Sprint1 硬化）

| 控制 | 行为 |
|---|---|
| **confirm_authority=local-ui（默认）** | MCP `confirm(confirm_id, answer=true)` **不能**批准；须本机 UI/热键 |
| 路径沙箱 | find_file/open_folder 默认 home+cwd，越界拒绝 |
| 安全门 | 元字符 DENY；黑名单；未知命令 needs_confirm（fail-closed 超时拒绝） |
| shell=False | 唯一 subprocess 点；内建命令 Python 原生 |
| 审计 | 默认 `~/.voiceconsole/audit.jsonl` |
| TTS | 默认 `system`；`edge` 需 `tts_allow_network=true` |

## 残余风险

- 同机其他进程可打本地 Web UI（无应用层鉴权时）
- 白名单中 ping/ps 等仍可侦察
- `confirm_authority=mcp` 显式打开后回到旧信任模型
- STT 在线 API 的数据出境（若配置）

## 披露

见仓库 SECURITY 相关说明 / Issue。
