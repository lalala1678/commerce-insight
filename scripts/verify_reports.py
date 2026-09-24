"""Independent raw-file verification of report metrics, strata and alert dates."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median, stdev
import requests

ROOT=Path(__file__).resolve().parents[1]
FILES=['olist_orders_dataset.csv','olist_order_items_dataset.csv','olist_customers_dataset.csv',
       'olist_products_dataset.csv','olist_order_reviews_dataset.csv']


def verify(url, output):
    raw=ROOT/'data/raw'
    hashes={f:hashlib.sha256((raw/f).read_bytes()).hexdigest() for f in FILES}
    def read(f):
        with (raw/f).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
    clients={r['customer_id']:r for r in read(FILES[2])}
    products={r['product_id']:r['product_category_name'].strip() or 'unknown' for r in read(FILES[3])}
    items=defaultdict(list)
    for r in read(FILES[1]):items[r['order_id']].append((products[r['product_id']],int(Decimal(r['price'])*100)))
    reviews={}
    for i,r in enumerate(read(FILES[4])):
        key=(r['review_answer_timestamp'],r['review_creation_date'],r['review_id'],i)
        if r['order_id'] not in reviews or key>reviews[r['order_id']][0]:reviews[r['order_id']]=(key,int(r['review_score']))
    orders=[]
    for r in read(FILES[0]):
        if r['order_status']!='delivered':continue
        client=clients[r['customer_id']];arrival=r['order_delivered_customer_date'];estimate=r['order_estimated_delivery_date']
        late=int(arrival[:10]>estimate[:10]) if arrival and estimate and arrival>=r['order_purchase_timestamp'] else None
        orders.append(dict(day=r['order_purchase_timestamp'][:10],uid=client['customer_unique_id'],state=client['customer_state'],
                           items=items[r['order_id']],late=late,score=reviews.get(r['order_id'],(None,None))[1]))
    coverage=(max('2017-01-01',min(r['day'] for r in orders)),min('2018-07-31',max(r['day'] for r in orders)))
    def select(start,end,category='',state=''):
        result=[]
        for r in orders:
            if not start<=r['day']<=end or (state and state!=r['state']):continue
            selected=[(cat,cents) for cat,cents in r['items'] if not category or category==cat]
            if not selected:continue
            amounts=defaultdict(int)
            for cat,cents in selected:amounts[cat]+=cents
            result.append({**r,'amounts':amounts,'cents':sum(amounts.values()),'item_count':len(selected),
                           'category':sorted(amounts,key=lambda cat:(-amounts[cat],cat))[0]})
        return result
    def kpis(rows):
        n=len(rows);amount=sum(r['cents'] for r in rows)
        return dict(order_count=n,revenue_cents=amount,item_count=sum(r['item_count'] for r in rows),
                    customer_count=len({r['uid'] for r in rows}),average_order_value_cents=amount/n if n else None)
    def groups(rows):
        answer={}
        for key,late in [('on_time',0),('late',1),('unknown',None)]:
            matched=[r for r in rows if r['late']==late];scores=[r['score'] for r in matched if r['score'] is not None]
            counts=Counter(scores);n=len(scores)
            answer[key]=dict(order_count=len(matched),reviewed_orders=n,missing_reviews=len(matched)-n,
                             mean_score=sum(scores)/n if n else None,median_score=median(scores) if n else None,
                             score_sd=stdev(scores) if n>1 else None,low_score_share=sum(x<=2 for x in scores)/n if n else None,
                             scores=[dict(score=i,count=counts[i]) for i in range(1,6)])
        return answer
    def equal(actual,expected,path='result'):
        if isinstance(expected,dict):
            for k,v in expected.items():equal(actual[k],v,path+'.'+k)
        elif isinstance(expected,list):
            assert len(actual)==len(expected),path
            for i,v in enumerate(expected):equal(actual[i],v,path+str(i))
        elif isinstance(expected,float):assert abs(actual-expected)<1e-7,(path,actual,expected)
        else:assert actual==expected,(path,actual,expected)
    cases=[dict(start='2018-07-01',end='2018-07-31'),dict(start='2018-07-23',end='2018-07-29'),
           dict(start='2017-11-20',end='2017-11-26'),dict(start='2018-07-01',end='2018-07-31',category='cama_mesa_banho',state='SP'),
           dict(start='2018-07-23',end='2018-07-29',state='XX'),dict(start='2017-01-01',end='2017-01-07')]
    evidence=[];versions=set()
    for filters in cases:
        response=requests.get(url.rstrip('/')+'/api/reports',params=filters,timeout=90);response.raise_for_status();r=response.json()
        versions.add(r['meta']['data_version']);rows=select(**filters);equal(r['current'],kpis(rows))
        old=select(r['meta']['comparison_start'],r['meta']['comparison_end'],filters.get('category',''),filters.get('state',''))
        start=date.fromisoformat(filters['start']);end=date.fromisoformat(filters['end'])
        # Independently derive previous month or equal duration, not just trust API dates.
        previous_end=start-timedelta(days=1)
        natural=start.day==1 and start.year==end.year and start.month==end.month and (end+timedelta(days=1)).day==1
        previous_start=previous_end.replace(day=1) if natural else previous_end-(end-start)
        assert r['meta']['comparison_start']==previous_start.isoformat() and r['meta']['comparison_end']==previous_end.isoformat()
        comparable=coverage[0]<=previous_start.isoformat() and filters['end']<=coverage[1]
        assert r['meta']['comparable']==comparable
        if comparable:
            equal(r['previous'],kpis(old));delta=kpis(rows)['revenue_cents']-kpis(old)['revenue_cents'];assert r['delta_cents']==delta
            if rows and old:
                volume=(len(rows)-len(old))*(kpis(rows)['average_order_value_cents']+kpis(old)['average_order_value_cents'])/2
                equal(r['decomposition']['order_effect_cents'],volume)
                equal(sum(r['decomposition'][key] for key in ['order_effect_cents','aov_effect_cents']),float(delta))
            for dimension in ['category','state']:
                now=defaultdict(int);before=defaultdict(int)
                for target,source in [(now,rows),(before,old)]:
                    for x in source:
                        if dimension=='category':
                            for cat,cents in x['amounts'].items():target[cat]+=cents
                        else:target[x['state']]+=x['cents']
                expected={key:(now[key],before[key],now[key]-before[key]) for key in set(now)|set(before)}
                actual={x['name']:(x['current_cents'],x['previous_cents'],x['delta_cents']) for x in r['contributions'][dimension]}
                assert actual==expected and sum(x[2] for x in actual.values())==delta
        else:assert r['previous'] is None and r['decomposition'] is None
        equal(r['delivery']['groups'],groups(rows))
        for dimension in ['category','state']:
            bins=defaultdict(list)
            for row in rows:bins[row[dimension]].append(row)
            assert set(bins)=={x['name'] for x in r['delivery']['strata'][dimension]}
            for x in r['delivery']['strata'][dimension]:
                g=groups(bins[x['name']]);equal(x,g)
                enough=min(g['late']['reviewed_orders'],g['on_time']['reviewed_orders'])>=20
                assert x['comparison_eligible']==enough
                equal(x['score_gap'],g['late']['mean_score']-g['on_time']['mean_score'] if enough else None)
        history=select((start-timedelta(days=56)).isoformat(),filters['end'],filters.get('category',''),filters.get('state',''))
        counts=Counter(x['day'] for x in history)
        assert len(r['anomalies'])==(end-start).days+1
        for i,alert in enumerate(r['anomalies']):
            day=start+timedelta(days=i);prior=[(day-timedelta(days=7*k)).isoformat() for k in range(1,9)]
            covered=lambda s:coverage[0]<=s<=coverage[1]
            assert alert['day']==day.isoformat() and alert['baseline_n']==sum(covered(s) for s in prior)
            assert alert['history_start']==prior[-1] and alert['history_end']==prior[0]
            equal(alert['order_count'],counts[day.isoformat()] if covered(day.isoformat()) else None)
            status='insufficient'
            if covered(day.isoformat()) and all(covered(s) for s in prior):
                center=median(counts[s] for s in prior);mad=median(abs(counts[s]-center) for s in prior)
                threshold=max(3*1.4826*mad,center*.5,10);equal(alert['baseline_median'],center);equal(alert['threshold'],threshold)
                if center>=5:
                    diff=counts[day.isoformat()]-center
                    status=('high' if diff>0 else 'low') if abs(diff)>threshold else 'normal'
            assert alert['status']==status
        assert r['meta']['data_version'] in r['rendered']['markdown'] and r['meta']['data_version'] in r['rendered']['html']
        evidence.append(dict(filters=filters,current=r['current'],previous=r['previous'],delta_cents=r['delta_cents'],
                             anomalies=[x for x in r['anomalies'] if x['status'] in ('high','low')],
                             insufficient_days=sum(x['status']=='insufficient' for x in r['anomalies']),
                             contributions_reconcile=True,delivery_and_strata_match=True,all_days_match=True))
        if not filters.get('category') and filters['start']=='2018-07-01':
            saved=json.loads((ROOT/'docs/reports/case-data/commerce-report-2018-07-01-2018-07-31.json').read_text(encoding='utf-8'))
            for field in ('current','previous','decomposition','contributions','anomalies','delivery'):equal(saved[field],r[field])
    assert len(versions)==1
    receipt=json.loads((ROOT/'docs/core/etl_receipt.json').read_text(encoding='utf-8'))
    assert versions=={receipt['data_version']} and all(receipt['file_hashes'][name]==digest for name,digest in hashes.items())
    assert hashes=={f:hashlib.sha256((raw/f).read_bytes()).hexdigest() for f in FILES}
    result=dict(verified_at_utc=datetime.now(timezone.utc).isoformat(),data_version=versions.pop(),source_hashes=hashes,
                method='Independent CSV and HTTP; no report implementation reuse',cases=evidence,sqlite_case_matches_mysql=True)
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(evidence),'all_match_raw':True,'sqlite_case_matches_mysql':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--api-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default=str(ROOT/'docs/reports/acceptance.json'))
    args=parser.parse_args();verify(args.api_url,args.output)
