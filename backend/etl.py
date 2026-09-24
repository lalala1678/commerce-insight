"""Validate Olist CSVs, then atomically refresh the real-data warehouse.

Run from the repository root: python -m backend.etl data/raw
No raw text reviews, customer names or precise geolocation enter serving tables.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, select

from .db import make_engine
from .warehouse import (agg_day, dim_customer, dim_product, dim_seller, etl_run,
                        fact_item, fact_order, warehouse_metadata)

FILES = {
    'orders': 'olist_orders_dataset.csv',
    'items': 'olist_order_items_dataset.csv',
    'customers': 'olist_customers_dataset.csv',
    'products': 'olist_products_dataset.csv',
    'sellers': 'olist_sellers_dataset.csv',
    'payments': 'olist_order_payments_dataset.csv',
    'reviews': 'olist_order_reviews_dataset.csv',
    'translation': 'product_category_name_translation.csv',
}
REQUIRED = {
    'orders': ['order_id', 'customer_id', 'order_status', 'order_purchase_timestamp',
               'order_delivered_carrier_date', 'order_delivered_customer_date', 'order_estimated_delivery_date'],
    'items': ['order_id', 'order_item_id', 'product_id', 'seller_id', 'price', 'freight_value'],
    'customers': ['customer_id', 'customer_unique_id', 'customer_state'],
    'products': ['product_id', 'product_category_name'],
    'sellers': ['seller_id', 'seller_state'],
    'payments': ['order_id', 'payment_sequential', 'payment_value'],
    'reviews': ['review_id', 'order_id', 'review_score', 'review_creation_date', 'review_answer_timestamp'],
    'translation': ['product_category_name', 'product_category_name_english'],
}
STATES = {'delivered', 'shipped', 'canceled', 'unavailable', 'invoiced', 'processing', 'created', 'approved'}
MAX_CENTS = 2**63 - 1


def _digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _read(directory):
    frames, hashes = {}, {}
    csv.field_size_limit(1_000_000)
    for name, filename in FILES.items():
        path = directory / filename
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError(f'{filename}: missing input or larger than 64 MiB')
        hashes[filename] = _digest(path)
        # Pandas can quietly pad short rows; verify rectangular input first.
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, [])
            if len(header) != len(set(header)) or not set(REQUIRED[name]).issubset(header):
                raise ValueError(f'{filename}: missing or duplicate columns')
            count = 0
            for row in reader:
                count += 1
                if len(row) != len(header) or count > 1_200_000:
                    raise ValueError(f'{filename}: malformed row or row bound exceeded')
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        if len(frame) != count:
            raise ValueError(f'{filename}: inconsistent CSV row count')
        for column in REQUIRED[name]:
            frame[column] = frame[column].str.strip()
        frames[name] = frame
    return frames, hashes


def _unique(frame, columns, name):
    if frame[columns].eq('').any().any() or frame.duplicated(columns).any():
        raise ValueError(f'{name}: missing or duplicate key ({", ".join(columns)})')


def _strings(frame, column, limit, required=True):
    values = frame[column]
    if values.str.len().gt(limit).any() or (required and values.eq('').any()):
        raise ValueError(f'{column}: missing or too long')


def _money(value):
    try:
        amount = Decimal(value) * 100
        if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value() or amount > MAX_CENTS:
            raise ValueError('Money must be nonnegative, at most two decimals and fit BIGINT')
        return int(amount)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Invalid monetary value') from exc


def _positive_ids(frame, column):
    if not frame[column].str.fullmatch(r'[1-9][0-9]*').all():
        raise ValueError(f'{column}: must be a positive integer without leading zeroes')
    values = frame[column].map(int)
    if values.gt(2**31 - 1).any():
        raise ValueError(f'{column}: outside INTEGER range')
    frame[column] = values


def _dates(frame, column, required=False):
    values = frame[column]
    nonempty = values.ne('')
    if required and not nonempty.all():
        raise ValueError(f'{column}: missing required date')
    if not values[nonempty].str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}').all():
        raise ValueError(f'{column}: use YYYY-MM-DD HH:MM:SS')
    parsed = pd.to_datetime(values.where(nonempty), format='%Y-%m-%d %H:%M:%S', errors='coerce')
    if (nonempty & parsed.isna()).any():
        raise ValueError(f'{column}: malformed date')
    return parsed


def _safe_sum(values):
    total = sum(int(value) for value in values)
    if total > MAX_CENTS:
        raise ValueError('Aggregated monetary value exceeds BIGINT')
    return total


def _prepare(directory):
    raw, hashes = _read(directory)
    orders, items, customers, products, sellers, payments, reviews, translation = [raw[key] for key in FILES]
    for frame, keys, name in [
        (orders, ['order_id'], 'orders'), (customers, ['customer_id'], 'customers'),
        (products, ['product_id'], 'products'), (sellers, ['seller_id'], 'sellers'),
        (translation, ['product_category_name'], 'translation'),
    ]:
        _unique(frame, keys, name)
    _positive_ids(items, 'order_item_id')
    _positive_ids(payments, 'payment_sequential')
    _unique(items, ['order_id', 'order_item_id'], 'items')
    _unique(payments, ['order_id', 'payment_sequential'], 'payments')
    # review_id is deliberately NOT a primary key: multiple rows can be valid.
    for frame in [orders, items, customers, products, sellers, payments, reviews]:
        for column in frame.columns.intersection(['order_id', 'customer_id', 'customer_unique_id', 'product_id', 'seller_id', 'review_id']):
            _strings(frame, column, 64)
    for frame, column in [(customers, 'customer_state'), (sellers, 'seller_state')]:
        _strings(frame, column, 8, required=False)
    for frame, column in [(products, 'product_category_name'), (translation, 'product_category_name'),
                          (translation, 'product_category_name_english')]:
        _strings(frame, column, 128, required=False)
    for child, field, parent, parentfield in [
        (orders, 'customer_id', customers, 'customer_id'), (items, 'order_id', orders, 'order_id'),
        (items, 'product_id', products, 'product_id'), (items, 'seller_id', sellers, 'seller_id'),
        (payments, 'order_id', orders, 'order_id'), (reviews, 'order_id', orders, 'order_id'),
    ]:
        if not child[field].isin(parent[parentfield]).all():
            raise ValueError(f'Orphan foreign key: {field}')
    if not orders.order_status.isin(STATES).all():
        raise ValueError('Unsupported order status')
    if not orders.loc[orders.order_status.eq('delivered'), 'order_id'].isin(items.order_id).all():
        raise ValueError('Delivered orders must have item details')
    if not reviews.review_score.str.fullmatch(r'[1-5]').all():
        raise ValueError('Review scores must be integers from 1 to 5')

    dates = {}
    for column in ['order_purchase_timestamp', 'order_delivered_carrier_date',
                   'order_delivered_customer_date', 'order_estimated_delivery_date']:
        dates[column] = _dates(orders, column, required=column == 'order_purchase_timestamp')
    if 'order_approved_at' in orders:
        _dates(orders, 'order_approved_at')
    if 'shipping_limit_date' in items:
        _dates(items, 'shipping_limit_date')
    for column in ['review_creation_date', 'review_answer_timestamp']:
        _dates(reviews, column)

    items['price_cents'] = items.price.map(_money)
    items['freight_cents'] = items.freight_value.map(_money)
    payments['payment_cents'] = payments.payment_value.map(_money)
    totals = items.groupby('order_id', sort=False).agg(
        revenue_cents=('price_cents', _safe_sum), freight_cents=('freight_cents', _safe_sum), item_count=('order_item_id', 'size'))
    payment_totals = payments.groupby('order_id', sort=False).agg(
        payment_cents=('payment_cents', _safe_sum), payment_count=('payment_sequential', 'size'))
    reviews['_input_row'] = range(len(reviews))
    review_counts = reviews.groupby('order_id').size().to_dict()
    latest_reviews = reviews.sort_values(
        ['review_answer_timestamp', 'review_creation_date', 'review_id', '_input_row'], kind='stable'
    ).drop_duplicates('order_id', keep='last').set_index('order_id').review_score.map(int).to_dict()
    totals = totals.to_dict('index')
    payment_totals = payment_totals.to_dict('index')
    translations = translation.set_index('product_category_name').product_category_name_english.to_dict()

    customer_rows = [{'customer_id': r.customer_id, 'customer_unique_id': r.customer_unique_id,
                      'state': r.customer_state or 'unknown'} for r in customers.itertuples()]
    product_rows = [{'product_id': r.product_id, 'category': r.product_category_name or 'unknown',
                     'category_english': translations.get(r.product_category_name) or None} for r in products.itertuples()]
    seller_rows = [{'seller_id': r.seller_id, 'state': r.seller_state or 'unknown'} for r in sellers.itertuples()]
    item_rows = items[['order_id', 'order_item_id', 'product_id', 'seller_id', 'price_cents', 'freight_cents']].rename(
        columns={'order_item_id': 'item_id'}).to_dict('records')
    order_rows, day_totals, quality = [], defaultdict(lambda: {'revenue_cents': 0, 'order_count': 0, 'item_count': 0}), Counter()
    for r in orders.itertuples():
        index = r.Index
        purchase = dates['order_purchase_timestamp'].iloc[index]
        carrier = dates['order_delivered_carrier_date'].iloc[index]
        delivery = dates['order_delivered_customer_date'].iloc[index]
        estimated = dates['order_estimated_delivery_date'].iloc[index]
        flags = []
        if pd.notna(carrier) and carrier < purchase:
            flags.append('carrier_before_purchase')
        if pd.notna(delivery) and pd.notna(carrier) and delivery < carrier:
            flags.append('delivery_before_carrier')
        if pd.notna(delivery) and delivery < purchase:
            flags.append('delivery_before_purchase')
        delivered = r.order_status == 'delivered'
        if delivered and pd.isna(delivery):
            flags.append('delivered_missing_delivery_date')
        if delivered and pd.isna(estimated):
            flags.append('delivered_missing_estimated_date')
        item_total = totals.get(r.order_id, {'revenue_cents': 0, 'freight_cents': 0, 'item_count': 0})
        payment_total = payment_totals.get(r.order_id, {'payment_cents': None, 'payment_count': 0})
        if not item_total['item_count']:
            flags.append('missing_items')
        if not payment_total['payment_count']:
            flags.append('missing_payment')
        elif item_total['item_count'] and payment_total['payment_cents'] != item_total['revenue_cents'] + item_total['freight_cents']:
            flags.append('payment_total_mismatch')
        review_count = int(review_counts.get(r.order_id, 0))
        if review_count == 0:
            flags.append('missing_review')
        elif review_count > 1:
            flags.append('multiple_reviews')
        delivery_seconds = None
        if delivered and pd.notna(delivery) and delivery >= purchase:
            delivery_seconds = int((delivery - purchase).total_seconds())
            if delivery_seconds > 2**31 - 1:
                raise ValueError('Delivery duration exceeds INTEGER range')
        late = None
        if delivered and pd.notna(delivery) and pd.notna(estimated) and delivery >= purchase:
            late = int(delivery.date() > estimated.date())
        row = {'order_id': r.order_id, 'customer_id': r.customer_id, 'purchase_at': r.order_purchase_timestamp,
               'purchase_date': r.order_purchase_timestamp[:10], 'status': r.order_status,
               'carrier_at': r.order_delivered_carrier_date or None,
               'delivered_at': r.order_delivered_customer_date or None,
               'estimated_at': r.order_estimated_delivery_date or None,
               **{k: int(v) for k, v in item_total.items()},
               'payment_cents': None if payment_total['payment_cents'] is None else int(payment_total['payment_cents']),
               'payment_count': int(payment_total['payment_count']),
               'review_score': latest_reviews.get(r.order_id), 'review_count': review_count,
               'delivery_seconds': delivery_seconds, 'is_late': late,
               'quality_flags': json.dumps(flags, ensure_ascii=False)}
        order_rows.append(row)
        quality.update(flags)
        if delivered:
            day = day_totals[row['purchase_date']]
            day['revenue_cents'] += row['revenue_cents']
            day['order_count'] += 1
            day['item_count'] += row['item_count']
    day_rows = [{'day': day, **values} for day, values in sorted(day_totals.items())]
    delivered_ids = set(orders.loc[orders.order_status.eq('delivered'), 'order_id'])
    raw_revenue = _safe_sum(items.price_cents)
    raw_freight = _safe_sum(items.freight_cents)
    delivered_revenue = _safe_sum(items.loc[items.order_id.isin(delivered_ids), 'price_cents'])
    if _safe_sum(r['revenue_cents'] for r in order_rows) != raw_revenue:
        raise ValueError('Prepared order totals fail raw item reconciliation')
    payload = {
        'etl_schema_version': 1,
        'data_version': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16],
        'source': 'Olist', 'currency': 'BRL',
        'raw_order_count': len(orders), 'delivered_order_count': len(delivered_ids),
        'delivered_revenue_cents': delivered_revenue,
        'observed_start': min(day_totals) if day_totals else None,
        'observed_end': max(day_totals) if day_totals else None,
        'imported_at': datetime.now(timezone.utc).isoformat(),
        'row_counts': {name: len(frame) for name, frame in raw.items()},
        'quality_counts': dict(sorted(quality.items())),
        'review_rows_collapsed': len(reviews) - len(latest_reviews),
        'file_hashes': hashes,
        'reconciliation': {'passed': True, 'all_item_revenue_cents': raw_revenue,
                           'all_item_freight_cents': raw_freight,
                           'all_payment_cents': _safe_sum(payments.payment_cents)},
    }
    payload['quality_counts']['products_missing_category'] = int(products.product_category_name.eq('').sum())
    payload['quality_counts']['products_missing_translation'] = sum(
        bool(r['category'] != 'unknown' and r['category_english'] is None) for r in product_rows)
    rows = [(dim_customer, customer_rows), (dim_product, product_rows), (dim_seller, seller_rows),
            (fact_order, order_rows), (fact_item, item_rows), (agg_day, day_rows)]
    return rows, payload


def _assert_reconciled(conn, payload):
    def scalar(statement):
        return int(conn.execute(statement).scalar_one() or 0)
    checks = {
        'order count': (scalar(select(func.count()).select_from(fact_order)), payload['raw_order_count']),
        'item count': (scalar(select(func.count()).select_from(fact_item)), payload['row_counts']['items']),
        'item revenue': (scalar(select(func.sum(fact_item.c.price_cents))), payload['reconciliation']['all_item_revenue_cents']),
        'order revenue': (scalar(select(func.sum(fact_order.c.revenue_cents))), payload['reconciliation']['all_item_revenue_cents']),
        'item freight': (scalar(select(func.sum(fact_item.c.freight_cents))), payload['reconciliation']['all_item_freight_cents']),
        'order freight': (scalar(select(func.sum(fact_order.c.freight_cents))), payload['reconciliation']['all_item_freight_cents']),
        'order payments': (scalar(select(func.sum(fact_order.c.payment_cents))), payload['reconciliation']['all_payment_cents']),
        'delivered orders': (scalar(select(func.count()).select_from(fact_order).where(fact_order.c.status == 'delivered')), payload['delivered_order_count']),
        'delivered revenue': (scalar(select(func.sum(fact_order.c.revenue_cents)).where(fact_order.c.status == 'delivered')), payload['delivered_revenue_cents']),
        'daily orders': (scalar(select(func.sum(agg_day.c.order_count))), payload['delivered_order_count']),
        'daily revenue': (scalar(select(func.sum(agg_day.c.revenue_cents))), payload['delivered_revenue_cents']),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise ValueError(f'Warehouse reconciliation failed: {label}')


def import_data(directory, db=None):
    directory = Path(directory).resolve()
    rows, payload = _prepare(directory)
    engine = db if db is not None else make_engine()
    try:
        # DDL is outside the transaction: MySQL CREATE TABLE implicitly commits.
        warehouse_metadata.create_all(engine)
        with engine.begin() as conn:
            for table in [etl_run, agg_day, fact_item, fact_order, dim_seller, dim_product, dim_customer]:
                conn.execute(delete(table))
            for table, records in rows:
                for offset in range(0, len(records), 2000):
                    conn.execute(table.insert(), records[offset:offset + 2000])
            _assert_reconciled(conn, payload)
            for filename, fingerprint in payload['file_hashes'].items():
                if _digest(directory / filename) != fingerprint:
                    raise ValueError('Source CSV changed during ETL; transaction rolled back')
            conn.execute(etl_run.insert(), {'id': 1, 'payload': json.dumps(payload, ensure_ascii=False)})
        return payload
    finally:
        if db is None:
            engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', default='data/raw')
    args = parser.parse_args()
    print(json.dumps(import_data(args.directory), ensure_ascii=False, indent=2))
