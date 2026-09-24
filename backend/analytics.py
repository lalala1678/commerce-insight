"""Read-only Olist analytics, with an order-grain scope shared by every metric."""
import calendar
import json
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from sqlalchemy import inspect, text

SCOPE_SQL = (Path(__file__).resolve().parents[1] / 'sql' / 'analytics_scope.sql').read_text(encoding='utf-8')
CORE_START, CORE_END = date(2017, 1, 1), date(2018, 7, 31)


class WarehouseNotReady(Exception):
    """Raised when the real-data ETL has not been run."""


@contextmanager
def read_snapshot(db):
    """Every response sees one import version, even when ETL runs concurrently."""
    with db.connect() as conn:
        if conn.dialect.name == 'mysql':
            conn = conn.execution_options(isolation_level='REPEATABLE READ')
        if conn.dialect.name == 'sqlite':
            # Python sqlite's legacy mode does not BEGIN for SELECT statements.
            conn.exec_driver_sql('BEGIN')
        else:
            conn.begin()
        try:
            yield conn
        finally:
            conn.rollback()


def _meta(conn):
    if not inspect(conn).has_table('etl_run'):
        raise WarehouseNotReady()
    payload = conn.execute(text('SELECT payload FROM etl_run WHERE id = 1')).scalar_one_or_none()
    if not payload:
        raise WarehouseNotReady()
    return json.loads(payload) if isinstance(payload, str) else payload


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(value)


def _range(start, end):
    start, end = _date(start), _date(end)
    if not date(1900, 1, 1) <= start <= end <= date(2099, 12, 31):
        raise ValueError('开始日期不得晚于结束日期，日期须位于 1900–2099 年。')
    if (end - start).days > 1095:
        raise ValueError('单次查询范围不得超过 1096 天。')
    return start, end


def _params(start, end, category='', state=''):
    return {'start_at': start.isoformat() + ' 00:00:00',
            'end_at': (end + timedelta(days=1)).isoformat() + ' 00:00:00',
            'start_day': start.isoformat(), 'end_day': end.isoformat(),
            'category': category, 'state': state}


def _rows(conn, sql, params):
    return [dict(r) for r in conn.execute(text(SCOPE_SQL + '\n' + sql), params).mappings()]


def _kpis(conn, params):
    row = _rows(conn, '''SELECT COUNT(*) AS order_count,
        COALESCE(SUM(scoped_revenue_cents), 0) AS revenue_cents,
        COALESCE(SUM(scoped_item_count), 0) AS item_count,
        COUNT(DISTINCT customer_unique_id) AS customer_count FROM scoped_orders''', params)[0]
    row = {key: int(value) for key, value in row.items()}
    row['average_order_value_cents'] = row['revenue_cents'] / row['order_count'] if row['order_count'] else None
    return row


def _coverage(meta):
    # Conservative analysis window; it does not prove complete platform sampling.
    if not meta.get('observed_start') or not meta.get('observed_end'):
        return None
    start, end = max(CORE_START, _date(meta['observed_start'])), min(CORE_END, _date(meta['observed_end']))
    return (start, end) if start <= end else None


def _default_dates(meta, coverage):
    # Keep defaults usable for smaller imports, even when no recommended window exists.
    if coverage:
        start, end = coverage
    elif meta.get('observed_start') and meta.get('observed_end'):
        start, end = _date(meta['observed_start']), _date(meta['observed_end'])
    else:
        return '2018-07-01', '2018-07-31'
    return max(start, end.replace(day=1)).isoformat(), end.isoformat()


