"""文件系统工具：跨平台在文件管理器中显示路径。

Used by the right-click menu in skill list rows.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


def reveal_in_file_manager(path: str | Path) -> bool:
    """Open the OS file manager focused on `path`.

    - macOS: `open -R <path>` highlights the entry in Finder.
    - Windows: `explorer /select,<path>` highlights the entry in Explorer.
    - Linux: `xdg-open <dir>` opens the containing directory.

    Returns True on best-effort success, False on any failure.
    """
    p = Path(path)
    if not p.exists():
        # Fall back to its parent if the entry itself was removed.
        if p.parent.exists():
            p = p.parent
        else:
            logger.warning("reveal_in_file_manager: path does not exist: %s", path)
            return False

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
            return True
        if os.name == "nt":
            # /select highlights, but only for files; for dirs, just open it.
            if p.is_dir():
                subprocess.Popen(["explorer", str(p)])
            else:
                subprocess.Popen(["explorer", f"/select,{p}"])
            return True
        # Linux / others
        target = p if p.is_dir() else p.parent
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener:
            subprocess.Popen([opener, str(target)])
            return True
        logger.warning("No xdg-open/gio available; cannot reveal %s", target)
        return False
    except Exception as e:
        logger.warning("reveal_in_file_manager failed for %s: %s", path, e)
        return False
