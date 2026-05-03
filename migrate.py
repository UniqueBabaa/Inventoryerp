"""One-shot migration: download master sheet → seed items → import history.

Run locally with DATABASE_URL pointing at production Postgres (Neon, etc.):

    export DATABASE_URL='postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require'
    python migrate.py

Idempotent: re-runs are safe (seed_db skips if items exist; import_history is dedup'd).
"""
import os
import sys

# Make local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("="*60)
print("DB target:", os.environ.get("DATABASE_URL", "<sqlite local>")[:60], "...")
print("="*60)

from backend import fetch_master, extract_seed, seed_db, import_history
from backend.database import Base, engine

print("\n[1/4] Downloading master sheet...")
fetch_master.main()

print("\n[2/4] Extracting items from sheet...")
extract_seed.main()

print("\n[3/4] Creating schema + seeding items into DB...")
Base.metadata.create_all(engine)
seed_db.run()

print("\n[4/4] Importing historical transactions...")
import_history.run()

print("\nDone. DB ready for production.")
