"""Hand-countable Olist-shaped inputs exercise money, grain and atomicity."""
import csv
import json
from pathlib import Path

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from backend import etl
from backend.db import make_engine
from backend.etl import FILES, import_data
from backend.metrics import overview
from backend.seed import seed
from backend.warehouse import fact_order, warehouse_metadata


def create_olist_fixture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    datasets = {
        'orders': (
            ['order_id', 'customer_id', 'order_status', 'order_purchase_timestamp', 'order_approved_at',
             'order_delivered_carrier_date', 'order_delivered_customer_date', 'order_estimated_delivery_date'],
            [
                ['order-a', 'customer-a', 'delivered', '2018-07-01 12:00:00', '', '2018-06-30 12:00:00', '2018-07-03 23:30:00', '2018-07-03 00:00:00'],
                ['order-b', 'customer-b', 'delivered', '2018-07-02 12:00:00', '', '2018-07-06 12:00:00', '2018-07-05 12:00:00', '2018-07-04 00:00:00'],
                ['order-c', 'customer-c', 'delivered', '2018-07-03 12:00:00', '', '', '', '2018-07-04 00:00:00'],
                ['order-d', 'customer-d', 'canceled', '2018-07-04 12:00:00', '', '', '', ''],
                ['order-e', 'customer-e', 'processing', '2018-07-05 12:00:00', '', '', '', ''],
            ]),
        'items': (
            ['order_id', 'order_item_id', 'product_id', 'seller_id', 'shipping_limit_date', 'price', 'freight_value'],
            [
                ['order-a', '1', 'product-a', 'seller-a', '2018-07-03 12:00:00', '100.00', '10.00'],
                ['order-a', '2', 'product-b', 'seller-b', '2018-07-03 12:00:00', '50.00', '5.00'],
                ['order-b', '1', 'product-a', 'seller-a', '2018-07-03 12:00:00', '200.00', '20.00'],
                ['order-c', '1', 'product-c', 'seller-a', '2018-07-03 12:00:00', '100.00', '10.00'],
                ['order-d', '1', 'product-a', 'seller-a', '2018-07-03 12:00:00', '999.00', '0.00'],
            ]),
        'customers': (
            ['customer_id', 'customer_unique_id', 'customer_state'],
            [['customer-a', 'person-ab', 'SP'], ['customer-b', 'person-ab', 'SP'],
             ['customer-c', 'person-c', 'RJ'], ['customer-d', 'person-d', 'MG'], ['customer-e', 'person-e', 'SP']]),
        'products': (
            ['product_id', 'product_category_name'],
            [['product-a', 'casa'], ['product-b', ''], ['product-c', 'sem_traducao']]),
        'sellers': (['seller_id', 'seller_state'], [['seller-a', 'SP'], ['seller-b', 'RJ']]),
        'payments': (
            ['order_id', 'payment_sequential', 'payment_value'],
            [['order-a', '1', '100.00'], ['order-a', '2', '65.00'], ['order-c', '1', '110.00'], ['order-d', '1', '999.00']]),
        'reviews': (
            ['review_id', 'order_id', 'review_score', 'review_creation_date', 'review_answer_timestamp'],
            [
                ['review-shared', 'order-a', '1', '2018-07-03 00:00:00', '2018-07-05 00:00:00'],
                ['review-z', 'order-a', '2', '2018-07-04 00:00:00', '2018-07-05 00:00:00'],
                ['review-zz', 'order-a', '3', '2018-07-04 00:00:00', '2018-07-05 00:00:00'],
                ['review-zz', 'order-a', '5', '2018-07-04 00:00:00', '2018-07-05 00:00:00'],
                ['review-shared', 'order-b', '4', '2018-07-04 00:00:00', '2018-07-05 00:00:00'],
            ]),
        'translation': (['product_category_name', 'product_category_name_english'], [['casa', 'home']]),
    }
    for name, (headers, rows) in datasets.items():
        with (directory / FILES[name]).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
    return directory


@pytest.fixture
def source(tmp_path):
    return create_olist_fixture(tmp_path / 'raw')


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "warehouse.db"}')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    yield engine
    engine.dispose()


def test_real_import_reconciles_and_does_not_touch_demo(db, source):
    seed(db)
    result = import_data(source, db)
    assert result['raw_order_count'] == 5
    assert result['delivered_order_count'] == 3
    assert result['delivered_revenue_cents'] == 45000
    assert result['observed_start'] == '2018-07-01'
    assert result['observed_end'] == '2018-07-03'
    assert result['reconciliation']['passed'] is True
    assert result['reconciliation']['all_item_revenue_cents'] == 144900
    assert result['review_rows_collapsed'] == 3
    assert overview(db)['revenue_cents'] == 45000
    with db.connect() as conn:
        rows = {r['order_id']: r for r in conn.execute(select(fact_order)).mappings()}
        # Two item rows × two payments × four reviews must not multiply revenue.
        assert rows['order-a']['revenue_cents'] == 15000
        assert rows['order-a']['payment_cents'] == 16500
        assert rows['order-a']['payment_count'] == 2
        assert rows['order-a']['review_count'] == 4
        assert rows['order-a']['review_score'] == 5
        assert rows['order-b']['review_score'] == 4
        assert conn.execute(text('SELECT SUM(revenue_cents) FROM agg_day')).scalar_one() == 45000
        assert conn.execute(text('SELECT COUNT(*) FROM fact_item')).scalar_one() == 5


