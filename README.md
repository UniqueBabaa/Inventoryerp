# Factory Stock Dashboard

User-facing dashboard for managing raw material, packaging, consumables, labels, finished goods, housekeeping & GRN transactions for the factory.

**Master backend = Google Sheet:** [Factory Stock Master](https://docs.google.com/spreadsheets/d/1Ij99dOXXkf0srM8_ceY_Tx2SmGA2V-Ku/edit)

- The dashboard reads existing items from the sheet on startup (downloaded as XLSX, no auth needed).
- Every transaction created via the dashboard is appended back to the sheet in the `App_Transactions` tab.
- Every new item added via the dashboard is appended to the `App_Items` tab.
- Existing daily-column tabs (RM, PACKAGING, etc.) are **never** mutated by the app.

## Stack

- Backend: FastAPI + SQLAlchemy
- DB: SQLite locally, Postgres in production (Neon / Vercel Postgres / Supabase)
- Sync: gspread + service-account auth (write-back to Google Sheet)
- Frontend: single HTML page (Tailwind CDN + Alpine.js)
- Deployable: serverless (Vercel) or container (Fly / Render)

## Deploy on Vercel + Neon Postgres

Prerequisites: a Neon (or Vercel Postgres / Supabase) connection string, Vercel CLI.

```bash
# 1. Provision Postgres (free): https://neon.tech → create project → copy DATABASE_URL
export DATABASE_URL='postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require'

# 2. Migrate (creates schema, seeds 1,866 items, imports 5,174 historical txns)
python migrate.py

# 3. Deploy to Vercel
npm i -g vercel
vercel login
vercel --prod
# When prompted for env vars, add DATABASE_URL (same as above)
# Optional: GOOGLE_CREDENTIALS_JSON (paste your service-account JSON as one line)
```

After deploy, Vercel returns a URL like `https://inventoryerp.vercel.app`.

## Run

```bash
bash run.sh
```

Then open <http://localhost:8765>.

`run.sh` will:
1. Create the venv (Python 3.12).
2. Install deps.
3. Download the latest master sheet (XLSX) into `data/cache/master.xlsx`.
4. Re-extract `data/seed_items.json`.
5. Seed the DB if empty.
6. Start the server.

## Enable write-back to the Google Sheet

Read works without auth. To make the dashboard **write** transactions back to the sheet you need a Google service account.

1. Go to <https://console.cloud.google.com/>, create or pick a project.
2. APIs & Services → enable **Google Sheets API** and **Google Drive API**.
3. IAM & Admin → Service Accounts → Create service account → Done.
4. On the new service account → Keys → Add Key → JSON → download.
5. Save the file as `data/credentials.json` in this project.
6. Open the master sheet → Share → paste the service-account email (looks like `something@your-project.iam.gserviceaccount.com`) → role **Editor** → Send.
7. Restart the server (`bash run.sh`).

The dashboard banner at the top shows current sync status (ON / OFF).

When ON, two new tabs appear in the sheet:

- `App_Transactions` — `Timestamp | Date | Type | Category | Item | Unit | Qty | Party | Person | Invoice No | Order No | Remarks`
- `App_Items` — log of any new SKUs added via the dashboard.

## Categories (auto-seeded from sheet)

| Key | Sheet | Items |
| --- | --- | --- |
| `raw_material` | RM | 131 |
| `packaging` | PACKAGING | 318 |
| `consumable` | CONSUMABLE | 104 |
| `label` | Labels | 185 |
| `finished_good` | FG | 52 |
| `housekeeping` | Housekeeping +Stationary+Pantry | 72 |
| `can_label` | Cans Labels | 71 |
| `thread_tag` | Thread & Tags | 31 |

## Features

- Inventory list with category filter, search, low-stock toggle
- Receive / Issue / Adjust transactions (auto-updates current stock; blocks issue when stock < qty)
- Vendor autocomplete (auto-captured from receive entries)
- Today's received / issued totals on dashboard
- Low-stock alerts (current < min)
- GRN log
- Add new item

## Endpoints

- `GET  /api/summary` — counts + today totals
- `GET  /api/categories` — categories with counts
- `GET  /api/items?category=&q=&low_stock=` — list items
- `POST /api/items` — create item *(also appends to App_Items in sheet)*
- `GET  /api/transactions?item_id=&txn_type=&category=` — log
- `POST /api/transactions` — receive/issue/adjust *(also appends to App_Transactions in sheet)*
- `GET  /api/grns` / `POST /api/grns` — GRN log
- `GET  /api/vendors` — vendor names
- `GET  /api/sync/status` — sheet sync status (enabled, sheet_id, credentials_present)

## Files

```
backend/
  main.py          FastAPI app + endpoints
  models.py        SQLAlchemy models
  database.py      Engine + session
  seed_db.py       Seed DB from data/seed_items.json
  fetch_master.py  Download sheet → data/cache/master.xlsx
  extract_seed.py  Parse XLSX → data/seed_items.json
  sheets_sync.py   Google Sheets write-back layer
  requirements.txt
frontend/
  index.html       Dashboard SPA
data/
  cache/master.xlsx  Master sheet snapshot
  seed_items.json    Items extracted from sheet
  factory.db         SQLite (created at runtime)
  credentials.json   Service-account JSON (you provide; gitignored)
run.sh
```

## Env vars

- `SHEET_ID` — override Google Sheet ID (default = master sheet above).
- `GOOGLE_CREDENTIALS_PATH` — override credentials path (default `data/credentials.json`).
- `SOURCE_XLSX` — override seed source XLSX file.
- `AUTO_SEED` — `0` to skip auto-seed on startup (default `1`).
