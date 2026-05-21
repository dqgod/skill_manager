"""测试 SkillSource 模型 —— 4 类来源 + 序列化 + 校验。"""

from src.models.skill_source import (
    SkillSource,
    DEVICE_LOCAL, DEVICE_REMOTE,
    SCOPE_GLOBAL, SCOPE_PROJECT,
    local_global, local_project,
    remote_global, remote_project,
)


def test_local_global_is_valid_and_labelled():
    s = local_global()
    assert s.is_local and s.is_global and s.is_valid()
    assert s.connection_name == ""
    assert s.project_id == ""
    assert s.label() == "本机 / 全局"


def test_local_project_requires_project_id():
    ok = local_project("proj-1", "我的项目")
    assert ok.is_valid()
    assert ok.is_local and ok.is_project
    assert ok.label() == "本机 / 项目: 我的项目"

    bad = SkillSource(device_kind=DEVICE_LOCAL, scope=SCOPE_PROJECT)
    assert not bad.is_valid()


def test_remote_global_requires_connection_name():
    ok = remote_global("dev-server")
    assert ok.is_valid()
    assert ok.is_remote and ok.is_global
    assert ok.label() == "远程[dev-server] / 全局"

    bad = SkillSource(device_kind=DEVICE_REMOTE, scope=SCOPE_GLOBAL)
    assert not bad.is_valid()


def test_remote_project_full_label():
    s = remote_project("dev-server", "proj-2", "服务端项目")
    assert s.is_valid()
    assert s.is_remote and s.is_project
    assert s.label() == "远程[dev-server] / 项目: 服务端项目"


def test_to_json_from_json_round_trip():
    """SkillSource 是 QSettings 持久化的载体，必须严格 round-trip。"""
    src = remote_project("dev-server", "proj-3", "回环测试")
    blob = src.to_json()
    restored = SkillSource.from_json(blob)
    assert restored == src


def test_from_json_handles_empty_and_garbage():
    """非法 JSON / 空串 都应静默回退到默认 SkillSource()。"""
    assert SkillSource.from_json("") == SkillSource()
    assert SkillSource.from_json(None) == SkillSource()
    assert SkillSource.from_json("not-json{}") == SkillSource()


def test_invalid_device_kind_or_scope_caught():
    assert not SkillSource(device_kind="unknown").is_valid()
    assert not SkillSource(scope="weird").is_valid()
