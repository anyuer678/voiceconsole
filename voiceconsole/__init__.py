"""语音指令控制台 MCP Server 入口（注册全部工具）。"""

import os

from . import actions, config as config_mod, intent, mcp_server, safety, stt, tts
from .mcp_server import server

__all__ = [
    "actions", "config", "intent", "mcp_server", "safety", "stt", "tts",
    "server", "run",
]


def default_config_path() -> str:
    """默认 config.json 路径：环境变量 VOICECONSOLE_CONFIG 或项目根目录。"""
    env = os.environ.get("VOICECONSOLE_CONFIG")
    if env:
        return env
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "config.json")


def run() -> None:
    """启动 stdio MCP server（python -m voiceconsole）。"""
    cfg = config_mod.load_config(default_config_path())
    mcp_server.configure(cfg)
    server.run(transport="stdio")