def test_missing_values_and_date_anomalies_keep_sales(db, source):
    import_data(source, db)
    with db.connect() as conn:
        rows = {r['order_id']: r for r in conn.execute(select(fact_order)).mappings()}
        assert rows['order-b']['payment_cents'] is None
        assert rows['order-b']['payment_count'] == 0
        assert rows['order-c']['delivery_seconds'] is None
        assert rows['order-c']['is_late'] is None
        assert rows['order-c']['review_score'] is None
        assert rows['order-c']['revenue_cents'] == 10000
        assert rows['order-a']['is_late'] == 0  # Same promised natural date, even at 23:30.
        assert rows['order-b']['is_late'] == 1
        assert rows['order-a']['delivery_seconds'] == 214200
        assert rows['order-b']['delivery_seconds'] == 259200
        assert 'carrier_before_purchase' in json.loads(rows['order-a']['quality_flags'])
        assert 'delivery_before_carrier' in json.loads(rows['order-b']['quality_flags'])
        categories = conn.execute(text('SELECT category, category_english FROM dim_product ORDER BY product_id')).all()
        assert categories == [('casa', 'home'), ('unknown', None), ('sem_traducao', None)]


def test_repeat_import_is_identical_and_keeps_input_hashes(db, source):
    before = {file.name: file.read_bytes() for file in source.iterdir()}
    first = import_data(source, db)
    with db.connect() as conn:
        baseline = conn.execute(select(fact_order).order_by(fact_order.c.order_id)).all()
    second = import_data(source, db)
    assert first['data_version'] == second['data_version']
    assert first['file_hashes'] == second['file_hashes']
    assert first['row_counts'] == second['row_counts']
    with db.connect() as conn:
        assert conn.execute(select(fact_order).order_by(fact_order.c.order_id)).all() == baseline
        assert conn.execute(text('SELECT COUNT(*) FROM etl_run')).scalar_one() == 1
    assert {file.name: file.read_bytes() for file in source.iterdir()} == before


@pytest.mark.parametrize('name,old,new', [
    ('items', '100.00,10.00', '-1.00,10.00'),
    ('items', '100.00,10.00', '1.001,10.00'),
    ('items', '100.00,10.00', 'NaN,10.00'),
    ('items', 'product-a,seller-a', 'missing-product,seller-a'),
    ('items', 'order-a,1', 'order-a,0'),
    ('orders', '2018-07-01 12:00:00', 'not-a-date'),
    ('orders', 'order-a,customer-a', 'order-a,missing-customer'),
    ('customers', 'customer-a,person-ab', 'customer-a,'),
    ('reviews', 'order-a,1,', 'order-a,9,'),
])
def test_invalid_source_cannot_replace_existing_warehouse(db, source, name, old, new):
    import_data(source, db)
    path = source / FILES[name]
    original = path.read_text(encoding='utf-8')
    assert old in original
    path.write_text(original.replace(old, new, 1), encoding='utf-8')
    with pytest.raises(ValueError):
        import_data(source, db)
    with db.connect() as conn:
        assert conn.execute(text('SELECT SUM(revenue_cents) FROM agg_day')).scalar_one() == 45000
        assert conn.execute(text('SELECT COUNT(*) FROM fact_order')).scalar_one() == 5


def test_duplicate_item_key_rejected(db, source):
    import_data(source, db)
    path = source / FILES['items']
    with path.open('a', encoding='utf-8') as stream:
        stream.write('order-a,1,product-a,seller-a,2018-07-03 12:00:00,100.00,10.00\n')
    with pytest.raises(ValueError, match='duplicate key'):
        import_data(source, db)


def test_reconciliation_error_inside_transaction_rolls_back_every_table(db, source, monkeypatch):
    import_data(source, db)
    with db.connect() as conn:
        before = {table.name: conn.execute(select(table)).all() for table in warehouse_metadata.sorted_tables}
    path = source / FILES['items']
    path.write_text(path.read_text().replace('100.00,10.00', '123.45,10.00', 1))
    def fail_after_inserts(conn, payload):
        assert conn.execute(text('SELECT SUM(revenue_cents) FROM agg_day')).scalar_one() == 47345
        raise ValueError('Injected reconciliation failure')
    monkeypatch.setattr(etl, '_assert_reconciled', fail_after_inserts)
    with pytest.raises(ValueError, match='Injected'):
        import_data(source, db)
    with db.connect() as conn:
        after = {table.name: conn.execute(select(table)).all() for table in warehouse_metadata.sorted_tables}
    assert after == before


def test_changed_raw_file_during_import_rolls_back(db, source, monkeypatch):
    baseline = import_data(source, db)
    original_check = etl._assert_reconciled
    def change_after_inserts(conn, payload):
        original_check(conn, payload)
        path = source / FILES['items']
        path.write_text(path.read_text().replace('100.00,10.00', '101.00,10.00', 1))
    monkeypatch.setattr(etl, '_assert_reconciled', change_after_inserts)
    with pytest.raises(ValueError, match='changed during ETL'):
        import_data(source, db)
    with db.connect() as conn:
        assert conn.execute(text('SELECT SUM(revenue_cents) FROM agg_day')).scalar_one() == 45000
        assert json.loads(conn.execute(text('SELECT payload FROM etl_run')).scalar_one()) == baseline


def test_schema_uses_mysql_transactional_tables_and_bigint_money():
    schema = '\n'.join(str(CreateTable(table).compile(dialect=mysql.dialect())) for table in warehouse_metadata.sorted_tables)
    assert schema.count('ENGINE=InnoDB') == 7
    assert 'revenue_cents BIGINT' in schema
    assert 'payment_cents BIGINT' in schema
    assert 'FOREIGN KEY(customer_id)' in schema
