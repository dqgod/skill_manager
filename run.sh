#!/usr/bin/env bash
# Launch Skill Manager: clean previous logs, then start the app.
set -e

cd "$(dirname "$0")"

# ---- 1. Clean previous run logs (~/.skill-manager/logs) ------------------
LOG_DIR="${HOME}/.skill-manager/logs"
if [ -d "${LOG_DIR}" ]; then
    echo "[run.sh] Cleaning previous logs in ${LOG_DIR}"
    rm -f "${LOG_DIR}"/*.log "${LOG_DIR}"/*.log.* 2>/dev/null || true
else
    mkdir -p "${LOG_DIR}"
fi

# ---- 2. Pick a Python interpreter ---------------------------------------
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    PY="python"
fi
echo "[run.sh] Using interpreter: ${PY}"

# ---- 3. Launch -----------------------------------------------------------
exec "${PY}" -m src.main "$@"
