"""Factory Stock Dashboard API."""
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import csv
import io
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from . import models, seed_db, sheets_sync

Base.metadata.create_all(engine)

app = FastAPI(title="Factory Stock Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------
class ItemOut(BaseModel):
    id: int
    category: str
    name: str
    unit: str
    pet: Optional[str] = None
    type: Optional[str] = None
    packing: Optional[str] = None
    brand: Optional[str] = None
    min_qty: float
    opening_stock: float
    current_stock: float
    notes: Optional[str] = None
    low_stock: bool = False

    class Config:
        from_attributes = True


class ItemCreate(BaseModel):
    category: str
    name: str
    unit: str = "PCS"
    pet: Optional[str] = None
    type: Optional[str] = None
    packing: Optional[str] = None
    brand: Optional[str] = None
    min_qty: float = 0
    opening_stock: float = 0


class TxnCreate(BaseModel):
    item_id: int
    txn_type: str = Field(..., pattern="^(receive|issue|adjust)$")
    qty: float = Field(..., gt=0)
    txn_date: Optional[datetime] = None
    party: Optional[str] = None
    person: Optional[str] = None
    invoice_no: Optional[str] = None
    order_no: Optional[str] = None
    remarks: Optional[str] = None


class TxnOut(BaseModel):
    id: int
    item_id: int
    item_name: Optional[str] = None
    category: Optional[str] = None
    txn_type: str
    qty: float
    txn_date: datetime
    party: Optional[str] = None
    person: Optional[str] = None
    invoice_no: Optional[str] = None
    order_no: Optional[str] = None
    remarks: Optional[str] = None
    source: Optional[str] = "dashboard"
    bill_qty: Optional[float] = None
    short_excess: Optional[float] = None

    class Config:
        from_attributes = True


class GRNCreate(BaseModel):
    invoice_no: str
    invoice_date: Optional[datetime] = None
    vendor: str
    received_by: Optional[str] = None
    status: str = "Pending"
    remarks: Optional[str] = None


class GRNOut(GRNCreate):
    id: int

    class Config:
        from_attributes = True


# ---------- Items ----------
@app.get("/api/items", response_model=List[ItemOut])
def list_items(
    category: Optional[str] = None,
    q: Optional[str] = None,
    low_stock: bool = False,
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_db),
):
    query = db.query(models.Item)
    if category:
        query = query.filter(models.Item.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            models.Item.name.ilike(like),
            models.Item.brand.ilike(like),
            models.Item.type.ilike(like),
        ))
    if low_stock:
        query = query.filter(models.Item.current_stock < models.Item.min_qty,
                             models.Item.min_qty > 0)
    items = query.order_by(models.Item.category, models.Item.name).limit(limit).all()
    out = []
    for i in items:
        d = ItemOut.model_validate(i)
        d.low_stock = i.min_qty > 0 and i.current_stock < i.min_qty
        out.append(d)
    return out


