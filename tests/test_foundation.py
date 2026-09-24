import shutil
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from backend.app import create_app
from backend.db import ROOT, items, make_engine, orders
from backend.metrics import overview
from backend.seed import seed

@pytest.fixture
def db(tmp_path):
    database=make_engine(f'sqlite:///{tmp_path / "test.db"}')
    seed(database)
    yield database
    database.dispose()

def test_hand_calculated_metrics(db):
    result=overview(db)
    assert result['order_count']==3
    assert result['revenue_cents']==45000
    assert result['average_order_value_cents']==15000
    assert result['data_source']=='synthetic'

def test_import_is_repeatable(db):
    seed(db);seed(db)
    with db.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM demo_orders')).scalar_one()==5
        assert conn.execute(text('SELECT COUNT(*) FROM demo_items')).scalar_one()==6
    assert overview(db)['revenue_cents']==45000

def test_empty_orders_are_not_divided_by_zero(db):
    with db.begin() as conn:
        conn.execute(delete(items));conn.execute(delete(orders))
    assert overview(db)['order_count']==0
    assert overview(db)['revenue_cents']==0
    assert overview(db)['average_order_value_cents'] is None

@pytest.mark.parametrize('change', ['duplicate','orphan','negative','missing','invalid_date'])
def test_bad_import_preserves_previous_data(db,tmp_path,change):
    target=tmp_path/'sample'
    shutil.copytree(ROOT/'sample_data',target)
    path=target/'items.csv'
    contents=path.read_text()
    if change=='duplicate':contents+='demo-001,1,100.00\n'
    if change=='orphan':contents=contents.replace('demo-001','unknown')
    if change=='negative':contents=contents.replace('100.00','-1.00')
    if change=='missing':contents=contents.replace('100.00','')
    path.write_text(contents)
    if change=='invalid_date':
        path=target/'orders.csv';path.write_text(path.read_text().replace('2018-07-01','not-a-date'))
    with pytest.raises(ValueError):seed(db,target)
    assert overview(db)['revenue_cents']==45000

def test_api_contract(db):
    with TestClient(create_app(db)) as client:
        assert client.get('/api/health').json()['status']=='ok'
        response=client.get('/api/overview')
        assert response.status_code==200
        assert response.json()==overview(db)
        assert client.get('/openapi.json').status_code==200

def test_uninitialized_database_explains_next_step(tmp_path):
    db=make_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with TestClient(create_app(db)) as client:
        response=client.get('/api/overview')
        assert response.status_code==503
        assert 'backend.seed' in response.json()['detail']
    db.dispose()
