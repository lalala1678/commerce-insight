"""Export bounded, aggregate-only Olist snapshots for the GitHub Pages demo.

Run after the real ETL: python -m scripts.export_static
DATABASE_URL may point to the same MySQL database used by FastAPI; otherwise the
local SQLite warehouse is used. The exporter never copies raw CSVs or order rows.
"""

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from backend import analytics, customers, reports
from backend.db import make_engine


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'frontend' / 'public' / 'static-data'
GRAINS = ('day', 'week', 'month')
PRESETS = (
    dict(id='july-2018', label='2018 年 7 月 · 全部品类与地区', start='2018-07-01', end='2018-07-31', category='', state=''),
    dict(id='june-2018', label='2018 年 6 月 · 全部品类与地区', start='2018-06-01', end='2018-06-30', category='', state=''),
    dict(id='feb-jul-2018', label='2018 年 2–7 月 · 长观察窗 / 全部', start='2018-02-01', end='2018-07-31', category='', state=''),
    dict(id='july-2018-sp', label='2018 年 7 月 · 圣保罗州', start='2018-07-01', end='2018-07-31', category='', state='SP'),
    dict(id='july-2018-cama-sp', label='2018 年 7 月 · 床上与卫浴 / 圣保罗州', start='2018-07-01', end='2018-07-31', category='cama_mesa_banho', state='SP'),
    dict(id='week-2018-07-23', label='2018 年 7 月 23–29 日 · 完整周', start='2018-07-23', end='2018-07-29', category='', state='', latest_week=True),
    dict(id='week-2017-11-20', label='2017 年 11 月 20–26 日 · 异常核查案例', start='2017-11-20', end='2017-11-26', category='', state=''),
)
FORBIDDEN_KEYS = frozenset({
    'customer_id', 'customer_unique_id', 'order_id', 'seller_id',
    'review_comment_title', 'review_comment_message', 'review_text', 'review_body',
    'customer_zip_code_prefix', 'customer_city', 'address', 'email', 'phone',
    'geolocation_lat', 'geolocation_lng', 'payment_sequential',
})
ALLOWED_TOP_LEVEL = {
    'dashboard': frozenset({'meta', 'kpis', 'previous', 'trend', 'categories',
                            'regions', 'products', 'low_volume_products', 'fulfillment'}),
    'customers': frozenset({'meta', 'summary', 'frequency_distribution', 'distribution', 'segments'}),
    'reports': frozenset({'meta', 'current', 'previous', 'delta_cents', 'revenue_change_rate',
                          'daily_revenue_cents', 'previous_daily_revenue_cents', 'decomposition',
                          'contributions', 'anomalies', 'delivery', 'limitations', 'investigations', 'rendered'}),
}


def safe_json(value):
    """Use FastAPI's encoder so published JSON matches the live API types."""
    encoded = jsonable_encoder(value)
    def scan(node):
        if isinstance(node, dict):
            for key, item in node.items():
                if key in FORBIDDEN_KEYS:
                    raise ValueError(f'Private or order-level key in static export: {key}')
                scan(item)
        elif isinstance(node, list):
            for item in node:
                scan(item)
    scan(encoded)
    return encoded


def require_aggregate_shape(kind, payload):
    if set(payload) != ALLOWED_TOP_LEVEL[kind]:
        raise ValueError(f'Static {kind} response shape changed; review before publishing.')


def write_json(path, value):
    encoded = safe_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(encoded, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    path.write_bytes(body)
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def check_consistency(options, preset, dashboards, customer, report):
    version = options['data_version']
    expected_scope = {key: preset[key] for key in ('start', 'end', 'category', 'state')}
    first = dashboards['day']
    for grain, payload in dashboards.items():
        assert payload['meta']['data_version'] == version
        assert payload['meta']['grain'] == grain
        assert all(payload['meta'][key] == value for key, value in expected_scope.items())
        assert payload['kpis'] == first['kpis']
        assert payload['previous'] == first['previous']
    for payload in (customer, report):
        assert payload['meta']['data_version'] == version
        assert all(payload['meta'][key] == value for key, value in expected_scope.items())
    assert first['kpis']['revenue_cents'] == customer['summary']['revenue_cents'] == report['current']['revenue_cents']
    assert first['kpis']['order_count'] == customer['summary']['order_count'] == report['current']['order_count']
    assert first['kpis']['customer_count'] == customer['summary']['customer_count']
    assert report['current']['revenue_cents'] == sum(row['revenue_cents'] for row in first['categories'])
    assert report['current']['revenue_cents'] == sum(row['revenue_cents'] for row in first['regions'])
    if preset['id'] == 'july-2018':
        assert (first['kpis']['revenue_cents'], first['kpis']['order_count']) == (86795346, 6159)
    if preset['id'] == 'july-2018-cama-sp':
        assert (first['kpis']['revenue_cents'], first['kpis']['order_count']) == (2710604, 262)
    if preset['id'] == 'feb-jul-2018':
        # The long window must demonstrate both sides of the R=30 threshold.
        assert customer['summary']['customer_count'] == 38560
        assert sum(group['customer_count'] for group in customer['segments'] if group['key'].startswith('0')) == 32460
        assert sum(group['customer_count'] for group in customer['segments'] if group['key'].startswith('1')) == 6100


def export(db, output=DEFAULT_OUTPUT):
    output = Path(output)
    options = safe_json(analytics.options(db))
    if options['data_source'] != 'olist':
        raise ValueError('Only the imported Olist warehouse may be exported.')
    options['static_demo'] = True
    options['static_presets'] = list(PRESETS)
    options['static_note'] = '历史数据静态演示；仅能查看预先导出的筛选范围，无实时查询和订单级数据。'
    hashes = {'options.json': write_json(output / 'options.json', options)}
    summary = []
    for preset in PRESETS:
        scope = {key: preset[key] for key in ('start', 'end', 'category', 'state')}
        dashboards = {grain: safe_json(analytics.dashboard(db, **scope, grain=grain)) for grain in GRAINS}
        customer = safe_json(customers.customer_analysis(db, **scope))
        report = safe_json(reports.build_report(db, **scope))
        report['rendered'] = {'markdown': reports.markdown(report), 'html': reports.html_report(report)}
        for dashboard in dashboards.values():
            require_aggregate_shape('dashboard', dashboard)
        require_aggregate_shape('customers', customer)
        require_aggregate_shape('reports', report)
        check_consistency(options, preset, dashboards, customer, report)
        for grain, payload in dashboards.items():
            relative = f"{preset['id']}/dashboard-{grain}.json"
            hashes[relative] = write_json(output / relative, payload)
        for name, payload in (('customers', customer), ('reports', report)):
            relative = f"{preset['id']}/{name}.json"
            hashes[relative] = write_json(output / relative, payload)
        summary.append(dict(id=preset['id'], order_count=dashboards['day']['kpis']['order_count'],
                            revenue_cents=dashboards['day']['kpis']['revenue_cents']))
        print(f"Exported {preset['id']}: {summary[-1]['order_count']} orders")
    # The manifest carries no database URL, raw names, order IDs or personal data.
    manifest = dict(schema_version=1, data_source='olist', data_version=options['data_version'],
                    preset_count=len(PRESETS), files=hashes, summary=summary)
    write_json(output / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export(make_engine(), args.output)


if __name__ == '__main__':
    main()
