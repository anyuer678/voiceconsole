"""Phase 1 验收：连接 stdio server 并成功调用 speak（开发规划验证项）。"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client


def test_conn_speak(server_env):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "voiceconsole"], env=server_env
    )

    async def main():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool("speak", {"text": "你好"})
                return res

    res = asyncio.run(main())
    assert not res.is_error
    text = res.content[0].text if res.content else ""
    assert '"ok": true' in text
