"""本机+远程双面板容器"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame

from src.ui.skill_panel import SkillPanel


class SkillPanels(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        # separator line between panels
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background: #3a3a55; max-width: 1px;")

        self.local_panel = SkillPanel("🖥 本机 (Windows)")
        self.remote_panel = SkillPanel("🌐 远程 (Linux)", show_device_selector=True)

        layout.addWidget(self.local_panel, stretch=1)
        layout.addWidget(sep)
        layout.addWidget(self.remote_panel, stretch=1)
