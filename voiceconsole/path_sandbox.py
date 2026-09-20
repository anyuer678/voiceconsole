"""路径沙箱：find_file / open_folder 默认限制在允许根目录内。"""

from __future__ import annotations

import os
from pathlib import Path


class PathSandboxError(PermissionError):
    """路径越界。"""


def default_roots() -> list[str]:
    roots = []
    home = str(Path.home())
    if home:
        roots.append(home)
    try:
        roots.append(os.getcwd())
    except OSError:
        pass
    # 去重保序
    seen = set()
    out = []
    for r in roots:
        key = os.path.normcase(os.path.realpath(r))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def resolve_allowed(path: str, roots: list[str] | None = None) -> str:
    """规范化路径并校验位于允许根目录内；成功返回 realpath。"""
    if not path:
        raise PathSandboxError("路径为空")
    allowed = roots if roots is not None else default_roots()
    if not allowed:
        # 无配置时 fail-closed：拒绝一切路径访问
        raise PathSandboxError("未配置任何允许的根目录，拒绝访问")
    raw = os.path.expanduser(path)
    # 允许相对路径：相对 CWD 解析
    if not os.path.isabs(raw):
        raw = os.path.join(os.getcwd(), raw)
    try:
        resolved = os.path.realpath(raw)
    except OSError as e:
        raise PathSandboxError(str(e)) from e
    for root in allowed:
        try:
            root_real = os.path.realpath(os.path.expanduser(root))
        except OSError:
            continue
        # 边界：resolved == root 或 resolved 在 root 之下
        if resolved == root_real:
            return resolved
        prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
        if resolved.startswith(prefix) or resolved.lower().startswith(prefix.lower()):
            # Windows 大小写不敏感场景用 lower 比较；仍以 resolved 返回
            if os.path.normcase(resolved).startswith(os.path.normcase(root_real + os.sep)) or os.path.normcase(resolved) == os.path.normcase(root_real):
                return resolved
    raise PathSandboxError(f"路径超出允许范围: {path}")
