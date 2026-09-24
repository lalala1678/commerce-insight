from datetime import date,timedelta
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.db import make_engine
from backend.etl import import_data
from backend.reports import detect_anomalies, decompose, contributions, build_report, markdown, html_report, delivery_diagnosis, build_investigations
from test_etl import create_olist_fixture


def test_symmetric_decomposition_exact_and_zero_denominator():
    old=dict(order_count=10,revenue_cents=10000)
    new=dict(order_count=20,revenue_cents=30000)
    d=decompose(new,old)
    assert d['order_effect_cents']==12500
    assert d['aov_effect_cents']==7500
    assert decompose(dict(order_count=0,revenue_cents=0),old) is None


def test_contribution_union_accounts_for_appearing_and_disappearing_categories():
    rows=contributions([dict(name='a',revenue_cents=100),dict(name='b',revenue_cents=400)],
                       [dict(name='a',revenue_cents=200),dict(name='c',revenue_cents=300)])
    assert {r['name']:r['delta_cents'] for r in rows}==dict(a=-100,b=400,c=-300)
    assert sum(r['delta_cents'] for r in rows)==0


def test_anomaly_has_no_future_or_current_day_in_baseline():
    day=date(2018,7,23);coverage=(date(2017,1,1),date(2018,7,31))
    daily={(day-timedelta(days=7*k)).isoformat():dict(order_count=20) for k in range(1,9)}
    daily[day.isoformat()]=dict(order_count=100)
    result=detect_anomalies(daily,day,day,coverage)[0]
    assert result['status']=='high' and result['baseline_median']==20 and result['threshold']==10
    daily[(day+timedelta(days=7)).isoformat()]=dict(order_count=100000)
    assert detect_anomalies(daily,day,day,coverage)[0]==result
    daily[day.isoformat()]=dict(order_count=0)
    assert detect_anomalies(daily,day,day,coverage)[0]['status']=='low'


def test_rule_threshold_is_strict_and_sparse_is_not_flagged():
    day=date(2018,7,23);coverage=(date(2017,1,1),date(2018,7,31))
    daily={(day-timedelta(days=7*k)).isoformat():dict(order_count=20) for k in range(1,9)}
    daily[day.isoformat()]=dict(order_count=30)
    assert detect_anomalies(daily,day,day,coverage)[0]['status']=='normal'
    assert detect_anomalies({},day,day,coverage)[0]['status']=='insufficient'
    assert detect_anomalies(daily,day,day,(day-timedelta(days=55),day))[0]['baseline_n']==7
    assert detect_anomalies(daily,day,day,None)[0]['order_count'] is None


def test_group_samples_medians_and_stratum_gate():
    rows=[dict(category='a',state='SP',is_late=0,review_score=5,order_count=20),
          dict(category='a',state='SP',is_late=1,review_score=1,order_count=20),
          dict(category='a',state='SP',is_late=1,review_score=None,order_count=2),
          dict(category='b',state='RJ',is_late=1,review_score=4,order_count=1)]
    d=delivery_diagnosis(rows)
    assert d['groups']['late']['missing_reviews']==2
    assert d['groups']['late']['median_score']==1
    assert d['strata']['category'][0]['score_gap']==-4
    assert d['strata']['category'][1]['score_gap'] is None


