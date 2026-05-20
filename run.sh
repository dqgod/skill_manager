#!/bin/bash
cd "$(dirname "$0")"

# if [ ! -f ".venv/bin/python" ]; then
#     echo "[ERROR] 虚拟环境不存在，请先运行: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
#     exit 1
# fi

python -m src.main
