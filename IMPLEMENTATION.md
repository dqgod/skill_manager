# 实现方案：跨设备 Skill 管理软件

## 背景

项目当前处于规划阶段，已完成需求文档（REQUIREMENTS.md）和 UI 原型（ui-preview/index.html），无代码。

## 技术栈选型

**Python 3.10+ + PySide6**

选型理由：
- **Paramiko** 是跨生态最成熟的 SSH 库，SSH 是本项目最易出错的子系统
- **单语言**开发，避免 Go+JS/C# 的上下文切换
- **cryptography** 提供高级 AES-GCM 原语，无需手动管理 IV/填充/认证标签
- **PyInstaller** 打包为单文件 Windows exe，成熟稳定
- **PySide6 / cryptography / keyring 均为跨平台库**，一套代码同时支持 Windows + macOS + Linux
- 路径均使用 `pathlib.Path` / `Path.home()` 处理，无平台硬编码
- PyInstaller 在所有三个平台上均可打包为独立可执行文件
- Go 的仅优势是二进制体积（15-30MB vs 60-80MB），对开发者工具可接受

## 跨平台编译与分发

项目基于纯 Python + 跨平台依赖，同一套源码在三个平台上均可直接运行和编译。

### 运行环境

| 平台 | Python 版本 | 注意事项 |
| ---- | ----------- | -------- |
| **Windows** 10+ | 3.10+ | `.venv\Scripts\activate` |
| **macOS** 12+ | 3.10+ | `source .venv/bin/activate` |
| **Linux** (Ubuntu 20.04+ / Debian 11+ / Fedora 36+) | 3.10+ | 需安装 `libxcb-cursor0` 等 Qt 运行时依赖 |

### 编译为独立可执行文件

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 使用 spec 文件编译
pyinstaller skill-manager.spec

# 可执行文件位于 dist/ 目录：
#   Windows: dist/SkillManager.exe
#   macOS:   dist/SkillManager.app  (或 dist/SkillManager)
#   Linux:   dist/SkillManager
```

### 平台特定依赖

```bash
# Linux — 需要安装 Qt 系统库
sudo apt install libxcb-cursor0 libxcb-xinerama0  # Ubuntu/Debian
# sudo dnf install libxcb libxcb-cursor            # Fedora

# macOS — 通常无需额外依赖，如报错可安装
# brew install python-tk

