"""语音指令控制台主程序：热键循环（默认）或交互文本模式（--text）。"""

import argparse
import os
import threading

import voiceconsole
from voiceconsole import actions, config as config_mod, intent, mcp_server, safety as safety_mod, stt

_TEXT_MODE = False  # 文本模式：确认应答改走 stdin，不初始化 STT
_QUIT_EVENT = threading.Event()


def _load_config(args) -> dict:
    path = args.config or voiceconsole.default_config_path()
    cfg = config_mod.load_config(path)
    mcp_server.configure(cfg)
    return cfg


def _speak(cfg, text: str) -> None:
    actions.speak_text(text, engine=cfg["tts_engine"])


def _handle_text(cfg, text: str) -> str | None:
    """处理一句文本：意图 → 执行 → 播报；返回 'quit' 表示退出。"""
    it = intent.parse_intent(text)
    if it.action == intent.ACTION_QUIT:
        return "quit"
    if it.action == intent.ACTION_HELP:
        _speak(cfg, "可用指令：打开文件夹、找文件、执行白名单命令、退出")
        return None
    if it.action == intent.ACTION_UNKNOWN or it.confidence < stt.CONFIDENCE_THRESHOLD:
        _speak(cfg, "没听懂，请再说一次")
        return None
    mapped = intent.map_to_tool(it)
    if mapped is None:
        _speak(cfg, "暂不支持该操作")
        return None
    tool, args = mapped
    if tool == "run_cli":
        verdict = mcp_server.safety.check_command(args["command"])
        if verdict == safety_mod.SafetyVerdict.DENIED:
            _speak(cfg, f"已拒绝执行危险命令：{args['command']}")
            return None
        if verdict == safety_mod.SafetyVerdict.NEEDS_CONFIRM and not _ask_confirm(cfg, f"确认执行 {args['command']}？"):
            _speak(cfg, "已取消")
            return None
        result = actions.run_cli_cmd(args["command"], timeout_ms=cfg["timeout_ms"])
        summary = (result.stdout or "").strip()[:200] or (result.stderr or "").strip()[:200] or f"完成（{result.elapsed_ms}ms）"
        _speak(cfg, f"执行结果：{summary}")
    elif tool == "open_folder":
        if cfg["confirm_mode"] == "all" and not _ask_confirm(cfg, f"确认打开 {args['path']}？"):
            _speak(cfg, "已取消")
            return None
        ok = actions.open_in_file_manager(args["path"])
        _speak(cfg, "已打开" if ok else "打开失败")
    elif tool == "find_file":
        try:
            matches = actions.search_files(args["pattern"], directory=args.get("directory", "."), max_hits=5)
        except NotADirectoryError:
            _speak(cfg, "目录不存在")
            return None
        if not matches:
            _speak(cfg, "没有找到匹配的文件")
        else:
            names = "、".join(m["path"] for m in matches)
            _speak(cfg, f"找到 {len(matches)} 个：{names[:200]}")
    return None


def _ask_confirm(cfg, prompt: str) -> bool:
    """播报问题并应答：热键模式录音听答，文本模式 stdin 输入。"""
    _speak(cfg, prompt)
    if _TEXT_MODE:
        try:
            answer = input(f"{prompt}（是/否）: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        return intent.is_affirmative(answer)
    answer = _record_once(cfg)
    return bool(answer) and intent.is_affirmative(answer)


def _record_once(cfg) -> str:
    """录一句音并转文本（文本模式无麦克风时直接返回文本）。"""
    wav = stt.record_until_release(max_sec=15)
    if not wav:
        return ""
    res = stt.transcribe(wav)
    print(f"[STT] {res.text} (conf={res.confidence:.2f})")
    if res.confidence < stt.CONFIDENCE_THRESHOLD:
        return ""
    return res.text


def run_text_loop(cfg) -> None:
    """交互文本模式：逐行输入指令（免麦克风演示）。"""
    global _TEXT_MODE
    _TEXT_MODE = True
    print("语音指令控制台（文本模式）。输入 '退出' 结束。")
    while True:
        try:
            line = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        print(f"[你] {line}")
        if _handle_text(cfg, line) == "quit":
            break


def run_hotkey_loop(cfg) -> None:
    """热键循环：Ctrl+Shift+Space 开始/停止录音，Ctrl+Shift+Q 退出。"""
    try:
        import keyboard
    except ImportError as e:
        print("keyboard 未安装：pip install keyboard（Windows 需以管理员运行）")
        raise SystemExit(1) from e
    stt.init_stt(cfg["stt_engine"])
    print(f"就绪。热键 {cfg['hotkey']} 开始/停止录音，Ctrl+Shift+Q 退出。")
    stop_event = threading.Event()
    busy = threading.Event()

    def record_worker():
        try:
            wav = stt.record_until_release(max_sec=15, stop_event=stop_event)
            if wav:
                res = stt.transcribe(wav)
                print(f"[STT] {res.text} (conf={res.confidence:.2f})")
                if res.confidence < stt.CONFIDENCE_THRESHOLD or not res.text:
                    _speak(cfg, "没听懂，请再说一次")
                elif _handle_text(cfg, res.text) == "quit":
                    _QUIT_EVENT.set()
        except Exception as e:
            print(f"[录音处理失败] {e}")
        finally:
            busy.clear()

    def toggle_recording():
        if busy.is_set():
            stop_event.set()
        else:
            busy.set()
            stop_event.clear()
            threading.Thread(target=record_worker, daemon=True).start()

    keyboard.add_hotkey(cfg["hotkey"], toggle_recording, suppress=False)
    keyboard.add_hotkey("ctrl+shift+q", _QUIT_EVENT.set)
    threading.Thread(target=quit_watcher, daemon=True).start()
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        pass


def quit_watcher():
    """等待退出信号后强制退出（子线程无法安全中断主线程等待）。"""
    _QUIT_EVENT.wait()
    os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="语音指令控制台 MCP（Voice Console）")
    parser.add_argument("--config", default=None, help="config.json 路径（默认项目根目录）")
    parser.add_argument("--text", action="store_true", help="交互文本模式（免麦克风/免管理员）")
    args = parser.parse_args()
    cfg = _load_config(args)
    if args.text:
        run_text_loop(cfg)
    else:
        run_hotkey_loop(cfg)


if __name__ == "__main__":
    main()
