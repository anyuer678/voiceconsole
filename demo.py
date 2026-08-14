"""演示脚本：模拟一次"语音 → 意图 → 安全门 → 执行 → 播报"全链路（免麦克风）。

用法：python demo.py
说明：open_folder 会真实打开资源管理器窗口（演示本意）。
"""

import voiceconsole
from voiceconsole import actions, config as config_mod, intent, mcp_server, safety as safety_mod


def main() -> None:
    cfg = config_mod.load_config(voiceconsole.default_config_path())
    mcp_server.configure(cfg)
    samples = [
        "打开桌面",
        "找 report",
        "执行 dir",
        "执行 rm -rf /",
        "打开 C:/Users/Public",
        "退出",
    ]
    for text in samples:
        print(f"\n[语音] {text}")
        it = intent.parse_intent(text)
        if it.action == intent.ACTION_QUIT:
            print("[系统] 播报：再见")
            break
        if it.action == intent.ACTION_UNKNOWN:
            print("[系统] 播报：没听懂，请再说一次")
            continue
        mapped = intent.map_to_tool(it)
        if mapped is None:
            print("[系统] 播报：暂不支持该操作")
            continue
        tool, args = mapped
        if tool == "run_cli":
            verdict = mcp_server.safety.check_command(args["command"])
            print(f"[安全门] {args['command']} → {verdict}")
            if verdict == safety_mod.SafetyVerdict.DENIED:
                print("[系统] 播报：已拒绝执行危险命令")
                continue
            result = actions.run_cli_cmd(args["command"], timeout_ms=cfg["timeout_ms"])
            summary = (result.stdout or result.stderr or "").strip()[:120]
            print(f"[执行] exit={result.exit_code} {result.elapsed_ms}ms → {summary}")
            print("[系统] 播报：执行结果已回读")
        elif tool == "open_folder":
            print(f"[执行] 在资源管理器中打开 {args['path']}")
            ok = actions.open_in_file_manager(args["path"])
            print("[系统] 播报：已打开" if ok else "[系统] 播报：打开失败")
        elif tool == "find_file":
            hits = actions.search_files(args["pattern"], max_hits=5)
            print(f"[执行] 找到 {len(hits)} 个：")
            for h in hits[:3]:
                print(f"   {h['path']}")
            print("[系统] 播报：找到结果已回读")
    print("\n演示结束。真实语音模式：python main.py（热键 Ctrl+Shift+Space）。")


if __name__ == "__main__":
    main()
