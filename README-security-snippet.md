# 安全硬化说明（合并入 README 顶部或「安全」章节）

> **状态**：`local-tool` · 语音控制将执行本机命令 · **仅在可信 MCP 宿主使用**  
> **威胁模型**：[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)

### Sprint1 硬化

| 项 | 默认 |
|---|---|
| `confirm_authority` | `local-ui` — MCP **不能** `confirm(confirm_id)` 自批 |
| `path_roots` | null → 默认用户主目录 + 当前工作目录；越界拒绝 |
| 审计 | `~/.voiceconsole/audit.jsonl`（可用 `audit_path` / `VOICECONSOLE_AUDIT_PATH`） |
| TTS | 默认 `system`；`edge` 需 `tts_engine=edge` **且** `tts_allow_network=true`（会出网） |

迁移：若你依赖 MCP 自批，需在 `config.json` 显式设 `"confirm_authority": "mcp"`（不推荐）。
