import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.app import create_app
from backend.customers import customer_analysis, segment_key
from backend.db import make_engine
from backend.etl import import_data
from test_etl import create_olist_fixture


@pytest.fixture
def warehouse(tmp_path):
    db = make_engine(f'sqlite:///{tmp_path / "customers.db"}')
    import_data(create_olist_fixture(tmp_path/'raw'), db)
    yield db
    db.dispose()


def test_stable_identity_money_and_exhaustive_segments(warehouse):
    result = customer_analysis(warehouse)
    s = result['summary']
    assert s == dict(customer_count=2, new_customers=2, returning_customers=0,
                    repeat_customers=1, repeat_rate=.5, order_count=3,
                    revenue_cents=45000, single_purchase_share=.5)
    assert result['frequency_distribution'] == [dict(frequency=1,customer_count=1),dict(frequency=2,customer_count=1)]
    assert result['distribution']['recency_days']['min'] == 28
    assert result['distribution']['recency_days']['max'] == 29
    assert len(result['segments']) == 8
    assert sum(g['customer_count'] for g in result['segments']) == 2
    assert sum(g['revenue_cents'] for g in result['segments']) == 45000
    assert sum(g['order_count'] for g in result['segments']) == 3


def test_first_purchase_precedes_category_and_state_filters(warehouse):
    # Earlier purchase belongs to another category AND state, same stable person.
    with warehouse.begin() as conn:
        conn.execute(text("UPDATE fact_item SET product_id='product-b' WHERE order_id='order-a'"))
        conn.execute(text("UPDATE dim_customer SET state='MG' WHERE customer_id='customer-a'"))
    result=customer_analysis(warehouse,start='2018-07-02',end='2018-07-02',category='casa',state='SP')
    assert result['summary']['new_customers'] == 0
    assert result['summary']['returning_customers'] == 1
    assert result['summary']['repeat_rate'] == 0
    assert result['summary']['revenue_cents'] == 20000
    assert result['distribution']['recency_days']['max'] == 0


def test_customers_cross_states_are_not_additive(warehouse):
    with warehouse.begin() as conn:
        conn.execute(text("UPDATE dim_customer SET customer_unique_id='person-ab' WHERE customer_id='customer-c'"))
    assert customer_analysis(warehouse)['summary']['customer_count'] == 1
    assert customer_analysis(warehouse,state='SP')['summary']['customer_count'] == 1
    assert customer_analysis(warehouse,state='RJ')['summary']['customer_count'] == 1


def test_future_order_cannot_change_historical_analysis(warehouse):
    before=customer_analysis(warehouse)
    with warehouse.begin() as conn:
        conn.execute(text("UPDATE dim_customer SET customer_unique_id='person-ab' WHERE customer_id='customer-d'"))
        conn.execute(text("UPDATE fact_order SET status='delivered',purchase_date='2020-01-01',purchase_at='2020-01-01 00:00:00' WHERE order_id='order-d'"))
    assert customer_analysis(warehouse) == before


@pytest.mark.parametrize('r,f,m,expected',[(30,2,20000,'111'),(31,2,20000,'011'),(30,1,20000,'101'),(30,2,19999,'110')])
def test_inclusive_rfm_boundaries(r,f,m,expected):
    assert segment_key(r,f,m) == expected


def test_empty_null_denominators_and_ties(warehouse):
    result=customer_analysis(warehouse,state="x' OR 1=1--")
    assert result['summary']['customer_count'] == 0
    assert result['summary']['repeat_rate'] is None
    assert all(g['customer_count']==0 for g in result['segments'])
    assert result['distribution']['frequency']['p75'] is None
    with warehouse.begin() as conn:
        conn.execute(text('UPDATE fact_item SET price_cents=0'))
    result=customer_analysis(warehouse)
    assert result['distribution']['monetary_cents']['p75'] == 0
    assert sum(g['customer_count'] for g in result['segments']) == 2


def test_customer_api_validation_and_no_identifiers(warehouse):
    with TestClient(create_app(warehouse)) as client:
        response=client.get('/api/customers')
        assert response.status_code == 200
        assert 'person-ab' not in response.text
        assert client.get('/api/customers?start=2018-07-31&end=2018-07-01').status_code == 422
        assert client.get('/api/customers?category='+('x'*129)).status_code == 422
        assert client.get('/api/customers?state=XX').json()['summary']['repeat_rate'] is None


def test_missing_warehouse_is_503(tmp_path):
    db=make_engine(f'sqlite:///{tmp_path/"empty.db"}')
    with TestClient(create_app(db)) as client:
        assert client.get('/api/customers').status_code == 503
    db.dispose()
