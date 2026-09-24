from pathlib import Path
from sqlalchemy import text

SQL=(Path(__file__).resolve().parents[1]/'sql'/'overview.sql').read_text(encoding='utf-8')

def overview(db):
    with db.connect() as conn:
        row=conn.execute(text(SQL)).mappings().one()
    count=int(row['order_count'])
    return {'data_source':'synthetic','currency':'BRL','order_count':count,
        'revenue_cents':int(row['revenue_cents']),
        'average_order_value_cents':float(row['revenue_cents'])/count if count else None,
        'definition':'仅已交付订单；商品金额不含运费；金额单位为分。'}
