"""SourceSelector —— 面板顶部的"数据源选择"控件。

对外行为：
  • 显示当前选中的 SkillSource 的 label，例如 "本机 / 全局"。
  • 点击弹出树状菜单：
      本机
        ├── 全局
        └── 项目
              ├── task-a
              ├── task-b
              └── ...
      远程[dev-server]
        ├── 全局
        └── 项目
              ├── task-a
              └── ...
      远程[192.168.x.x]
        ├── 全局
        └── 项目
              └── ...
  • 用户选完发出 source_changed(SkillSource) 信号。

设计取舍：
  - 不用 QComboBox，因为分层菜单视觉清晰、空间占用更可控。
  - 不直接挂到 QMenuBar 上，避免之前在 macOS 原生菜单栏 corner widget 那次
    踩到的 C++ 对象提前释放问题。
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QPushButton, QSizePolicy, QWidget

from src.models.skill_source import (
    SkillSource,
    local_global,
    local_project,
    remote_global,
    remote_project,
)


class SourceSelector(QPushButton):
    source_changed = Signal(object)  # emits SkillSource

    def __init__(self, source: Optional[SkillSource] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._source: SkillSource = source or local_global()
        self._connections: list = []
        self._projects: list = []
        self.setFlat(True)
        self.setCursor(self.cursor())
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet(
            "QPushButton { background: #2d2d44; border: 1px solid #3a3a55;"
            "color: #cdd6f4; padding: 4px 10px; border-radius: 4px;"
            "font-size: 11px; text-align: left; }"
            "QPushButton:hover { background: #3a3a55; }"
            "QPushButton::menu-indicator { width: 0px; }"
        )
        self.setMinimumWidth(220)
        self._refresh_label()
        self.clicked.connect(self._popup_menu)

    # ---- public API ----

    @property
    def source(self) -> SkillSource:
        return self._source

    def set_source(self, source: SkillSource, *, emit: bool = False):
        self._source = source
        self._refresh_label()
        if emit:
            self.source_changed.emit(self._source)

    def set_options(self, connections: Iterable, projects: Iterable):
        """更新可选项（连接列表、项目列表）。"""
        self._connections = list(connections)
        self._projects = list(projects)
        # 如果当前 source 已失效（比如对应连接被删除），回退到 local_global。
        if self._source.is_remote:
            names = {c.name for c in self._connections}
            if self._source.connection_name not in names:
                self.set_source(local_global(), emit=True)
                return
        if self._source.is_project:
            ids = {p.id for p in self._projects}
            if self._source.project_id not in ids:
                # 同设备退化到全局
                if self._source.is_local:
                    self.set_source(local_global(), emit=True)
                else:
                    self.set_source(
                        remote_global(self._source.connection_name), emit=True,
                    )

    # ---- internal ----

    def _refresh_label(self):
        self.setText(f"  {self._source.label()}  ▾")
        self.setToolTip(self._source.label())

    def _popup_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e2e; color: #cdd6f4; border: 1px solid #3a3a55; }"
            "QMenu::item { padding: 4px 18px; }"
            "QMenu::item:selected { background: #313244; }"
        )

        # 本机
        local_menu = menu.addMenu("本机")
        act_lg = local_menu.addAction("全局")
        act_lg.triggered.connect(lambda: self._choose(local_global()))
        if self._projects:
            local_proj_menu = local_menu.addMenu("项目")
            for p in self._projects:
                a = local_proj_menu.addAction(p.name)
                a.triggered.connect(
                    lambda _checked=False, pid=p.id, pname=p.name:
                        self._choose(local_project(pid, pname))
                )
        else:
            ph = local_menu.addAction("（暂无项目）")
            ph.setEnabled(False)

        # 远程：每个连接一个子菜单
        if self._connections:
            menu.addSeparator()
            for c in self._connections:
                conn_menu = menu.addMenu(f"远程[{c.name}]")
                act_rg = conn_menu.addAction("全局")
                act_rg.triggered.connect(
                    lambda _checked=False, cn=c.name: self._choose(remote_global(cn))
                )
                if self._projects:
                    rproj_menu = conn_menu.addMenu("项目")
                    for p in self._projects:
                        # 远程项目只对那些声明了 remote_path 的项目可选
                        if not getattr(p, "remote_path", None):
                            continue
                        a = rproj_menu.addAction(p.name)
                        a.triggered.connect(
                            lambda _checked=False, cn=c.name, pid=p.id, pname=p.name:
                                self._choose(remote_project(cn, pid, pname))
                        )
                else:
                    ph = conn_menu.addAction("（暂无项目）")
                    ph.setEnabled(False)
        else:
            menu.addSeparator()
            ph = menu.addAction("（暂无远程连接）")
            ph.setEnabled(False)

        # 在按钮正下方弹出
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _choose(self, src: SkillSource):
        if src == self._source:
            return
        self._source = src
        self._refresh_label()
        self.source_changed.emit(self._source)
