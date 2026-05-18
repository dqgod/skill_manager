"""暗色主题 QSS 样式表"""

DARK_QSS = """
/* Global */
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

/* Menu Bar */
QMenuBar {
    background-color: #252536;
    border-bottom: 1px solid #3a3a55;
    padding: 0;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    color: #a6adc8;
    font-size: 12px;
}
QMenuBar::item:selected {
    background-color: #2d2d44;
    color: #cdd6f4;
}
QMenu {
    background-color: #252536;
    border: 1px solid #3a3a55;
    padding: 4px;
}
QMenu::item {
    padding: 4px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2d2d44;
}

/* Buttons */
QPushButton {
    background-color: #2d2d44;
    border: 1px solid #3a3a55;
    border-radius: 4px;
    padding: 6px 14px;
    color: #cdd6f4;
}
QPushButton:hover {
    background-color: #3a3a55;
}
QPushButton:pressed {
    background-color: #1e1e2e;
}
QPushButton[cssClass="primary"] {
    background-color: #74c7ec;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}
QPushButton[cssClass="primary"]:hover {
    background-color: #89d4f5;
}
QPushButton[cssClass="danger"] {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}
QPushButton[cssClass="danger"]:hover {
    background-color: #f5a0b8;
}
QPushButton[cssClass="tool-tab"] {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 6px 12px;
    color: #6c7086;
    font-size: 12px;
}
QPushButton[cssClass="tool-tab"]:hover {
    color: #a6adc8;
    background: transparent;
}
QPushButton[cssClass="tool-tab"][active="true"] {
    color: #89b4fa;
    border-bottom-color: #89b4fa;
}
QPushButton[cssClass="nav-item"] {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 6px 12px;
    text-align: left;
    color: #a6adc8;
    font-size: 12px;
}
QPushButton[cssClass="nav-item"]:hover {
    background-color: #2d2d44;
    color: #cdd6f4;
}
QPushButton[cssClass="nav-item"][active="true"] {
    background-color: #2d2d44;
    color: #89b4fa;
    border-left-color: #89b4fa;
}
QPushButton[cssClass="sync-dir"] {
    background-color: #2d2d44;
    border: 1px solid #3a3a55;
    padding: 6px 14px;
}
QPushButton[cssClass="sync-dir"][active="true"] {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
}
QPushButton[cssClass="sync-level"] {
    background-color: #2d2d44;
    border: 1px solid #3a3a55;
    padding: 6px 10px;
    font-size: 11px;
    border-radius: 4px;
}
QPushButton[cssClass="sync-level"][active="true"] {
    background-color: #cba6f7;
    color: #1e1e2e;
    border-color: #cba6f7;
}

/* Labels */
QLabel[cssClass="section-title"] {
    color: #6c7086;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 8px 12px 4px;
}
QLabel[cssClass="panel-title"] {
    font-weight: 600;
    font-size: 12px;
    color: #cdd6f4;
}
QLabel[cssClass="skill-name"] {
    font-size: 12px;
    font-weight: 500;
    color: #cdd6f4;
}
QLabel[cssClass="skill-meta"] {
    font-size: 10px;
    color: #6c7086;
}
QLabel[cssClass="badge"] {
    font-size: 10px;
    color: #6c7086;
    background-color: #2d2d44;
    padding: 1px 6px;
    border-radius: 10px;
}
QLabel[cssClass="sync-tag"] {
    font-size: 9px;
    padding: 0px 5px;
    border-radius: 3px;
    background-color: #2d2d44;
}

/* Inputs */
QLineEdit, QComboBox {
    background-color: #2d2d44;
    border: 1px solid #3a3a55;
    border-radius: 4px;
    padding: 6px 10px;
    color: #cdd6f4;
    font-size: 12px;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
}
QComboBox::down-arrow {
    image: none;
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #252536;
    border: 1px solid #3a3a55;
    selection-background-color: #2d2d44;
    color: #cdd6f4;
}

/* Checkboxes */
QCheckBox {
    color: #a6adc8;
    font-size: 11px;
    spacing: 4px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1.5px solid #3a3a55;
    border-radius: 3px;
    background-color: #1e1e2e;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

/* Scroll Area */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #1e1e2e;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #3a3a55;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4a65;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Progress Bar */
QProgressBar {
    background-color: #2d2d44;
    border: none;
    border-radius: 10px;
    height: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #74c7ec;
    border-radius: 10px;
}

/* Separators */
QFrame[cssClass="divider"] {
    background-color: #3a3a55;
}

/* Dialog */
QDialog {
    background-color: #252536;
    border: 1px solid #3a3a55;
    border-radius: 8px;
}

/* Tooltips */
QToolTip {
    background-color: #252536;
    border: 1px solid #3a3a55;
    color: #cdd6f4;
    padding: 4px;
    border-radius: 4px;
}
"""
