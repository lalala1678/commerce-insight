"""Verify raw CSV -> SQL warehouse -> HTTP API with independent raw arithmetic.

Run against a stable imported warehouse: python -m scripts.verify_pipeline
DATABASE_URL selects the SQL store; --api-url selects the matching running API.
No raw identifiers, credentials or review text enter the acceptance artifact.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import time

import requests
from sqlalchemy import text
from backend.db import ROOT, make_engine


def records(filename):
    with (ROOT/'data/raw'/filename).open(encoding='utf-8-sig',newline='') as file:
        return list(csv.DictReader(file))


def raw_expectations():
    orders={r['order_id']:r for r in records('olist_orders_dataset.csv')}
    customers={r['customer_id']:r for r in records('olist_customers_dataset.csv')}
    categories={r['product_id']:r['product_category_name'].strip() or 'unknown' for r in records('olist_products_dataset.csv')}
    items=records('olist_order_items_dataset.csv')
    for r in items:r['cents']=int(Decimal(r['price'])*100)

    def calculate(filters):
        selected={}; cents=0;units=0
        for item in items:
            order=orders[item['order_id']]
            if order['order_status']!='delivered':continue
            if not filters['start']<=order['order_purchase_timestamp'][:10]<=filters['end']:continue
            customer=customers[order['customer_id']]
            if filters.get('state') and customer['customer_state']!=filters['state']:continue
            if filters.get('category') and categories[item['product_id']]!=filters['category']:continue
            cents+=item['cents'];units+=1
            selected[order['order_id']]=customer['customer_unique_id']
        return {'revenue_cents':cents,'order_count':len(selected),'item_count':units,
            'customer_count':len(set(selected.values())),
            'average_order_value_cents':cents/len(selected) if selected else None}
    return calculate


def require(condition,message):
    if not condition:raise AssertionError(message)


def verify(api_url,output):
    calculate=raw_expectations()
    cases=[
      ('all_delivered',{'start':'2016-09-04','end':'2018-10-17'}),
      ('july',{'start':'2018-07-01','end':'2018-07-31'}),
      ('july_category_state',{'start':'2018-07-01','end':'2018-07-31','category':'cama_mesa_banho','state':'SP'}),
      ('june_rj',{'start':'2018-06-01','end':'2018-06-30','state':'RJ'}),
      ('empty_filter',{'start':'2018-07-01','end':'2018-07-31','state':'XX'}),
      ('quoted_filter',{'start':'2018-07-01','end':'2018-07-31','category':"x' OR 1=1--"}),
    ]
    session=requests.Session();results=[]
    for name,filters in cases:
        expected=calculate(filters);begin=time.perf_counter()
        response=session.get(api_url+'/api/dashboard',params=filters,timeout=60)
        response.raise_for_status();data=response.json();elapsed=time.perf_counter()-begin
        actual=data['kpis']
        for key,value in expected.items():
            if key=='average_order_value_cents' and value is not None:
                require(abs(actual[key]-value)<.01,f'{name}: average mismatch')
            else:require(actual[key]==value,f'{name}: {key} mismatch')
        require(data['meta']['data_source']=='olist','API must identify real source')
        results.append({'name':name,'filters':filters,'expected':expected,'matches':True,'elapsed_seconds':round(elapsed,3)})
    db=make_engine()
    with db.connect() as conn:
        warehouse=dict(conn.execute(text("SELECT COUNT(*) AS orders,SUM(revenue_cents) AS revenue_cents,SUM(item_count) AS item_count FROM fact_order WHERE status='delivered'")).mappings().one())
        day=dict(conn.execute(text('SELECT SUM(order_count) AS orders,SUM(revenue_cents) AS revenue_cents,SUM(item_count) AS item_count FROM agg_day')).mappings().one())
        all_expected=results[0]['expected']
        for key,expected_key in [('orders','order_count'),('revenue_cents','revenue_cents'),('item_count','item_count')]:
            require(int(warehouse[key])==all_expected[expected_key],f'Warehouse {key} differs from raw CSV')
            require(int(day[key])==all_expected[expected_key],f'Daily aggregate {key} differs from raw CSV')
        missing_payment=conn.execute(text("SELECT COUNT(*) FROM fact_order WHERE status='delivered' AND payment_cents IS NULL")).scalar_one()
        require(missing_payment==1,'Known missing payment must be null and preserve the order')
        etl=json.loads(conn.execute(text('SELECT payload FROM etl_run WHERE id=1')).scalar_one())
        dialect=db.dialect.name
    # Validate actual pagination/detail contracts without publishing IDs in evidence.
    filters={'start':'2018-07-01','end':'2018-07-31','category':'cama_mesa_banho','state':'SP'}
    listed=session.get(api_url+'/api/orders',params={**filters,'page':1,'page_size':5},timeout=30)
    listed.raise_for_status();page1=listed.json()
    require(page1['total']==results[2]['expected']['order_count'],'Order list total differs from filtered KPI')
    require(len(page1['rows'])==min(5,page1['total']),'Page size incorrect')
    if page1['rows']:
        row=page1['rows'][0]
        detail=session.get(api_url+'/api/orders/'+row['order_id'],params={'category':filters['category']},timeout=30)
        detail.raise_for_status();detail=detail.json()
        require(sum(item['price_cents'] for item in detail['items'])==row['revenue_cents'],'Detail/category subtotal mismatch')
        require(all(item['category']==filters['category'] for item in detail['items']),'Detail escaped selected category')
    page2=session.get(api_url+'/api/orders',params={**filters,'page':2,'page_size':5},timeout=30).json()
    require(not ({x['order_id'] for x in page1['rows']}&{x['order_id'] for x in page2['rows']}),'Pagination overlaps')
    require(session.get(api_url+'/api/dashboard',params={'start':'2018-07-31','end':'2018-07-01'},timeout=30).status_code==422,'Reversed dates must fail')
    require(session.get(api_url+'/api/orders/unknown-order',timeout=30).status_code==404,'Unknown detail must be 404')
    result={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'database':dialect,
        'data_version':etl['data_version'],'cases':results,'raw_sql_api_reconciled':True,
        'daily_aggregate_reconciled':True,'missing_payment_retained':True,'pagination_and_detail':True,
        'invalid_input_and_not_found':True,'notes':'Durations are one local run, not a load-test or SLA.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'database':dialect,'cases':len(results),'raw_sql_api_reconciled':True,'daily_aggregate_reconciled':True}))
    db.dispose()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default=str(ROOT/'docs/core/acceptance.json'))
    args=parser.parse_args();verify(args.api_url.rstrip('/'),args.output)