def options(db):
    with read_snapshot(db) as conn:
        meta = _meta(conn)
        cats = conn.execute(text('''SELECT DISTINCT category AS value,
            COALESCE(category_english, category) AS label FROM dim_product ORDER BY label, category''')).mappings()
        result = {key: meta[key] for key in ('data_version', 'currency', 'observed_start', 'observed_end', 'imported_at')}
        coverage = _coverage(meta)
        default_start, default_end = _default_dates(meta, coverage)
        result.update(data_source='olist', default_start=default_start, default_end=default_end,
                      supported_start=coverage[0].isoformat() if coverage else None,
                      supported_end=coverage[1].isoformat() if coverage else None,
                      categories=[dict(row) for row in cats],
                      states=list(conn.execute(text('SELECT DISTINCT state FROM dim_customer ORDER BY state')).scalars()))
        return result


def _comparison(start, end):
    if start.day == 1 and start.month == end.month and start.year == end.year and end.day == calendar.monthrange(end.year, end.month)[1]:
        previous_end = start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        label = f'前一完整自然月（本期 {(end-start).days+1} 天，对比期 {previous_end.day} 天）'
    else:
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - (end - start)
        label = f'前一等长周期（{(end-start).days+1} 天）'
    return previous_start, previous_end, label


def _period(day, grain):
    if grain == 'week':
        return day - timedelta(days=day.weekday())
    return day.replace(day=1) if grain == 'month' else day


def _period_end(day, grain):
    if grain == 'week':
        return day + timedelta(days=6)
    return day.replace(day=calendar.monthrange(day.year, day.month)[1]) if grain == 'month' else day


def _trend(conn, params, start, end, grain, coverage):
    if grain == 'day':
        expression = 'purchase_date'
    elif grain == 'month':
        expression = "CONCAT(SUBSTRING(purchase_date, 1, 7), '-01')" if conn.dialect.name == 'mysql' else "substr(purchase_date, 1, 7) || '-01'"
    elif conn.dialect.name == 'mysql':
        expression = "DATE_FORMAT(DATE_SUB(purchase_date, INTERVAL WEEKDAY(purchase_date) DAY), '%Y-%m-%d')"
    else:
        expression = "date(purchase_date, '-' || ((CAST(strftime('%w', purchase_date) AS INTEGER) + 6) % 7) || ' days')"
    values = _rows(conn, f'''SELECT {expression} AS period,
        SUM(scoped_revenue_cents) AS revenue_cents, COUNT(*) AS order_count
        FROM scoped_orders GROUP BY {expression} ORDER BY period''', params)
    by_period = {str(row['period']): row for row in values}
    periods = []
    cursor = _period(start, grain)
    while cursor <= end:
        bucket_end = _period_end(cursor, grain)
        key = cursor.isoformat()
        complete = bool(coverage and cursor >= start and bucket_end <= end and cursor >= coverage[0] and bucket_end <= coverage[1])
        covered_part = bool(coverage and max(cursor, start) >= coverage[0] and min(bucket_end, end) <= coverage[1])
        actual = by_period.get(key)
        periods.append({'period': key, 'complete': complete,
                        'revenue_cents': int(actual['revenue_cents']) if actual else (0 if covered_part else None),
                        'order_count': int(actual['order_count']) if actual else (0 if covered_part else None)})
        cursor = bucket_end + timedelta(days=1)
    return periods


def _int_columns(rows):
    for row in rows:
        for key in ('revenue_cents', 'order_count', 'item_count'):
            if key in row:
                row[key] = int(row[key])
    return rows


def _rankings(conn, params):
    categories = _int_columns(_rows(conn, '''SELECT category AS name, category_label AS label,
        SUM(price_cents) AS revenue_cents, COUNT(DISTINCT order_id) AS order_count, COUNT(*) AS item_count
        FROM scoped_items GROUP BY category, category_label ORDER BY revenue_cents DESC, name''', params))
    regions = _int_columns(_rows(conn, '''SELECT state AS name, SUM(scoped_revenue_cents) AS revenue_cents,
        COUNT(*) AS order_count, SUM(scoped_item_count) AS item_count
        FROM scoped_orders GROUP BY state ORDER BY revenue_cents DESC, name''', params))
    product_sql = '''SELECT product_id, category, category_label AS label, SUM(price_cents) AS revenue_cents,
        COUNT(DISTINCT order_id) AS order_count, COUNT(*) AS item_count
        FROM scoped_items GROUP BY product_id, category, category_label'''
    products = _int_columns(_rows(conn, product_sql + ' ORDER BY revenue_cents DESC, product_id LIMIT 20', params))
    low_volume = _int_columns(_rows(conn, product_sql + ' ORDER BY item_count, revenue_cents, product_id LIMIT 20', params))
    return categories, regions, products, low_volume


