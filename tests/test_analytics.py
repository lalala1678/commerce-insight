"""Hand-calculated serving tests; no ETL/analytics code generates the expectations."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend import analytics
from backend.app import create_app
from backend.db import make_engine
from backend.warehouse import dim_customer, dim_product, dim_seller, etl_run, fact_item, fact_order, warehouse_metadata


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "analytics.db"}')
    warehouse_metadata.create_all(engine)
    dates = ['2018-07-01 00:00:00', '2018-07-31 23:59:59', '2018-07-02 12:00:00',
             '2018-07-02 00:00:00', '2018-06-30 23:59:59', '2018-08-01 00:00:00']
    amounts = [15001, 20000, 10000, 99999, 10000, 3000]
    with engine.begin() as conn:
        conn.execute(dim_customer.insert(), [{'customer_id': f'c{i}', 'customer_unique_id': 'u1' if i < 3 else f'u{i}',
                                              'state': 'RJ' if i == 3 else 'SP'} for i in range(1, 7)])
        conn.execute(dim_product.insert(), [{'product_id': 'a', 'category': 'cat_a', 'category_english': 'Category A'},
                                            {'product_id': 'b', 'category': 'cat_b', 'category_english': None}])
        conn.execute(dim_seller.insert(), [{'seller_id': 's1', 'state': 'SP'}])
        rows = []
        for i, timestamp in enumerate(dates, 1):
            rows.append({'order_id': f'o{i}', 'customer_id': f'c{i}', 'purchase_at': timestamp,
                         'purchase_date': timestamp[:10], 'status': 'canceled' if i == 4 else 'delivered',
                         'revenue_cents': amounts[i-1], 'freight_cents': 1000, 'item_count': 2 if i in (1, 3) else 1,
                         'payment_cents': None if i == 2 else amounts[i-1]+1000,
                         'payment_count': 0 if i == 2 else 2, 'review_count': 3 if i == 1 else (1 if i == 3 else 0),
                         'review_score': {1: 5, 3: 2}.get(i), 'is_late': {1: 0, 3: 1}.get(i),
                         'delivery_seconds': {1: 86400, 3: 172800}.get(i),
                         'quality_flags': '["missing_payment"]' if i == 2 else '[]'})
        conn.execute(fact_order.insert(), rows)
        items = [('o1', 1, 'a', 10001), ('o1', 2, 'b', 5000), ('o2', 1, 'a', 20000),
                 ('o3', 1, 'a', 4000), ('o3', 2, 'b', 6000), ('o4', 1, 'a', 99999),
                 ('o5', 1, 'a', 10000), ('o6', 1, 'a', 3000)]
        conn.execute(fact_item.insert(), [{'order_id': oid, 'item_id': iid, 'product_id': pid, 'seller_id': 's1',
                                          'price_cents': cents, 'freight_cents': 500} for oid, iid, pid, cents in items])
        conn.execute(etl_run.insert(), {'id': 1, 'payload': json.dumps({
            'data_version': 'fixture-v1', 'source': 'olist', 'currency': 'BRL',
            'observed_start': '2017-01-01', 'observed_end': '2018-08-29', 'imported_at': '2026-09-19T00:00:00Z'})})
    yield engine
    engine.dispose()


def test_exact_cents_order_grain_and_stable_customers(db):
    result = analytics.dashboard(db)
    assert result['kpis'] == {'revenue_cents': 45001, 'order_count': 3, 'item_count': 5,
                              'customer_count': 2, 'average_order_value_cents': 45001/3}
    assert sum(row['revenue_cents'] for row in result['trend']) == 45001
    assert sum(row['revenue_cents'] for row in result['categories']) == 45001
    assert sum(row['revenue_cents'] for row in result['regions']) == 45001
    assert result['previous']['revenue_cents'] == 10000
    assert result['meta']['comparison_start'] == '2018-06-01'
    assert result['meta']['comparison_end'] == '2018-06-30'
    assert '31 天' in result['meta']['comparison_label']


def test_category_restricts_money_without_duplicating_orders(db):
    result = analytics.dashboard(db, category='cat_a')
    assert result['kpis']['revenue_cents'] == 34001
    assert result['kpis']['order_count'] == 3
    assert result['kpis']['item_count'] == 3
    assert result['kpis']['customer_count'] == 2
    scoped = analytics.dashboard(db, category='cat_b', state='RJ')
    assert scoped['kpis']['revenue_cents'] == 6000
    assert scoped['kpis']['order_count'] == 1
    assert scoped['fulfillment']['late_rate'] == 1


def test_inclusive_dates_and_equal_length_comparison(db):
    assert analytics.dashboard(db, '2018-07-31', '2018-07-31')['kpis']['revenue_cents'] == 20000
    assert analytics.dashboard(db, '2018-07-01', '2018-07-01')['kpis']['revenue_cents'] == 15001
    result = analytics.dashboard(db, '2018-07-02', '2018-07-03')
    assert result['meta']['comparison_start'] == '2018-06-30'
    assert result['meta']['comparison_end'] == '2018-07-01'
    assert result['previous']['revenue_cents'] == 25001


def test_missing_dates_and_reviews_use_their_own_denominators(db):
    value = analytics.dashboard(db)['fulfillment']
    assert value['eligible_orders'] == 2
    assert value['late_orders'] == 1
    assert value['late_rate'] == .5
    assert value['delivery_sample_count'] == 2
    assert value['average_delivery_days'] == 1.5
    assert value['median_delivery_days'] == 1.5
    assert value['reviewed_orders'] == 2
    assert value['average_review_score'] == 3.5
    assert sum(row['order_count'] for row in value['groups']) == 3
    assert sum(row['order_count'] for row in value['scores']) == 2


@pytest.mark.parametrize('category', ['not-a-category', "cat_a' OR 1=1 --"])
def test_empty_and_untrusted_filter_return_empty_scope(db, category):
    result = analytics.dashboard(db, category=category)
    assert result['kpis']['order_count'] == 0
    assert result['kpis']['revenue_cents'] == 0
    assert result['kpis']['average_order_value_cents'] is None
    assert result['fulfillment']['late_rate'] is None
    assert result['fulfillment']['average_review_score'] is None
    assert result['fulfillment']['median_delivery_days'] is None
    assert result['categories'] == []


def test_trend_complete_buckets_and_sparse_boundaries(db):
    weekly = analytics.dashboard(db, grain='week')['trend']
    assert weekly[0]['period'] == '2018-06-25'
    assert weekly[0]['complete'] is False
    assert weekly[1]['period'] == '2018-07-02'
    assert weekly[1]['complete'] is True
    assert weekly[-1]['complete'] is False
    assert sum(r['revenue_cents'] for r in weekly) == 45001
    monthly = analytics.dashboard(db, grain='month')['trend']
    assert monthly == [{'period': '2018-07-01', 'revenue_cents': 45001, 'order_count': 3, 'complete': True}]
    partial = analytics.dashboard(db, '2018-07-02', '2018-07-04', grain='month')
    assert partial['trend'][0]['complete'] is False
    sparse = analytics.dashboard(db, '2016-11-01', '2016-11-30', grain='month')
    assert sparse['previous'] is None
    assert sparse['trend'][0]['revenue_cents'] is None
    tail = analytics.dashboard(db, '2018-08-01', '2018-08-31', grain='month')
    assert tail['previous'] is None
    assert tail['trend'][0]['complete'] is False
    assert tail['trend'][0]['revenue_cents'] == 3000


def test_order_pagination_and_category_scoped_detail(db):
    page1 = analytics.orders(db, page=1, page_size=2)
    page2 = analytics.orders(db, page=2, page_size=2)
    assert page1['total'] == 3
    assert [r['order_id'] for r in page1['rows'] + page2['rows']] == ['o2', 'o3', 'o1']
    assert page1['rows'][0]['payment_cents'] is None
    assert page1['rows'][0]['quality_flags'] == ['missing_payment']
    detail = analytics.order_details(db, 'o1', 'cat_a')
    assert detail['order']['revenue_cents'] == 10001
    assert detail['order']['total_order_revenue_cents'] == 15001
    assert detail['order']['payment_cents'] == 16001
    assert detail['order']['review_count'] == 3
    assert len(detail['items']) == 1
    assert sum(i['price_cents'] for i in detail['items']) == detail['order']['revenue_cents']
    assert '整单' in detail['scope_note']
    assert analytics.order_details(db, 'o4') is None
    assert analytics.order_details(db, 'o1', 'not-a-category') is None


def test_api_contract_and_validation(db):
    with TestClient(create_app(db)) as client:
        assert client.get('/api/health').json()['warehouse_ready'] is True
        opts = client.get('/api/options').json()
        assert opts['data_source'] == 'olist'
        assert opts['supported_end'] == '2018-07-31'
        assert opts['categories'][1] == {'value': 'cat_b', 'label': 'cat_b'}
        assert client.get('/api/dashboard').json() == analytics.dashboard(db)
        for params in ({'start': '2018-08-01', 'end': '2018-07-31'}, {'start': 'invalid'},
                       {'grain': 'year'}, {'start': '2010-01-01'}, {'end': '9999-12-31'}):
            assert client.get('/api/dashboard', params=params).status_code == 422
        for params in ({'page': 0}, {'page_size': 101}):
            assert client.get('/api/orders', params=params).status_code == 422
        assert client.get('/api/orders/o4').status_code == 404
        assert client.get('/api/orders/missing').status_code == 404
        assert client.get('/api/orders/o1', params={'category': 'cat_b'}).json()['order']['revenue_cents'] == 5000
        assert client.get('/api/dashboard', params={'category': 'x'*128}).status_code == 200
        assert client.get('/api/dashboard', params={'category': 'x'*129}).status_code == 422


def test_api_unimported_is_clear_and_health_is_not_readiness(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with TestClient(create_app(engine)) as client:
        assert client.get('/api/health').json()['warehouse_ready'] is False
        for path in ('/api/dashboard', '/api/orders', '/api/options', '/api/orders/o1'):
            response = client.get(path)
            assert response.status_code == 503
            assert 'backend.etl' in response.json()['detail']
    engine.dispose()


def test_sqlite_reads_one_snapshot_during_concurrent_change(db):
    with db.connect() as conn:
        conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    with analytics.read_snapshot(db) as reader:
        before = analytics._meta(reader)['data_version']
        with db.begin() as writer:
            writer.execute(text("UPDATE etl_run SET payload = :payload WHERE id=1"),
                           {'payload': json.dumps({'data_version': 'replacement'})})
        assert analytics._meta(reader)['data_version'] == before
    with analytics.read_snapshot(db) as reader:
        assert analytics._meta(reader)['data_version'] == 'replacement'


def _replace_coverage(db, start, end, *, canceled=False):
    with db.begin() as conn:
        payload = json.loads(conn.execute(text('SELECT payload FROM etl_run WHERE id=1')).scalar_one())
        payload.update(observed_start=start, observed_end=end)
        conn.execute(text('UPDATE etl_run SET payload=:payload WHERE id=1'), {'payload': json.dumps(payload)})
        if canceled:
            conn.execute(text("UPDATE fact_order SET status='canceled'"))
        else:
            conn.execute(text('UPDATE fact_order SET purchase_date=:day, purchase_at=:timestamp'),
                         {'day': start, 'timestamp': start + ' 12:00:00'})


def test_all_canceled_has_no_coverage_and_no_false_zero_trend(db):
    _replace_coverage(db, None, None, canceled=True)
    with TestClient(create_app(db)) as client:
        response = client.get('/api/options')
        assert response.status_code == 200
        opts = response.json()
        assert opts['supported_start'] is None and opts['supported_end'] is None
        assert opts['default_start'] == '2018-07-01' and opts['default_end'] == '2018-07-31'
        response = client.get('/api/dashboard')
        assert response.status_code == 200
        data = response.json()
        assert data['kpis']['order_count'] == 0 and data['previous'] is None
        assert all(point['revenue_cents'] is None and point['complete'] is False for point in data['trend'])
        assert any('没有已交付' in warning for warning in data['meta']['warnings'])


@pytest.mark.parametrize('observed_day', ['2016-10-15', '2018-09-03'])
def test_observed_dates_outside_core_get_valid_fallback(db, observed_day):
    _replace_coverage(db, observed_day, observed_day)
    with TestClient(create_app(db)) as client:
        opts = client.get('/api/options').json()
        assert opts['supported_start'] is None and opts['supported_end'] is None
        assert opts['default_start'] == observed_day and opts['default_end'] == observed_day
        response = client.get('/api/dashboard', params={'start': opts['default_start'], 'end': opts['default_end']})
        assert response.status_code == 200
        data = response.json()
        assert data['kpis']['order_count'] == 5
        assert data['kpis']['revenue_cents'] == 58001
        assert data['previous'] is None
        assert data['trend'] == [{'period': observed_day, 'revenue_cents': 58001, 'order_count': 5, 'complete': False}]
