"""pytest 共享配置：路径与环境变量。"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_config.json")


@pytest.fixture(scope="session")
def server_env():
    """子进程环境：禁用 TTS 播报、指向测试配置（不依赖真实 config.json）。"""
    env = dict(os.environ)
    env["VOICECONSOLE_NO_TTS"] = "1"
    env["VOICECONSOLE_CONFIG"] = TEST_CONFIG
    # 子进程 MCP：允许 pytest 临时目录与仓库目录（find_file 等路径沙箱）
    import tempfile as _tf
    roots = [os.path.expanduser("~"), os.getcwd(), _tf.gettempdir(), ROOT]
    env["VOICECONSOLE_PATH_ROOTS"] = os.pathsep.join(roots)
    return env