def _fulfillment(conn, params):
    row = _rows(conn, '''SELECT COUNT(is_late) AS eligible_orders,
        COALESCE(SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END), 0) AS late_orders,
        COUNT(delivery_seconds) AS delivery_sample_count, AVG(delivery_seconds) AS average_seconds,
        COUNT(review_score) AS reviewed_orders, AVG(review_score) AS average_review_score
        FROM scoped_orders''', params)[0]
    for key in ('eligible_orders', 'late_orders', 'delivery_sample_count', 'reviewed_orders'):
        row[key] = int(row[key])
    row['late_rate'] = row['late_orders'] / row['eligible_orders'] if row['eligible_orders'] else None
    seconds = row.pop('average_seconds')
    row['average_delivery_days'] = float(seconds) / 86400 if seconds is not None else None
    row['average_review_score'] = float(row['average_review_score']) if row['average_review_score'] is not None else None
    samples = _rows(conn, 'SELECT delivery_seconds FROM scoped_orders WHERE delivery_seconds IS NOT NULL', params)
    row['median_delivery_days'] = median(float(r['delivery_seconds']) for r in samples) / 86400 if samples else None
    group_rows = _rows(conn, '''SELECT is_late, COUNT(*) AS order_count, COUNT(review_score) AS reviewed_orders,
        AVG(review_score) AS average_review_score FROM scoped_orders GROUP BY is_late''', params)
    groups = {r['is_late']: r for r in group_rows}
    row['groups'] = []
    for key, label in ((0, '准时交付'), (1, '延迟交付'), (None, '日期不足')):
        group = groups.get(key, {'order_count': 0, 'reviewed_orders': 0, 'average_review_score': None})
        row['groups'].append({'label': label, 'order_count': int(group['order_count']),
            'reviewed_orders': int(group['reviewed_orders']),
            'average_review_score': float(group['average_review_score']) if group['average_review_score'] is not None else None})
    scores = _rows(conn, '''SELECT review_score AS score, COUNT(*) AS order_count FROM scoped_orders
        WHERE review_score IS NOT NULL GROUP BY review_score ORDER BY review_score''', params)
    counts = {int(r['score']): int(r['order_count']) for r in scores}
    row['scores'] = [{'score': score, 'order_count': counts.get(score, 0)} for score in range(1, 6)]
    return row


