# Skill Manager — 跨设备 Skill 管理

管理 AI 编码助手（Claude Code、Codex、CC-Switch）的 skill 文件，支持 Windows、Linux、macOS 平台，能在本机与远程 Linux 机器间同步，支持全局和项目级别的 skill 管理。

## 快速开始

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动应用
python -m src.main
```

## 功能

- 扫描本机和远程（SSH）机器的 skill
- 自动对比去重，SHA-256 哈希检测差异
- 推送/拉取同步，支持选择目标工具（Codex、Claude Code、CC-Switch）
- 项目级别 skill 管理（注册项目目录，独立管理项目专属 skill）
- SSH 连接管理（密钥/密码认证，加密存储）
- 同步冲突处理（覆盖/跳过/保留双方）
- 同步操作历史记录

## 技术栈

Python 3.10+ · PySide6 · Paramiko · SQLite · cryptography (AES-256-GCM)

## 项目结构

```
src/
├── main.py              # 入口
├── config.py            # 全局常量
├── models/              # 数据层（Connection/Project/SyncHistory + CRUD）
├── services/            # 业务逻辑（Scanner/Hasher/Sync/SSH/Crypto/Project）
└── ui/                  # GUI（主窗口、面板、对话框、Toast）
```

## 运行测试

```bash
pip install pytest
python -m pytest tests/ -v
```

## 打包

```bash
pip install pyinstaller
pyinstaller skill-manager.spec
# 可执行文件位于 dist/SkillManager.exe
```

## 文档

- `REQUIREMENTS.md` — 完整需求规格说明书
- `IMPLEMENTATION.md` — 实现方案与架构设计