def test_investigation_evidence_resolves_to_report_values_even_when_previous_has_zero_orders(warehouse):
    report=build_report(warehouse,start='2018-07-01',end='2018-07-31')
    report['previous']=dict(order_count=0,revenue_cents=0,average_order_value_cents=None)
    report['previous_daily_revenue_cents']=0
    report['delta_cents']=report['current']['revenue_cents']
    report['contributions']={
        'category':contributions([dict(name='casa',revenue_cents=45000)],[]),
        'state':contributions([dict(name='SP',revenue_cents=45000)],[])}
    report['delivery']=delivery_diagnosis([
        dict(category='casa',state='SP',is_late=0,review_score=5,order_count=20),
        dict(category='casa',state='SP',is_late=1,review_score=1,order_count=20)])
    tasks=build_investigations(report)
    assert [task['id'] for task in tasks]==['sales-change','delivery-review']
    assert '待验证' in tasks[0]['hypothesis'] and '相关性' in tasks[1]['hypothesis']
    assert '品类 casa' in tasks[0]['title'] and '客户州 SP' in tasks[0]['title']
    assert all(task['checks'] and task['missing_data'] and task['verification_metric'] for task in tasks)
    for task in tasks:
        for evidence in task['evidence']:
            assert evidence['anchor'] in {'sales-breakdown','category-contribution','state-contribution','delivery-diagnosis'}
            actual=report
            for segment in evidence['pointer'].strip('/').split('/'):
                actual=actual[int(segment)] if isinstance(actual,list) else actual[segment]
            assert evidence['value']==actual
    report['investigations']=tasks
    md=markdown(report)
    assert '## 核查任务（尚未执行）' in md
    assert '/contributions/category/0/delta_cents' in md
    assert '验证指标：' in md and '还需补充的数据：' in md
    assert '核查步骤：' in html_report(report)
    report['contributions']['category'][0]['name']='<script>unsafe</script>'
    report['investigations']=build_investigations(report)
    escaped=html_report(report)
    assert '<script>' not in escaped and '&lt;script&gt;' in escaped
    report['previous']=report['current'].copy()
    report['previous_daily_revenue_cents']=report['daily_revenue_cents']
    report['delta_cents']=0
    assert [task['id'] for task in build_investigations(report)]==['delivery-review']


@pytest.fixture
def warehouse(tmp_path):
    db=make_engine(f'sqlite:///{tmp_path/"report.db"}')
    import_data(create_olist_fixture(tmp_path/'raw'),db)
    yield db
    db.dispose()


def test_real_scope_no_fanout_and_missing_coverage(warehouse):
    r=build_report(warehouse,start='2018-07-01',end='2018-07-31')
    assert r['current']['revenue_cents']==45000
    assert r['previous'] is None and r['decomposition'] is None
    assert sum(x['order_count'] for x in r['delivery']['groups'].values())==3
    assert sum(g['on_time']['order_count']+g['late']['order_count']+g['unknown']['order_count'] for g in r['delivery']['strata']['category'])==3
    assert all(x['status']=='insufficient' for x in r['anomalies'])
    assert r['investigations']==[]  # no comparable period or sufficiently sized review groups
    filtered=build_report(warehouse,category='casa',state='SP')
    assert filtered['current']['order_count']==0 # default last July week
    assert '不可计算' in markdown(filtered)


def test_export_is_escaped_and_reuses_period_and_version(warehouse):
    r=build_report(warehouse,category='<script>alert(1)</script>')
    h=html_report(r)
    assert '<script>' not in h and '&lt;script&gt;' in h
    assert r['meta']['data_version'] in h
    assert 'CC BY-NC-SA 4.0' in h
    assert '经营周报' in markdown(r)
    r['meta']['is_calendar_week']=False
    assert markdown(r).startswith('# 经营期间报告')


def test_api_formats_dates_empty_and_missing_warehouse(warehouse,tmp_path):
    with TestClient(create_app(warehouse)) as client:
        r=client.get('/api/reports')
        assert r.status_code==200 and 'rendered' in r.json()
        for fmt in ('markdown','html'):
            out=client.get('/api/reports',params={'format':fmt})
            assert out.status_code==200 and 'attachment' in out.headers['content-disposition']
        assert client.get('/api/reports?start=2018-07-31&end=2018-07-01').status_code==422
        assert client.get('/api/reports?start=2017-01-01&end=2018-07-31').status_code==422
        assert client.get('/api/reports?format=pdf').status_code==422
        assert client.get('/api/reports?state=XX').json()['current']['order_count']==0
    db=make_engine(f'sqlite:///{tmp_path/"empty.db"}')
    with TestClient(create_app(db)) as client:assert client.get('/api/reports').status_code==503
    db.dispose()
