"""全局常量：工具名、路径模板、默认值"""

from enum import Enum
from pathlib import Path


# --------------- supported tools ---------------

class Tool(Enum):
    CODEX = "codex"
    CLAUDE = "claude"
    CC_SWITCH = "cc-switch"

    def __str__(self):
        return self.value

ALL_TOOLS = [Tool.CODEX, Tool.CLAUDE, Tool.CC_SWITCH]
ALL_TOOLS_STR = [t.value for t in ALL_TOOLS]


# --------------- global skill paths ---------------

def _global_skill_paths(tool: str) -> Path:
    """Return global skill dir for the given tool on the current OS."""
    home = Path.home()
    mapping = {
        "codex": home / ".codex" / "skills",
        "claude": home / ".claude" / "skills",
        "cc-switch": home / ".cc-switch" / "skills",
    }
    return mapping[tool]

GLOBAL_SKILL_PATHS = {t.value: _global_skill_paths(t.value) for t in ALL_TOOLS}

# project-level subdirs (relative to project root)
PROJECT_SKILL_SUBDIRS = {
    "codex": ".codex/skills",
    "claude": ".claude/skills",
    "cc-switch": ".cc-switch/skills",
}


# --------------- sync ---------------

SYNC_DIRECTION_PUSH = "push"
SYNC_DIRECTION_PULL = "pull"

SYNC_LEVEL_GLOBAL = "global_to_global"
SYNC_LEVEL_TO_PROJECT = "global_to_project"
SYNC_LEVEL_TO_GLOBAL = "project_to_global"
SYNC_LEVEL_PROJECT = "project_to_project"

SYNC_LEVELS = [
    SYNC_LEVEL_GLOBAL,
    SYNC_LEVEL_TO_PROJECT,
    SYNC_LEVEL_TO_GLOBAL,
    SYNC_LEVEL_PROJECT,
]

CONFLICT_ASK = "ask"
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_SKIP = "skip"


# --------------- storage ---------------

APP_DATA_DIR = Path.home() / ".skill-manager"
DB_FILENAME = "skill_manager.db"
BACKUP_DIR = APP_DATA_DIR / "backups"
LOG_DIR = APP_DATA_DIR / "logs"

# backup retention (days)
BACKUP_RETENTION_DAYS = 7
# SSH idle timeout (seconds)
SSH_IDLE_TIMEOUT = 300

# scan timeout (seconds)
LOCAL_SCAN_TIMEOUT = 5
REMOTE_SCAN_TIMEOUT = 15
