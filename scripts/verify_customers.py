"""Independent raw CSV arithmetic -> customer HTTP API; aggregate-only evidence."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = ['olist_orders_dataset.csv', 'olist_order_items_dataset.csv',
         'olist_customers_dataset.csv', 'olist_products_dataset.csv']


def verify(api_url, output):
    raw = ROOT/'data/raw'
    hashes = {name: hashlib.sha256((raw/name).read_bytes()).hexdigest() for name in FILES}
    def read(name):
        with (raw/name).open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))
    orders = {r['order_id']: r for r in read(FILES[0])}
    customers = {r['customer_id']: r for r in read(FILES[2])}
    products = {r['product_id']: r['product_category_name'].strip() or 'unknown' for r in read(FILES[3])}
    items = read(FILES[1])
    cases = [
        dict(start='2018-07-01', end='2018-07-31'),
        dict(start='2018-02-01', end='2018-07-31'),
        dict(start='2017-01-01', end='2018-07-31'),
        dict(start='2018-07-01', end='2018-07-31', category='cama_mesa_banho',state='SP'),
        dict(start='2018-07-02', end='2018-07-02',state='RJ'),
        dict(start='2018-07-01', end='2018-07-31',state='XX'),
    ]
    evidence=[]; versions=set()
    for filters in cases:
        first={}
        for order in orders.values():
            day=order['order_purchase_timestamp'][:10]
            if order['order_status']=='delivered' and day<=filters['end']:
                uid=customers[order['customer_id']]['customer_unique_id']
                first[uid]=min(first.get(uid,day),day)
        matched=defaultdict(dict)
        for item in items:
            o=orders[item['order_id']]; c=customers[o['customer_id']]
            day=o['order_purchase_timestamp'][:10]
            if o['order_status']!='delivered' or not filters['start']<=day<=filters['end']:continue
            if filters.get('state') and c['customer_state']!=filters['state']:continue
            if filters.get('category') and products[item['product_id']]!=filters['category']:continue
            row=matched[c['customer_unique_id']].setdefault(item['order_id'],[day,0])
            row[1]+=int(Decimal(item['price'])*100)
        triples=[]; new=0
        expected_groups={format(i,'03b'):[0,0,0] for i in range(8)}
        for uid, purchases in matched.items():
            r=(date.fromisoformat(filters['end'])-date.fromisoformat(max(v[0] for v in purchases.values()))).days
            f=len(purchases);m=sum(v[1] for v in purchases.values())
            new+=first[uid]>=filters['start']
            triples.append((r,f,m))
            code=('1' if r<=30 else '0')+('1' if f>=2 else '0')+('1' if m>=20000 else '0')
            g=expected_groups[code];g[0]+=1;g[1]+=f;g[2]+=m
        n=len(triples);repeat=sum(f>=2 for r,f,m in triples)
        summary=dict(customer_count=n,new_customers=new,returning_customers=n-new,repeat_customers=repeat,
                     repeat_rate=repeat/n if n else None,order_count=sum(x[1] for x in triples),
                     revenue_cents=sum(x[2] for x in triples),single_purchase_share=(n-repeat)/n if n else None)
        response=requests.get(api_url.rstrip('/')+'/api/customers',params=filters,timeout=90)
        response.raise_for_status();result=response.json();versions.add(result['meta']['data_version'])
        assert result['summary']==summary, ('summary',filters)
        expected_frequency=[dict(frequency=f,customer_count=c) for f,c in sorted(Counter(x[1] for x in triples).items())]
        assert result['frequency_distribution']==expected_frequency, ('frequency',filters)
        for index,name in enumerate(['recency_days','frequency','monetary_cents']):
            v=sorted(x[index] for x in triples)
            d=dict(min=v[0],median=median(v),p75=v[(3*len(v)+3)//4-1],max=v[-1]) if v else dict.fromkeys(['min','median','p75','max'])
            assert result['distribution'][name]==d, ('distribution',filters,name)
        assert {g['key']:[g['customer_count'],g['order_count'],g['revenue_cents']] for g in result['segments']}==expected_groups
        assert sum(g['customer_count'] for g in result['segments'])==n
        assert summary['new_customers']+summary['returning_customers']==n
        evidence.append(dict(filters=filters,summary=summary,distribution=result['distribution'],
                             frequency_distribution=expected_frequency,segments=result['segments'],matches_raw=True))
    assert len(versions)==1, 'API data version changed; repeat on a stable import'
    assert hashes=={name:hashlib.sha256((raw/name).read_bytes()).hexdigest() for name in FILES}
    receipt=json.loads((ROOT/'docs/core/etl_receipt.json').read_text(encoding='utf-8'))
    assert versions=={receipt['data_version']}, 'Update ETL receipt before verifying a new dataset'
    assert all(receipt['file_hashes'][name]==value for name,value in hashes.items())
    report={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'data_version':versions.pop(),
            'source_hashes':hashes,'method':'Independent CSV / Decimal; actual HTTP, no business-function reuse',
            'rules':'R<=30, F>=2, M>=20000 cents; exploratory thresholds, not validated value segments',
            'cases':evidence}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(evidence),'all_match_raw':True,'july':evidence[0]['summary']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default=str(ROOT/'docs/customers/acceptance.json'))
    args=parser.parse_args();verify(args.api_url,args.output)
