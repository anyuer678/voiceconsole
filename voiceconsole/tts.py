"""文本转语音：edge-tts（在线合成）或系统 TTS（离线），尽力播报不抛错。"""

import asyncio
import os
import subprocess
import sys
import tempfile

_EDGE_AVAILABLE: bool | None = None


def _edge_available() -> bool:
    global _EDGE_AVAILABLE
    if _EDGE_AVAILABLE is None:
        try:
            import edge_tts  # noqa: F401
            _EDGE_AVAILABLE = True
        except ImportError:
            _EDGE_AVAILABLE = False
    return _EDGE_AVAILABLE


def _play_mp3(path: str) -> bool:
    """用系统默认播放器/命令播放 mp3，失败返回 False。"""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["afplay", path])
            return True
        for player in ("aplay", "ffplay", "mpv"):
            if _which(player):
                subprocess.Popen([player, path])
                return True
    except OSError:
        return False
    return False


def _which(name: str) -> bool:
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        if os.path.isfile(os.path.join(d, name)):
            return True
    return False


async def _edge_speak_async(text: str) -> bool:
    import edge_tts
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
    tmp = os.path.join(tempfile.gettempdir(), "_voiceconsole_tts.mp3")
    await communicate.save(tmp)
    return _play_mp3(tmp)


def _system_speak(text: str) -> bool:
    """Windows PowerShell System.Speech（需系统装有对应语音包）。"""
    if sys.platform != "win32":
        return False
    escaped = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True,
            timeout=30,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def speak_text(text: str, engine: str = "edge") -> None:
    """播报文本；edge 失败自动降级 system，全部失败则静默。"""
    if not text:
        return
    if os.environ.get("VOICECONSOLE_NO_TTS"):
        return
    if engine == "edge" and _edge_available():
        try:
            if asyncio.run(_edge_speak_async(text)):
                return
        except Exception:
            pass
    if not _system_speak(text):
        print(f"[TTS-不可用] {text}", file=sys.stderr)
