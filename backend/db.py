import os
from pathlib import Path
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

ROOT = Path(__file__).resolve().parents[1]
metadata = MetaData()
orders = Table('demo_orders', metadata,
    Column('order_id', String(64), primary_key=True),
    Column('customer_id', String(64), nullable=False),
    Column('purchased_at', String(10), nullable=False),
    Column('status', String(20), nullable=False))
items = Table('demo_items', metadata,
    Column('order_id', String(64), ForeignKey('demo_orders.order_id'), primary_key=True),
    Column('item_id', Integer, primary_key=True),
    Column('price_cents', Integer, nullable=False))

def make_engine(url=None):
    (ROOT / 'data').mkdir(exist_ok=True)
    return create_engine(url or os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "data" / "demo.db"}'), pool_pre_ping=True)
