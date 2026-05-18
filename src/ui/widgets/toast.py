"""右下角浮动通知"""

from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout
from PySide6.QtCore import QTimer, Qt


class Toast(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        self._label.setStyleSheet(
            "background: #2d2d44; color: #cdd6f4; border: 1px solid #3a3a55;"
            "border-radius: 6px; padding: 10px 16px; font-size: 12px;"
        )
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, duration: int = 2000,
                      success: bool = True):
        border = "#a6e3a1" if success else "#f38ba8"
        self._label.setStyleSheet(
            f"background: #2d2d44; color: #cdd6f4; border: 1px solid {border};"
            "border-radius: 6px; padding: 10px 16px; font-size: 12px;"
        )
        self._label.setText(text)
        self.adjustSize()

        # position relative to parent
        if self.parent():
            pw = self.parent()
            x = pw.width() - self.width() - 20
            y = pw.height() - self.height() - 20
            pos = pw.mapToGlobal(pw.rect().topLeft())
            self.move(pos.x() + x, pos.y() + y)

        self.show()
        self._timer.start(duration)
