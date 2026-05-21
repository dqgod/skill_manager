"""左右双面板容器（左/右皆为可选 source 的通用面板）。

历史上是 "本机 vs 远程"，现在两侧都可以独立选择 SkillSource，
比如：
  - 左 = 本机 全局，右 = 远程[dev-server] 全局
  - 左 = 本机 项目 A，右 = 本机 全局
  - 左 = 远程[A] 项目 X，右 = 远程[B] 项目 Y
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame

from src.models.skill_source import SkillSource, local_global
from src.ui.skill_panel import SkillPanel


class SkillPanels(QWidget):
    def __init__(self, left_source: SkillSource | None = None,
                 right_source: SkillSource | None = None,
                 parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background: #3a3a55; max-width: 1px;")

        self.left_panel = SkillPanel(
            "📦 来源 A", source=left_source or local_global(),
        )
        self.right_panel = SkillPanel(
            "📦 来源 B", source=right_source or local_global(),
        )

        layout.addWidget(self.left_panel, stretch=1)
        layout.addWidget(sep)
        layout.addWidget(self.right_panel, stretch=1)

    # ---- 兼容旧接口（早期测试与外部代码可能仍引用 local/remote_panel） ----

    @property
    def local_panel(self) -> SkillPanel:
        return self.left_panel

    @property
    def remote_panel(self) -> SkillPanel:
        return self.right_panel
