"""Download the master Google Sheet as XLSX (public export, no auth required)."""
import os
import sys
import requests

SHEET_ID = os.environ.get("SHEET_ID", "1Ij99dOXXkf0srM8_ceY_Tx2SmGA2V-Ku")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "cache", "master.xlsx")


def main():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    r = requests.get(url, allow_redirects=True, timeout=60)
    r.raise_for_status()
    with open(OUT, "wb") as f:
        f.write(r.content)
    print(f"Wrote {len(r.content)} bytes to {OUT}")


if __name__ == "__main__":
    main()
