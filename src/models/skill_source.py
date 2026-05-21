"""SkillSource —— 描述「一侧面板从哪儿读 skill」的统一抽象。

旧模型：左面板恒为本机、右面板恒为远程；视图维度通过 sidebar 的
view_id="global" / <project_id> 间接表达。

新模型：每一侧都是一个独立的 SkillSource，可以是
  (本机 / 全局)、(本机 / 项目 X)、(远程 dev-server / 全局)、
  (远程 192.168.x.x / 项目 Y) ……

这样比对、同步的两端都按同一接口工作，4×4 组合（左/右各 4 类）变得自然。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional


DEVICE_LOCAL = "local"
DEVICE_REMOTE = "remote"

SCOPE_GLOBAL = "global"
SCOPE_PROJECT = "project"


@dataclass(frozen=True)
class SkillSource:
    """描述一侧面板的数据来源。

    字段约定：
      - device_kind == "local"  时 connection_name 必为 ""
      - device_kind == "remote" 时 connection_name 必须给出已存在的连接名
      - scope == "global"       时 project_id / project_name 必为 ""
      - scope == "project"      时 project_id 必给，project_name 仅做展示
    """

    device_kind: str = DEVICE_LOCAL          # "local" | "remote"
    connection_name: str = ""                # remote 才有意义
    scope: str = SCOPE_GLOBAL                # "global" | "project"
    project_id: str = ""                     # scope=project 时给
    project_name: str = ""                   # 展示文案

    # ---- 合法性 ----

    def is_valid(self) -> bool:
        if self.device_kind not in (DEVICE_LOCAL, DEVICE_REMOTE):
            return False
        if self.scope not in (SCOPE_GLOBAL, SCOPE_PROJECT):
            return False
        if self.device_kind == DEVICE_REMOTE and not self.connection_name:
            return False
        if self.scope == SCOPE_PROJECT and not self.project_id:
            return False
        return True

    # ---- 派生属性 ----

    @property
    def is_local(self) -> bool:
        return self.device_kind == DEVICE_LOCAL

    @property
    def is_remote(self) -> bool:
        return self.device_kind == DEVICE_REMOTE

    @property
    def is_global(self) -> bool:
        return self.scope == SCOPE_GLOBAL

    @property
    def is_project(self) -> bool:
        return self.scope == SCOPE_PROJECT

    # ---- 展示 ----

    def label(self) -> str:
        """生成下拉按钮文案，例如 '本机 / 全局' 或 '远程[dev-server] / 项目: foo'."""
        if self.is_local:
            head = "本机"
        else:
            head = f"远程[{self.connection_name or '?'}]"

        if self.is_global:
            tail = "全局"
        else:
            tail = f"项目: {self.project_name or self.project_id or '?'}"

        return f"{head} / {tail}"

    # ---- 序列化（QSettings 持久化用） ----

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: Optional[str]) -> "SkillSource":
        if not s:
            return cls()
        try:
            data = json.loads(s)
        except (TypeError, ValueError):
            return cls()
        return cls(
            device_kind=data.get("device_kind", DEVICE_LOCAL),
            connection_name=data.get("connection_name", ""),
            scope=data.get("scope", SCOPE_GLOBAL),
            project_id=data.get("project_id", ""),
            project_name=data.get("project_name", ""),
        )


# ---- 常用工厂 ----

def local_global() -> SkillSource:
    return SkillSource(device_kind=DEVICE_LOCAL, scope=SCOPE_GLOBAL)


def local_project(project_id: str, project_name: str = "") -> SkillSource:
    return SkillSource(
        device_kind=DEVICE_LOCAL,
        scope=SCOPE_PROJECT,
        project_id=project_id,
        project_name=project_name,
    )


def remote_global(connection_name: str) -> SkillSource:
    return SkillSource(
        device_kind=DEVICE_REMOTE,
        connection_name=connection_name,
        scope=SCOPE_GLOBAL,
    )


def remote_project(connection_name: str, project_id: str,
                   project_name: str = "") -> SkillSource:
    return SkillSource(
        device_kind=DEVICE_REMOTE,
        connection_name=connection_name,
        scope=SCOPE_PROJECT,
        project_id=project_id,
        project_name=project_name,
    )
