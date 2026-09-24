"""Independent standard-library verification of key audit claims, no DB writes."""
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def verify(root=ROOT):
    a=json.loads((root/'docs/audit/profile.json').read_text(encoding='utf-8'))
    verified=0
    for table in a['tables'].values():
        path=root/'data/raw'/table['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==table['sha256'], 'Raw fingerprint mismatch'
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);count=0;nulls=Counter()
            for row in reader:
                count+=1
                nulls.update(k for k,v in row.items() if v is not None and not v.strip())
        assert count==table['rows'], 'Row count mismatch'
        for col in table['columns']:
            assert nulls[col['name']]==col['missing'], 'Missingness mismatch'
            verified+=1
    with (root/'data/raw/olist_orders_dataset.csv').open(encoding='utf-8',newline='') as stream:
        orders=list(csv.DictReader(stream))
    delivered={o['order_id'] for o in orders if o['order_status']=='delivered'}
    assert len(delivered)==a['quality']['statuses']['delivered']
    amount=Decimal(0);items=0
    with (root/'data/raw/olist_order_items_dataset.csv').open(encoding='utf-8',newline='') as stream:
        for item in csv.DictReader(stream):
            if item['order_id'] in delivered:
                amount+=Decimal(item['price']);items+=1
    assert int(amount*100)==a['quality']['money']['delivered_item_revenue_cents']
    assert items==a['quality']['money']['delivered_item_rows']
    assert sum(x['orders'] for x in a['quality']['monthly_orders'])==len(orders)
    freq=a['quality']['frequency_distribution']
    assert sum(x['customers'] for x in freq)==a['quality']['unique_customers_delivered']
    assert sum(x['orders_per_customer']*x['customers'] for x in freq)==len(delivered)
    # Includes fields repeated across tables; each is independently checked.
    result={'verified':True,'files':len(a['tables']),'field_missingness_checks':verified,
            'raw_hashes_unchanged':True,'delivered_orders':len(delivered),
            'delivered_revenue_cents':int(amount*100),'data_version':a['data_version']}
    (root/'docs/audit/verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':print(json.dumps(verify()))
