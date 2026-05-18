"""应用程序入口

用法: python -m src.main  或  python src/main.py  或 双击 run.bat
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（兼容直接运行 python src/main.py）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PySide6.QtWidgets import QApplication

from src.models.db import init_db, close_db
from src.ui.theme import DARK_QSS
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Skill Manager")
    app.setOrganizationName("skill-manager")

    app.setStyleSheet(DARK_QSS)
    app.setStyle("Fusion")

    init_db()

    window = MainWindow()
    window.show()

    try:
        exit_code = app.exec()
    finally:
        close_db()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
