"""Extract items from the source Excel into seed_items.json.

For sheets with daily date columns, current_stock = LATEST non-empty closing-stock value
across all date blocks (not the oldest opening).

Source priority:
1. data/cache/master.xlsx (downloaded from Google Sheet by fetch_master.py)
2. SOURCE_XLSX env var
3. Local Downloads file
"""
import json
import os
from datetime import datetime
from openpyxl import load_workbook

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "cache", "master.xlsx")
LOCAL = "/Users/anishpatel/Downloads/Factory Stock Raw Material & Packing Material .xlsx"
SRC = os.environ.get("SOURCE_XLSX") or (CACHE if os.path.exists(CACHE) else LOCAL)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "seed_items.json")


def num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def s(v):
    return str(v).strip() if v is not None and str(v).strip() else None


SKIP_NAMES = {"description", "item name", "items", "sku", "label name"}


def is_real_item_name(name):
    if not name:
        return False
    return name.strip().lower() not in SKIP_NAMES


def latest_closing(row, date_cols, closing_offset):
    """Walk date columns LATEST-first; return first numeric closing value found."""
    for i, _ in reversed(date_cols):
        col = i + closing_offset
        if col < len(row) and isinstance(row[col], (int, float)):
            return float(row[col])
    return None


def latest_opening(row, date_cols, opening_offset=0):
    """Earliest opening (oldest day) for reference."""
    for i, _ in date_cols:
        col = i + opening_offset
        if col < len(row) and isinstance(row[col], (int, float)):
            return float(row[col])
    return None


def main():
    wb = load_workbook(SRC, data_only=True)
    items = []
    seen = set()  # (category, normalized_name)

    def add(category, name, **kw):
        if not is_real_item_name(name):
            return
        key = (category, name.strip().lower())
        if key in seen:
            return
        seen.add(key)
        items.append({"category": category, "name": name.strip(), **kw})

    def dates(ws):
        row = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        return [(i, v) for i, v in enumerate(row) if isinstance(v, datetime)]

    # ---------------- RM (block: Open|Recv|RecvBy|Issue|IssBy|IssTo|Close = 7) ----------------
    ws = wb["RM"]
    dc = dates(ws)
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not s(r[1]):
            continue
        opening = latest_opening(r, dc, 0)
        closing = latest_closing(r, dc, 6)
        current = closing if closing is not None else (opening or 0)
        add("raw_material", s(r[1]),
            pet=s(r[2]),
            unit=s(r[3]) or "KG",
            min_qty=num(r[4]),
            opening_stock=opening or 0,
            current_stock=current)

    # ---------------- PACKAGING ----------------
    ws = wb["PACKAGING"]
    dc = dates(ws)
    last_packing, last_type = None, None
    for r in ws.iter_rows(min_row=4, values_only=True):
        if s(r[0]):
            last_packing = s(r[0])
        if s(r[1]):
            last_type = s(r[1])
        if not s(r[2]):
            continue
        opening = latest_opening(r, dc, 0)
        closing = latest_closing(r, dc, 6)
        current = closing if closing is not None else (opening or 0)
        add("packaging", s(r[2]),
            packing=last_packing, type=last_type,
            unit=s(r[3]) or "PCS",
            min_qty=num(r[4]),
            opening_stock=opening or 0,
            current_stock=current)

    # ---------------- CONSUMABLE ----------------
    ws = wb["CONSUMABLE"]
    dc = dates(ws)
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not s(r[2]):
            continue
        opening = latest_opening(r, dc, 0)
        closing = latest_closing(r, dc, 6)
        current = closing if closing is not None else (opening or 0)
        add("consumable", s(r[2]),
            unit=s(r[3]) or "PCS",
            min_qty_note=s(r[4]),
            min_qty=num(r[4]),
            opening_stock=opening or 0,
            current_stock=current)

    # ---------------- Labels (block starts col 4, 7-col blocks) ----------------
    ws = wb["Labels"]
    dc = dates(ws)
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not s(r[1]):
            continue
        opening = latest_opening(r, dc, 0)
        closing = latest_closing(r, dc, 6)
        current = closing if closing is not None else (opening or 0)
        add("label", s(r[1]),
            unit=s(r[2]) or "PCS",
            min_qty=num(r[3]),
            opening_stock=opening or 0,
            current_stock=current)

    # ---------------- FG (single-day sheet, just opening stock) ----------------
    ws = wb["FG"]
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not s(r[1]):
            continue
        os_v = num(r[3])
        add("finished_good", s(r[1]),
            type=s(r[0]),
            unit=s(r[2]) or "Pcs",
            opening_stock=os_v,
            current_stock=os_v)

    # ---------------- Housekeeping (block: Open|Recv|Issue|IssPerson|Close = 5) ----------------
    ws = wb["Housekeeping +Stationary+Pantry"]
    dc = dates(ws)
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not s(r[3]):
            continue
        opening = latest_opening(r, dc, 0)
        closing = latest_closing(r, dc, 4)  # 5-col block, closing at offset 4
        current = closing if closing is not None else (opening or 0)
        add("housekeeping", s(r[3]),
            unit=s(r[5]) or "Pcs",
            min_qty=num(r[4]),
            opening_stock=opening or 0,
            current_stock=current)

    # ---------------- Cans Labels (per-row issue blocks of 4 cols) ----------------
    ws = wb["Cans Labels"]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not s(r[2]):
            continue
        opening_v = num(r[4])
        # Walk closing-stk columns at 10, 14, 18, ... — pick last numeric
        closing = None
        for col in (10, 14, 18, 22, 26):
            if col < len(r) and isinstance(r[col], (int, float)):
                closing = float(r[col])
        current = closing if closing is not None else opening_v
        add("can_label", s(r[2]),
            brand=s(r[1]),
            unit="Pcs",
            sheets=num(r[3]),
            opening_stock=opening_v,
            min_qty=num(r[5]),
            current_stock=current)

    # ---------------- Thread & Tags ----------------
    ws = wb["Thread & Tags"]
    for r in ws.iter_rows(min_row=5, values_only=True):
        for col in (0, 8):
            n = s(r[col]) if col < len(r) else None
            if n:
                add("thread_tag", n, unit="Pcs", opening_stock=0, current_stock=0)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(items, f, indent=2, default=str)
    print(f"Wrote {len(items)} items to {OUT}")


if __name__ == "__main__":
    main()