def dashboard(db, start='2018-07-01', end='2018-07-31', category='', state='', grain='day'):
    start, end = _range(start, end)
    if grain not in ('day', 'week', 'month'):
        raise ValueError('粒度必须为 day、week 或 month。')
    params = _params(start, end, category, state)
    with read_snapshot(db) as conn:
        dataset = _meta(conn)
        coverage = _coverage(dataset)
        previous_start, previous_end, comparison_label = _comparison(start, end)
        comparable = bool(coverage and start >= coverage[0] and end <= coverage[1] and previous_start >= coverage[0] and previous_end <= coverage[1])
        warnings = ['按下单日期统计最终已交付订单；金额不含运费，币种 BRL。',
                    '推荐观察窗用于减轻数据边界影响，不代表平台交易完整覆盖。']
        if not dataset.get('observed_start') or not dataset.get('observed_end'):
            warnings.append('当前数据没有已交付订单，无法建立观察覆盖范围；空记录不表示已证实的零销售。')
        elif not coverage:
            warnings.append('已交付订单日期与推荐观察窗没有交集；展示已有记录，完整性与环比不可判断。')
        elif start < coverage[0] or end > coverage[1]:
            warnings.append('所选日期包含稀疏或尾部时段；缺少记录不等于已证实的零销售，环比不可计算。')
        if not comparable:
            warnings.append('对比周期超出推荐观察范围，或本期覆盖不足；不计算环比。')
        if category:
            warnings.append('金额和件数只含命中品类；订单去重，支付与履约仍为这些订单的整单信息。')
        categories, regions, products, low_volume = _rankings(conn, params)
        return {'meta': {'data_source': 'olist', 'data_version': dataset['data_version'], 'currency': dataset['currency'],
            'start': start.isoformat(), 'end': end.isoformat(), 'category': category, 'state': state, 'grain': grain,
            'warnings': warnings, 'comparison_start': previous_start.isoformat(), 'comparison_end': previous_end.isoformat(),
            'comparison_label': comparison_label}, 'kpis': _kpis(conn, params),
            'previous': _kpis(conn, _params(previous_start, previous_end, category, state)) if comparable else None,
            'trend': _trend(conn, params, start, end, grain, coverage),
            'categories': categories, 'regions': regions, 'products': products, 'low_volume_products': low_volume,
            'fulfillment': _fulfillment(conn, params)}


ORDER_COLUMNS = '''order_id, purchase_date, state, scoped_item_count AS item_count,
    scoped_revenue_cents AS revenue_cents, payment_cents, review_score, is_late, quality_flags'''


def _order_row(row):
    for key in ('item_count', 'revenue_cents', 'payment_cents', 'review_score', 'is_late', 'total_order_revenue_cents'):
        if key in row and row[key] is not None:
            row[key] = int(row[key])
    row['quality_flags'] = json.loads(row['quality_flags']) if isinstance(row['quality_flags'], str) else row['quality_flags']
    return row


def orders(db, start='2018-07-01', end='2018-07-31', category='', state='', page=1, page_size=20):
    start, end = _range(start, end)
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError('页码须大于等于 1，每页须为 1–100 条。')
    params = _params(start, end, category, state)
    params.update(limit=page_size, offset=(page-1) * page_size)
    with read_snapshot(db) as conn:
        _meta(conn)
        total = _rows(conn, 'SELECT COUNT(*) AS total FROM scoped_orders', params)[0]['total']
        rows = _rows(conn, f'''SELECT {ORDER_COLUMNS} FROM scoped_orders
            ORDER BY purchase_date DESC, order_id LIMIT :limit OFFSET :offset''', params)
        return {'rows': [_order_row(r) for r in rows], 'total': int(total), 'page': page, 'page_size': page_size}


def order_details(db, order_id, category=''):
    params = _params(date(1900, 1, 1), date(2099, 12, 31), category)
    params['order_id'] = order_id
    with read_snapshot(db) as conn:
        _meta(conn)
        rows = _rows(conn, f'''SELECT {ORDER_COLUMNS}, revenue_cents AS total_order_revenue_cents,
            purchase_at, delivered_at, estimated_at, payment_count, review_count
            FROM scoped_orders WHERE order_id = :order_id''', params)
        if not rows:
            return None
        items = _rows(conn, '''SELECT item_id, product_id, seller_id, category,
            category_label AS label, price_cents, freight_cents
            FROM scoped_items WHERE order_id = :order_id ORDER BY item_id''', params)
        for item in items:
            for key in ('item_id', 'price_cents', 'freight_cents'):
                item[key] = int(item[key])
        return {'order': _order_row(rows[0]), 'items': items,
                'scope_note': '金额及商品列表仅包含所选品类；支付金额、评分与交付信息为整单口径。' if category else
                              '商品金额不含运费；支付金额为整单各支付记录之和，可能与商品加运费不同。'}
