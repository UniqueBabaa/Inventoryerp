from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from .database import Base


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    category = Column(String(40), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    unit = Column(String(40), default="PCS")
    pet = Column(String(40))
    type = Column(String(60))
    packing = Column(String(120))
    brand = Column(String(120))
    min_qty = Column(Float, default=0)
    opening_stock = Column(Float, default=0)
    current_stock = Column(Float, default=0)
    notes = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="item", cascade="all, delete-orphan")


Index("ix_items_cat_name", Item.category, Item.name)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    txn_type = Column(String(10), nullable=False)  # 'receive' | 'issue' | 'adjust'
    qty = Column(Float, nullable=False)
    txn_date = Column(DateTime, default=datetime.utcnow, index=True)
    party = Column(String(180))         # vendor (receive) or issued-to (issue)
    person = Column(String(120))        # received-by / issued-by
    invoice_no = Column(String(120))
    order_no = Column(String(120))
    remarks = Column(Text)
    bill_qty = Column(Float)            # for receives: invoiced qty (may differ from qty)
    short_excess = Column(Float)        # bill_qty - received_qty
    source = Column(String(20), default="dashboard", index=True)  # dashboard|grn|sheet26|daily_log
    dedup_key = Column(String(220), unique=True, index=True)      # for idempotent imports
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("Item", back_populates="transactions")


class GRN(Base):
    __tablename__ = "grns"
    id = Column(Integer, primary_key=True)
    invoice_no = Column(String(120), index=True)
    invoice_date = Column(DateTime)
    vendor = Column(String(180))
    received_by = Column(String(120))
    status = Column(String(40), default="Pending")
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True)
    name = Column(String(180), unique=True, nullable=False)