# Windows — 无需额外系统依赖
```

### 跨平台注意事项

- **路径分隔符**：全部使用 `pathlib.Path`，自动适配 `/` vs `\`
- **HOME 目录**：使用 `Path.home()` 而非 `%USERPROFILE%` 或 `$HOME`
- **凭据存储**：`keyring` 库在 Windows 使用凭据管理器，macOS 使用 Keychain，Linux 使用 Secret Service
- **SSH 密钥**：用户可指定密钥路径，Windows 和 Linux/macOS 路径不同但均可正常工作
- **字体**：使用 `"Segoe UI", "Microsoft YaHei", sans-serif` 字体栈，各平台自动回退

依赖项（4个）：
```
PySide6>=6.5.0
paramiko>=3.0.0
cryptography>=41.0.0
keyring>=24.0.0          # Windows 凭据管理器集成
```

SQLite、pathlib、uuid、hashlib、logging 均为标准库。

---

## 项目目录结构

```
skill_manager/
├── src/
│   ├── __init__.py
│   ├── main.py                     # 入口：QApplication，初始化DB，启动MainWindow
│   ├── config.py                   # 常量：工具名、路径模板、默认值
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── db.py                   # SQLite 连接、init_db()
│   │   ├── connection.py           # Connection 数据类 + CRUD
│   │   ├── project.py              # Project 数据类 + CRUD
│   │   └── sync_history.py         # SyncRecord 数据类 + 批量插入
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── skill_scanner.py        # SkillInfo 数据类，扫描本地/远程 (F1, F2)
│   │   ├── skill_hasher.py         # SHA-256，DiffResult，对比逻辑 (F3)
│   │   ├── skill_sync.py           # 同步引擎，含回滚 (F4)
│   │   ├── ssh_manager.py          # SSH 连接池、测试、sftp (F5)
│   │   ├── crypto_service.py       # AES-256-GCM 加解密
│   │   └── project_service.py      # 项目注册、校验、自动创建目录 (F6)
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py          # 顶层窗口、菜单栏、布局骨架
│   │   ├── skill_panels.py         # 本机+远程双面板容器
│   │   ├── skill_panel.py          # 单个面板：标题栏、工具Tab、SkillList
│   │   ├── skill_list_widget.py    # QScrollArea + SkillItemRow
│   │   ├── skill_item_row.py       # 单行：复选框、图标、名称、大小/时间、标签
│   │   ├── sidebar.py              # 导航树（全局+项目）+ 徽章
│   │   ├── bottom_bar.py           # 同步方向、层级、工具复选框、同步按钮
│   │   ├── dialogs/
│   │   │   ├── __init__.py
│   │   │   ├── connection_dialog.py    # 连接CRUD列表+表单+测试
│   │   │   ├── project_dialog.py       # 项目注册表单+已注册列表
│   │   │   ├── sync_progress_dialog.py # 进度列表+进度条+取消
│   │   │   └── conflict_dialog.py      # 冲突解决选择
│   │   ├── widgets/
│   │   │   └── toast.py            # 右下角动画通知
│   │   └── theme.py                # 暗色 QSS 样式表
│   │
│   └── utils/
│       ├── path_utils.py           # Windows 路径展开、斜杠规范化
│       └── logger.py               # 结构化日志（文件+控制台）
│
├── tests/
│   ├── conftest.py                 # temp DB、temp skill 目录、mock SSH
│   ├── test_crypto_service.py
│   ├── test_skill_scanner.py
│   ├── test_skill_hasher.py
│   ├── test_skill_sync.py
│   ├── test_ssh_manager.py
│   ├── test_models.py
│   ├── test_project_service.py
│   └── fixtures/                   # 测试用 skill 目录结构
│       ├── global/.claude/skills/my-skill/
│       └── project/.claude/skills/proj-skill/
│
├── resources/icon.ico
├── data/                    # .gitignore — 运行时 DB 存放位置
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

---

## 三层架构

```
┌──────────────────────────────────────────────┐
│  UI 层 (PySide6 Widgets)                     │
│  - Widget 通过 signals 响应用户操作            │
│  - Worker (QThread) 调用 services，通过       │
│    signals 返回结果                            │
│  - 不直接 import models                      │
├──────────────────────────────────────────────┤
│  Services 层 (业务逻辑)                       │
│  - 纯 Python，无 Qt 依赖                      │
│  - 所有 I/O（文件、SSH、DB）在此层             │
│  - Services import models，不 import UI       │
├──────────────────────────────────────────────┤
│  Models 层 (数据访问)                         │
│  - 数据类定义 + sqlite3 上的薄 CRUD           │
│  - 无业务逻辑，无 Qt 依赖                     │
│  - 整个应用生命周期共享一个 sqlite3 连接       │
└──────────────────────────────────────────────┘
```

---

## SQLite 数据库 Schema

```sql
-- 连接配置（密码字段 AES-256-GCM 加密存储）
CREATE TABLE connections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    auth_type TEXT NOT NULL CHECK(auth_type IN ('key', 'password')),
    key_path TEXT,
    password_enc BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 注册的项目
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    local_path TEXT NOT NULL UNIQUE,
    remote_connection_id TEXT,
    remote_path TEXT,
    tools TEXT NOT NULL DEFAULT 'codex,claude',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (remote_connection_id) REFERENCES connections(id) ON DELETE SET NULL
);

-- 同步操作历史（仅追加）
CREATE TABLE sync_history (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    direction TEXT NOT NULL CHECK(direction IN ('push', 'pull')),
    source_device TEXT NOT NULL,
    source_level TEXT NOT NULL CHECK(source_level IN ('global', 'project')),
    source_project_id TEXT,
    source_tool TEXT NOT NULL,
    target_device TEXT NOT NULL,
    target_level TEXT NOT NULL CHECK(target_level IN ('global', 'project')),
    target_project_id TEXT,
    target_tool TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'skipped')),
    detail TEXT
);
```

