"""Seed SQLite DB from data/seed_items.json. Idempotent: skip if items already loaded."""
import json
import os
from .database import Base, engine, SessionLocal
from . import models

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seed_items.json")


def run():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(models.Item).count() > 0:
            print("Items already seeded; skipping.")
            return
        with open(SEED_PATH) as f:
            items = json.load(f)
        for it in items:
            cur = it.get("current_stock")
            if cur is None:
                cur = it.get("opening_stock") or 0
            db.add(models.Item(
                category=it["category"],
                name=it["name"],
                unit=it.get("unit") or "PCS",
                pet=it.get("pet"),
                type=it.get("type"),
                packing=it.get("packing"),
                brand=it.get("brand"),
                min_qty=float(it.get("min_qty") or 0),
                opening_stock=float(it.get("opening_stock") or 0),
                current_stock=float(cur),
                notes=it.get("min_qty_note"),
            ))
        db.commit()
        print(f"Seeded {len(items)} items.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
