"""Google Sheets sync — append every dashboard transaction back to the master sheet.

Design:
- Master sheet contains the user's existing tabs (RM, PACKAGING, etc.) with a complex
  daily-column structure. We do NOT mutate those tabs.
- We add two new tabs that the dashboard owns:
  - `App_Transactions` — every receive/issue/adjust the dashboard generates.
  - `App_Items` — append-only log of items added via dashboard.
- Read of existing items uses public CSV/XLSX export (no auth needed).
- Writes require a service-account JSON at GOOGLE_CREDENTIALS_PATH (default:
  data/credentials.json) and the sheet shared with that service account's email.
- All writes are best-effort: if creds missing or API fails, we log and continue;
  local SQLite remains the source of truth for the API.
"""
from __future__ import annotations
import logging
import os
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger("sheets_sync")

SHEET_ID = os.environ.get("SHEET_ID", "1Ij99dOXXkf0srM8_ceY_Tx2SmGA2V-Ku")
CRED_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "credentials.json"),
)

TXN_TAB = "App_Transactions"
ITEMS_TAB = "App_Items"

TXN_HEADERS = [
    "Timestamp", "Date", "Type", "Category", "Item", "Unit", "Qty",
    "Party (Vendor / Issued To)", "Person", "Invoice No", "Order No", "Remarks",
]
ITEM_HEADERS = [
    "Timestamp", "Category", "Item", "Unit", "Min Qty", "Opening Stock",
    "Pet", "Type", "Packing", "Brand", "Notes",
]

_lock = threading.Lock()
_client = None
_spreadsheet = None
_enabled: Optional[bool] = None


def enabled() -> bool:
    """True if write-back to sheet is configured."""
    global _enabled
    if _enabled is not None:
        return _enabled
    if not os.path.exists(CRED_PATH):
        log.info("Sheets write-back disabled: credentials not found at %s", CRED_PATH)
        _enabled = False
        return False
    try:
        _connect()
        _enabled = True
        return True
    except Exception as e:
        log.warning("Sheets write-back disabled: %s", e)
        _enabled = False
        return False


def _connect():
    global _client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CRED_PATH, scopes=scopes)
    _client = gspread.authorize(creds)
    _spreadsheet = _client.open_by_key(SHEET_ID)
    _ensure_tabs(_spreadsheet)
    return _spreadsheet


def _ensure_tabs(ss):
    existing = {ws.title for ws in ss.worksheets()}
    if TXN_TAB not in existing:
        ws = ss.add_worksheet(TXN_TAB, rows=1, cols=len(TXN_HEADERS))
        ws.append_row(TXN_HEADERS, value_input_option="USER_ENTERED")
        log.info("Created sheet tab %s", TXN_TAB)
    if ITEMS_TAB not in existing:
        ws = ss.add_worksheet(ITEMS_TAB, rows=1, cols=len(ITEM_HEADERS))
        ws.append_row(ITEM_HEADERS, value_input_option="USER_ENTERED")
        log.info("Created sheet tab %s", ITEMS_TAB)


def _append(tab: str, row: list):
    if not enabled():
        return False
    try:
        with _lock:
            ss = _connect()
            ws = ss.worksheet(tab)
            ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        log.error("append_row to %s failed: %s", tab, e)
        return False


def append_transaction(txn, item) -> bool:
    """Append a transaction row. txn = SQLAlchemy Transaction; item = Item."""
    row = [
        datetime.utcnow().isoformat(timespec="seconds"),
        txn.txn_date.isoformat(timespec="seconds") if txn.txn_date else "",
        txn.txn_type,
        item.category,
        item.name,
        item.unit or "",
        txn.qty,
        txn.party or "",
        txn.person or "",
        txn.invoice_no or "",
        txn.order_no or "",
        txn.remarks or "",
    ]
    return _append(TXN_TAB, row)


def append_item(item) -> bool:
    row = [
        datetime.utcnow().isoformat(timespec="seconds"),
        item.category,
        item.name,
        item.unit or "",
        item.min_qty or 0,
        item.opening_stock or 0,
        item.pet or "",
        item.type or "",
        item.packing or "",
        item.brand or "",
        item.notes or "",
    ]
    return _append(ITEMS_TAB, row)


def status() -> dict:
    return {
        "enabled": enabled(),
        "sheet_id": SHEET_ID,
        "credentials_path": CRED_PATH,
        "credentials_present": os.path.exists(CRED_PATH),
        "tabs": [TXN_TAB, ITEMS_TAB],
    }