@app.post("/api/items", response_model=ItemOut)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    item = models.Item(
        **payload.model_dump(),
        current_stock=payload.opening_stock,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    sheets_sync.append_item(item)
    return ItemOut.model_validate(item)


@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    out = ItemOut.model_validate(item)
    out.low_stock = item.min_qty > 0 and item.current_stock < item.min_qty
    return out


@app.delete("/api/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ---------- Transactions ----------
@app.post("/api/transactions", response_model=TxnOut)
def create_txn(payload: TxnCreate, db: Session = Depends(get_db)):
    item = db.get(models.Item, payload.item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    if payload.txn_type == "receive":
        item.current_stock = (item.current_stock or 0) + payload.qty
    elif payload.txn_type == "issue":
        if (item.current_stock or 0) < payload.qty:
            raise HTTPException(400, f"Insufficient stock. Available: {item.current_stock} {item.unit}")
        item.current_stock -= payload.qty
    elif payload.txn_type == "adjust":
        item.current_stock = payload.qty  # adjust = set to absolute

    txn = models.Transaction(
        item_id=item.id,
        txn_type=payload.txn_type,
        qty=payload.qty,
        txn_date=payload.txn_date or datetime.utcnow(),
        party=payload.party,
        person=payload.person,
        invoice_no=payload.invoice_no,
        order_no=payload.order_no,
        remarks=payload.remarks,
    )
    db.add(txn)

    # Auto-create vendor on receive
    if payload.txn_type == "receive" and payload.party:
        v = db.query(models.Vendor).filter_by(name=payload.party).first()
        if not v:
            db.add(models.Vendor(name=payload.party))

    db.commit()
    db.refresh(txn)
    sheets_sync.append_transaction(txn, item)
    out = TxnOut.model_validate(txn)
    out.item_name = item.name
    out.category = item.category
    return out


@app.get("/api/transactions", response_model=List[TxnOut])
def list_txns(
    item_id: Optional[int] = None,
    txn_type: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    query = db.query(models.Transaction, models.Item).join(models.Item, models.Transaction.item_id == models.Item.id)
    if item_id:
        query = query.filter(models.Transaction.item_id == item_id)
    if txn_type:
        query = query.filter(models.Transaction.txn_type == txn_type)
    if category:
        query = query.filter(models.Item.category == category)
    if source:
        query = query.filter(models.Transaction.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            models.Item.name.ilike(like),
            models.Transaction.party.ilike(like),
            models.Transaction.invoice_no.ilike(like),
        ))
    rows = query.order_by(models.Transaction.txn_date.desc()).limit(limit).all()
    out = []
    for txn, item in rows:
        d = TxnOut.model_validate(txn)
        d.item_name = item.name
        d.category = item.category
        out.append(d)
    return out


@app.get("/api/transactions/export")
def export_txns(
    period: str = Query("all", pattern="^(daily|weekly|monthly|yearly|all|custom)$"),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
    txn_type: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export filtered transactions as CSV. period applies relative to today."""
    from datetime import timedelta
    now = datetime.utcnow()
    start, end = None, None
    if period == "daily":
        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)
    elif period == "weekly":
        start = datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())
        end = start + timedelta(days=7)
    elif period == "monthly":
        start = datetime(now.year, now.month, 1)
        end = (datetime(now.year + 1, 1, 1) if now.month == 12
               else datetime(now.year, now.month + 1, 1))
    elif period == "yearly":
        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)
    elif period == "custom":
        if from_date:
            start = datetime.fromisoformat(from_date)
        if to_date:
            end = datetime.fromisoformat(to_date) + timedelta(days=1)

    q = db.query(models.Transaction, models.Item).join(models.Item, models.Transaction.item_id == models.Item.id)
    if start:
        q = q.filter(models.Transaction.txn_date >= start)
    if end:
        q = q.filter(models.Transaction.txn_date < end)
    if category:
        q = q.filter(models.Item.category == category)
    if txn_type:
        q = q.filter(models.Transaction.txn_type == txn_type)
    if source:
        q = q.filter(models.Transaction.source == source)
    rows = q.order_by(models.Transaction.txn_date.desc()).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Date", "Type", "Category", "Item", "Unit", "Qty",
        "Bill Qty", "Short/Excess", "Party (Vendor / Issued To)", "Person",
        "Invoice No", "Order No", "Source", "Remarks",
    ])
    for txn, item in rows:
        w.writerow([
            txn.txn_date.isoformat() if txn.txn_date else "",
            txn.txn_type, item.category, item.name, item.unit or "",
            txn.qty, txn.bill_qty or "", txn.short_excess or "",
            txn.party or "", txn.person or "",
            txn.invoice_no or "", txn.order_no or "",
            txn.source or "", txn.remarks or "",
        ])

    fname = f"transactions_{period}_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/short-excess", response_model=List[TxnOut])
def short_excess(limit: int = 500, db: Session = Depends(get_db)):
    """Receives where bill_qty != received qty."""
    rows = (db.query(models.Transaction, models.Item)
            .join(models.Item, models.Transaction.item_id == models.Item.id)
            .filter(models.Transaction.txn_type == "receive",
                    models.Transaction.bill_qty.is_not(None),
                    models.Transaction.bill_qty != models.Transaction.qty)
            .order_by(models.Transaction.txn_date.desc()).limit(limit).all())
    out = []
    for txn, item in rows:
        d = TxnOut.model_validate(txn)
        d.item_name = item.name
        d.category = item.category
        out.append(d)
    return out


# ---------- Summary / Dashboard ----------
@app.get("/api/summary")
def summary(db: Session = Depends(get_db)):
    total_items = db.query(func.count(models.Item.id)).scalar()
    by_cat = dict(db.query(models.Item.category, func.count(models.Item.id)).group_by(models.Item.category).all())
    low_stock = db.query(func.count(models.Item.id)).filter(
        models.Item.min_qty > 0,
        models.Item.current_stock < models.Item.min_qty,
    ).scalar()
    out_of_stock = db.query(func.count(models.Item.id)).filter(models.Item.current_stock <= 0).scalar()
    txns = db.query(func.count(models.Transaction.id)).scalar()
    txns_by_source = dict(db.query(models.Transaction.source, func.count(models.Transaction.id))
                          .group_by(models.Transaction.source).all())
    short_excess = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.bill_qty.is_not(None),
        models.Transaction.bill_qty != models.Transaction.qty,
    ).scalar()
    today = datetime.utcnow().date()
    today_receive = db.query(func.coalesce(func.sum(models.Transaction.qty), 0)).filter(
        models.Transaction.txn_type == "receive",
        func.date(models.Transaction.txn_date) == today,
    ).scalar()
    today_issue = db.query(func.coalesce(func.sum(models.Transaction.qty), 0)).filter(
        models.Transaction.txn_type == "issue",
        func.date(models.Transaction.txn_date) == today,
    ).scalar()
    return {
        "total_items": total_items,
        "by_category": by_cat,
        "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock,
        "txn_count": txns,
        "txns_by_source": txns_by_source,
        "short_excess_count": short_excess,
        "today_received_qty": today_receive,
        "today_issued_qty": today_issue,
    }


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.query(models.Item.category, func.count(models.Item.id)).group_by(models.Item.category).all()
    labels = {
        "raw_material": "Raw Material",
        "packaging": "Packaging",
        "consumable": "Consumable",
        "label": "Labels",
        "finished_good": "Finished Goods",
        "housekeeping": "Housekeeping",
        "can_label": "Cans Labels",
        "thread_tag": "Thread & Tags",
    }
    return [{"key": k, "label": labels.get(k, k.title()), "count": n} for k, n in rows]


# ---------- GRN ----------
@app.get("/api/grns", response_model=List[GRNOut])
def list_grns(db: Session = Depends(get_db)):
    return db.query(models.GRN).order_by(models.GRN.invoice_date.desc().nullslast()).limit(500).all()


@app.post("/api/grns", response_model=GRNOut)
def create_grn(payload: GRNCreate, db: Session = Depends(get_db)):
    grn = models.GRN(**payload.model_dump())
    db.add(grn)
    db.commit()
    db.refresh(grn)
    return grn


# ---------- Vendors ----------
@app.get("/api/vendors")
def list_vendors(db: Session = Depends(get_db)):
    return [v.name for v in db.query(models.Vendor).order_by(models.Vendor.name).all()]


# ---------- Sheets sync status ----------
@app.get("/api/sync/status")
def sync_status():
    return sheets_sync.status()


# ---------- Frontend (local dev only — Vercel serves /public statically) ----------
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

if not IS_SERVERLESS:
    @app.get("/")
    def root():
        for d in (PUBLIC_DIR, FRONTEND_DIR):
            p = os.path.join(d, "index.html")
            if os.path.exists(p):
                return FileResponse(p)
        return {"detail": "frontend not bundled in this deployment"}

    if os.path.isdir(FRONTEND_DIR):
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ---------- Startup ----------
@app.on_event("startup")
def on_startup():
    if IS_SERVERLESS:
        # Schema is created at migration time against Postgres; do not auto-seed in serverless
        return
    if int(os.environ.get("AUTO_SEED", "1")):
        seed_db.run()
