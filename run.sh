#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=/opt/homebrew/bin/python3.12
[ -d .venv ] || $PY -m venv .venv
source .venv/bin/activate
pip install -q -r backend/requirements.txt
python -m backend.fetch_master
python -m backend.extract_seed
python -m backend.seed_db
python -m backend.import_history
exec uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
