"""真实执行体（CLI/FS），全项目唯一调用 subprocess 的地方。"""

import fnmatch
import os
import shlex
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


# ---- 内建命令原生执行（不产生子进程，彻底消除 shell 注入面） ----
# 这些命令是 shell 内建（cmd/bash），argv 方式无法直接执行；用 Python 原生实现。
_BUILTIN_DIR = {"ls", "dir"}
_BUILTIN_CD = {"cd", "pwd"}
_BUILTIN_CAT = {"cat", "type"}
_BUILTIN_ECHO = {"echo"}


def _split_command(command: str) -> list[str]:
    """把命令字符串拆成 argv。

    Windows：用 posix=False 保留 `C:\\path` 反斜杠，随后剥离参数首尾的成对引号
    （posix=True 会吞掉反斜杠）。这样引号内空格合并为一个参数，且反斜杠路径不被破坏。
    """
    if sys.platform == "win32":
        args = shlex.split(command, posix=False)
        return [a[1:-1] if len(a) >= 2 and a[0] == '"' and a[-1] == '"' else a
                for a in args]
    return shlex.split(command)


def _run_builtin(args: list[str], cwd: str | None) -> CLIResult:
    """内建命令的原生实现：ls/dir/cd/pwd/cat/type。返回 CLIResult 兼容结构。"""
    cmd = args[0].lower()
    start = time.monotonic()
    try:
        base = os.path.abspath(cwd) if cwd else os.getcwd()
        if cmd in _BUILTIN_DIR:
            target = os.path.join(base, args[1]) if len(args) > 1 else base
            if not os.path.isdir(target):
                return CLIResult("", f"目录不存在: {target}", 1,
                                 int((time.monotonic() - start) * 1000))
            names = sorted(os.listdir(target))
            lines = []
            for n in names:
                full = os.path.join(target, n)
                suffix = "/" if os.path.isdir(full) else ""
                lines.append(n + suffix)
            return CLIResult("\n".join(lines) + "\n", "", 0,
                             int((time.monotonic() - start) * 1000))
        if cmd == "cd":
            target = os.path.join(base, args[1]) if len(args) > 1 else base
            if not os.path.isdir(target):
                return CLIResult("", f"目录不存在: {target}", 1,
                                 int((time.monotonic() - start) * 1000))
            os.chdir(target)
            return CLIResult("", "", 0, int((time.monotonic() - start) * 1000))
        if cmd == "pwd":
            return CLIResult(os.getcwd() + "\n", "", 0,
                             int((time.monotonic() - start) * 1000))
        if cmd in _BUILTIN_CAT:
            target = os.path.join(base, args[1]) if len(args) > 1 else None
            if target is None:
                return CLIResult("", "用法: cat <文件>", 1,
                                 int((time.monotonic() - start) * 1000))
            if not os.path.isfile(target):
                return CLIResult("", f"文件不存在: {target}", 1,
                                 int((time.monotonic() - start) * 1000))
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return CLIResult(content, "", 0, int((time.monotonic() - start) * 1000))
        if cmd == "echo":
            return CLIResult(" ".join(args[1:]) + "\n", "", 0,
                             int((time.monotonic() - start) * 1000))
    except OSError as e:
        return CLIResult("", str(e), 1, int((time.monotonic() - start) * 1000))
    return CLIResult("", f"不支持的内建命令: {cmd}", 2,
                     int((time.monotonic() - start) * 1000))


def run_cli_cmd(command: str, cwd: str | None = None, timeout_ms: int = 10_000) -> CLIResult:
    """执行命令，返回结构化结果；超时按 exit_code=124 处理。

    安全设计：外部命令用 argv 直接执行（shell=False），内建命令走 Python 原生实现，
    不经过任何 shell——`;`/`&`/`|`/`$()` 等字符无 shell 语义，命令注入面被消除。
    """
    start = time.monotonic()
    try:
        args = _split_command(command)
        if not args:
            return CLIResult("", "空命令", 1, int((time.monotonic() - start) * 1000))
        if args[0].lower() in _BUILTIN_DIR | _BUILTIN_CD | _BUILTIN_CAT | _BUILTIN_ECHO:
            return _run_builtin(args, cwd)
        proc = subprocess.run(
            args,
            shell=False,
            cwd=cwd,
            capture_output=True,
            timeout=timeout_ms / 1000,
        )
        out, err, code = _decode(proc.stdout), _decode(proc.stderr), proc.returncode
    except subprocess.TimeoutExpired as e:
        out = _decode(e.stdout) if e.stdout else ""
        err = _decode(e.stderr) if e.stderr else ""
        code = 124
    except (OSError, ValueError) as e:
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
