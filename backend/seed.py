"""Import only the explicitly synthetic demo tables. Never touches future Olist tables."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import pandas as pd
from sqlalchemy import delete
from .db import ROOT, items, make_engine, metadata, orders

def read_sample(directory):
    source=Path(directory)
    o=pd.read_csv(source/'orders.csv',dtype=str)
    i=pd.read_csv(source/'items.csv',dtype=str)
    for frame,keys in [(o,['order_id']),(i,['order_id','item_id'])]:
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError('缺失或重复主键')
    if o.isna().any().any() or i.isna().any().any():
        raise ValueError('示例数据缺失必填字段')
    for value in o.purchased_at:date.fromisoformat(value)
    if not o.status.isin(['delivered','canceled','processing']).all():
        raise ValueError('不支持的订单状态')
    if not i.order_id.isin(o.order_id).all():raise ValueError('明细引用了不存在的订单')
    if not o.loc[o.status.eq('delivered'),'order_id'].isin(i.order_id).all():
        raise ValueError('已交付订单缺少商品明细')
    cents=[]
    for value in i.price:
        value=Decimal(value)*100
        if not value.is_finite() or value<0 or value!=value.to_integral_value():
            raise ValueError('商品价格必须为非负数且最多两位小数')
        cents.append(int(value))
    i['price_cents']=cents
    if not i.item_id.str.fullmatch(r'[1-9][0-9]*').all():raise ValueError('item_id 必须为正整数')
    i['item_id']=i.item_id.astype(int)
    # Conversion can reveal duplicate identities such as 01 vs 1; leading zero IDs are rejected above.
    if i.duplicated(['order_id','item_id']).any():raise ValueError('重复明细主键')
    return o.to_dict('records'),i[['order_id','item_id','price_cents']].to_dict('records')

def seed(db=None,directory=None):
    order_rows,item_rows=read_sample(directory or ROOT/'sample_data')
    db=db or make_engine()
    metadata.create_all(db)
    with db.begin() as conn:
        conn.execute(delete(items));conn.execute(delete(orders))
        conn.execute(orders.insert(),order_rows);conn.execute(items.insert(),item_rows)
    return {'orders':len(order_rows),'items':len(item_rows),'source':'synthetic'}

if __name__=='__main__':print(seed())
