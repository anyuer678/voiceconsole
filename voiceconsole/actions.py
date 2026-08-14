"""真实执行体（CLI/FS），全项目唯一调用 subprocess 的地方。"""

import fnmatch
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from . import tts


@dataclass
class CLIResult:
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int


def _decode(raw: bytes) -> str:
    """优先 utf-8，其次 mbcs（中文 Windows ANSI），失败则 replace，保证不崩。"""
    for enc in ("utf-8", "mbcs"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_cli_cmd(command: str, cwd: str | None = None, timeout_ms: int = 10_000) -> CLIResult:
    """执行命令，返回结构化结果；超时按 exit_code=124 处理。"""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout_ms / 1000,
        )
        out, err, code = _decode(proc.stdout), _decode(proc.stderr), proc.returncode
    except subprocess.TimeoutExpired as e:
        out = _decode(e.stdout) if e.stdout else ""
        err = _decode(e.stderr) if e.stderr else ""
        code = 124
    except OSError as e:
        out, err, code = "", str(e), 1
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return CLIResult(stdout=out, stderr=err, exit_code=code, elapsed_ms=elapsed_ms)


def open_in_file_manager(path: str) -> bool:
    """在系统文件管理器中打开路径（explorer / open / xdg-open）。"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except OSError:
        return False


def search_files(pattern: str, directory: str = ".", max_hits: int = 20) -> list[dict]:
    """按文件名子串/通配符搜索，返回 [{path, is_dir, mtime}]。"""
    if not os.path.isdir(directory):
        raise NotADirectoryError(directory)
    matches: list[dict] = []
    pat_low = (pattern or "").lower()
    for root, dirs, files in os.walk(directory):
        for name in files + dirs:
            if len(matches) >= max_hits:
                break
            name_low = name.lower()
            if pat_low and (pat_low in name_low or fnmatch.fnmatch(name_low, pat_low)):
                full = os.path.join(root, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                matches.append({"path": full, "is_dir": os.path.isdir(full), "mtime": st.st_mtime})
    return matches[:max_hits]


def speak_text(text: str, engine: str = "edge") -> None:
    """TTS 播报（转调 tts 模块）。"""
    tts.speak_text(text, engine=engine)
