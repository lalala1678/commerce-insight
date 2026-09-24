"""Olist serving tables. Separate metadata keeps the synthetic demo untouched."""
from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, MetaData, String, Table, Text

warehouse_metadata = MetaData()
OPTIONS = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}

dim_customer = Table('dim_customer', warehouse_metadata,
    Column('customer_id', String(64), primary_key=True),
    Column('customer_unique_id', String(64), nullable=False),
    Column('state', String(8), nullable=False), **OPTIONS)

dim_product = Table('dim_product', warehouse_metadata,
    Column('product_id', String(64), primary_key=True),
    Column('category', String(128), nullable=False),
    Column('category_english', String(128)), **OPTIONS)

dim_seller = Table('dim_seller', warehouse_metadata,
    Column('seller_id', String(64), primary_key=True),
    Column('state', String(8), nullable=False), **OPTIONS)

fact_order = Table('fact_order', warehouse_metadata,
    Column('order_id', String(64), primary_key=True),
    Column('customer_id', String(64), ForeignKey('dim_customer.customer_id'), nullable=False),
    Column('purchase_at', String(19), nullable=False),
    Column('purchase_date', String(10), nullable=False),
    Column('status', String(20), nullable=False),
    Column('carrier_at', String(19)),
    Column('delivered_at', String(19)),
    Column('estimated_at', String(19)),
    Column('revenue_cents', BigInteger, nullable=False, server_default='0'),
    Column('freight_cents', BigInteger, nullable=False, server_default='0'),
    Column('item_count', Integer, nullable=False),
    Column('payment_cents', BigInteger),
    Column('payment_count', Integer, nullable=False),
    Column('review_score', Integer),
    Column('review_count', Integer, nullable=False),
    Column('delivery_seconds', Integer),
    Column('is_late', Integer),
    Column('quality_flags', Text, nullable=False), **OPTIONS)

fact_item = Table('fact_item', warehouse_metadata,
    Column('order_id', String(64), ForeignKey('fact_order.order_id'), primary_key=True),
    Column('item_id', Integer, primary_key=True),
    Column('product_id', String(64), ForeignKey('dim_product.product_id'), nullable=False),
    Column('seller_id', String(64), ForeignKey('dim_seller.seller_id'), nullable=False),
    Column('price_cents', BigInteger, nullable=False),
    Column('freight_cents', BigInteger, nullable=False), **OPTIONS)

agg_day = Table('agg_day', warehouse_metadata,
    Column('day', String(10), primary_key=True),
    Column('revenue_cents', BigInteger, nullable=False),
    Column('order_count', Integer, nullable=False),
    Column('item_count', Integer, nullable=False), **OPTIONS)

etl_run = Table('etl_run', warehouse_metadata,
    Column('id', Integer, primary_key=True, autoincrement=False),
    Column('payload', Text, nullable=False), **OPTIONS)

Index('ix_fact_order_status_date', fact_order.c.status, fact_order.c.purchase_date)
Index('ix_fact_order_customer', fact_order.c.customer_id)
Index('ix_fact_item_product', fact_item.c.product_id)
Index('ix_dim_customer_unique', dim_customer.c.customer_unique_id)
Index('ix_dim_customer_state', dim_customer.c.state)
Index('ix_dim_product_category', dim_product.c.category)