> **设计决策：Skill 不持久化到 DB。** Skill 每次扫描从文件系统实时发现。持久化 Skill 需要缓存失效逻辑，增加复杂度无收益。

---

## 关键设计决策

### 1. Skill 标识 = (name, tool) 而非仅 name
同名但不同工具的 skill 是不同的 skill。对比引擎在同一视图上下文中按 `(name, tool)` 匹配 local/remote。

### 2. 目录 Skill 的哈希 = 文件哈希排序拼接后再哈希
对目录内所有文件按路径排序，逐个 sha256sum，拼接结果后再 sha256sum。跨机器确定性：
```bash
find /path -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

### 3. 同步原子性：先写临时文件再 rename
1. 写入 `<target>.tmp-<uuid>`
2. 计算临时文件哈希，校验与期望值一致
3. `os.replace()` / `sftp.rename()`（原子操作）
4. 中断时只留下 `.tmp-*` 垃圾文件，不损坏目标

### 4. 回滚：同步前备份，失败恢复
覆盖前先备份到 `BACKUP_DIR/<timestamp>/<skill-name>`。成功则删备份；失败则恢复。启动时清理超过保留期的旧备份。

### 5. SSH 连接：惰性连接 + 空闲超时
需要时才连接，按 connection_id 缓存。空闲 5 分钟后关闭。

### 6. 冲突策略：会话级默认 + 逐文件可选
默认"询问"，可切换为"全部覆盖"/"全部跳过"。询问模式下可"应用于所有后续冲突"。

### 7. 所有 I/O 操作在 QThread 中执行
UI 线程永不阻塞。扫描、SSH、哈希、同步均在 QThread worker 中运行，通过 Qt signals 返回结果。

### 8. 无 ORM，直接 sqlite3
仅 3 张表、简单 CRUD，不用 SQLAlchemy。参数化 SQL 更简单、更快调试、无黑魔法。

---

## 实现阶段

### Phase 0：脚手架
- 创建目录结构、pyproject.toml、requirements.txt
- 实现 config.py、models/db.py、utils/logger.py
- 实现 main.py（空窗口 + 暗色主题）+ ui/theme.py

### Phase 1：数据层
- 实现 models/connection.py、project.py、sync_history.py（数据类 + CRUD）
- 实现 services/crypto_service.py（AES 加解密）
- 编写 tests/test_models.py、test_crypto_service.py

### Phase 2：本地 Skill 扫描 — F1
- 实现 utils/path_utils.py（展开 %USERPROFILE%）
- 实现 SkillInfo 数据类 + SkillScanner（scan_local_global、scan_local_project）
- 实现 ui/main_window.py 完整布局、ui/sidebar.py、skill_panel.py、skill_item_row.py

### Phase 3：SSH + 远程扫描 — F2、F5
- 实现 services/ssh_manager.py（connect、test、list_dir、compute_remote_hash）
- 实现 ui/dialogs/connection_dialog.py
- 添加远程 SkillPanel（含设备选择器）
- 实现 ui/widgets/toast.py

### Phase 4：去重对比 — F3
- 实现 services/skill_hasher.py（compute_local_hash、compare、DiffResult）
- 两侧加载后自动对比、标签上色

### Phase 5：项目管理 — F6
- 实现 services/project_service.py
- 实现 ui/dialogs/project_dialog.py
- 更新 sidebar.py — 动态项目导航项

### Phase 6：同步引擎 — F4
- 实现 services/skill_sync.py（prepare_tasks、execute、backup、rollback）
- 实现 ui/bottom_bar.py
- 实现 ui/dialogs/sync_progress_dialog.py、conflict_dialog.py
- 创建 SyncWorker(QThread)

### Phase 7：历史与打磨 — UI5
- 实现历史查看对话框
- 边界情况处理（超时、权限不足、磁盘满、连接中断）
- 加载动画、按钮禁用态、首次使用引导

### Phase 8：测试与打包
- 完整测试套件
- PyInstaller 打包为单文件 exe
- 编写 README

---

## UI 组件树

```
MainWindow (QMainWindow)
├── QMenuBar [连接管理 | 项目管理 | 操作历史]
├── CentralWidget (QHBoxLayout)
│   ├── Sidebar (240px)
│   │   ├── "全局" 分区 → NavItem("全局 Skill", badge)
│   │   └── "项目" 分区 → NavItem(project_name, badge) [动态]
│   └── ContentArea (QVBoxLayout)
│       ├── SkillPanels (QHBoxLayout)
│       │   ├── SkillPanel("本机 (Windows)")
│       │   │   ├── 标题栏 + 刷新按钮
│       │   │   ├── ToolTabs [Codex | Claude | CC-Switch]
│       │   │   ├── TagLegend
│       │   │   └── SkillList → SkillItemRow[]
│       │   └── SkillPanel("远程 (Linux - {device})")
│       │       └── [同上 + 设备选择器]
│       └── BottomBar
│           ├── 同步方向 [推送 | 拉取]
│           ├── 同步层级 [全局↔全局 | 全局→项目 | 项目→全局 | 项目↔项目]
│           ├── 工具复选框 [Codex] [Claude] [CC-Switch]
│           └── [开始同步]
├── ConnectionDialog     (模态)
├── ProjectDialog        (模态)
├── SyncProgressDialog   (模态)
├── ConflictDialog       (模态)
└── Toast                (浮动)
```

---

## 关键数据流

**扫描+对比流程：**
```
点击刷新 → SkillPanel → MainWindow.on_refresh
→ ScanWorker(QThread) → SkillScanner.scan_*()
→ List[SkillInfo] → worker.finished signal
→ MainWindow 更新 panel 内部列表
→ SkillHasher.compare(local, remote) → DiffResult
→ 应用状态标签 → SkillList 重新渲染
```

**同步流程：**
```
选择 skill → 设置方向/层级/工具 → 点击"开始同步"
→ BottomBar sync_requested signal
→ SyncWorker(QThread) → SkillSyncService.execute()
→ 每个任务：备份 → 冲突检测 → 复制 → 校验 → 记录历史
→ 通过 signals 发送进度/冲突/完成
→ SyncProgressDialog 实时显示
→ 完成后刷新 skill 列表
```

---

## 验证方式

### 自动化测试
- **单元测试**：crypto、scanner、hasher、models、project_service、sync（pytest，mock SSH）
- **集成测试**：完整扫描流程、同步流程（使用临时目录）

### 手动测试（按用户故事）
| 故事 | 验证方式 |
|------|---------|
| US1 | 启动应用，刷新本机，看到真实 skill |
| US2 | 添加 SSH 连接，测试通过，扫描远程 skill |
| US3 | 本机和远程并排显示，状态标签正确 |
| US4 | 选本机 skill 推送到远程，刷新确认 |
| US5 | 同步到仅 Codex，确认其他工具未变更 |
| US6 | 注册真实项目，看到项目 skill |
| US7 | 全局 skill → 项目，确认 .claude/skills 更新 |
| US8 | 项目 skill → 远程同名项目 |
| US9 | 项目 skill → 全局 |
| US10 | 查看操作历史，记录完整 |

### 打包验证
- Windows：PyInstaller 生成 exe，在干净的 Windows 10+/11 上运行
- macOS：PyInstaller 生成 app，在 macOS 12+ 上运行
- Linux：PyInstaller 生成独立可执行文件，在 Ubuntu 20.04+/Debian 11+/Fedora 36+ 上运行
