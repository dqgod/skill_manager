"""路径工具"""

import os
from pathlib import Path


def expand_path(path: str) -> Path:
    """展开 ~ 和环境变量，返回规范化绝对路径。"""
    expanded = os.path.expandvars(os.path.expanduser(path))
    return Path(expanded).resolve()
