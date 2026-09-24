"""Public Pages artifact stays aggregate-only and matches its own data contract."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.export_static import FORBIDDEN_KEYS, PRESETS, require_aggregate_shape, safe_json


SNAPSHOTS = Path(__file__).resolve().parents[1] / 'frontend' / 'public' / 'static-data'


@pytest.mark.parametrize('name', sorted(FORBIDDEN_KEYS))
def test_rejects_private_or_order_level_keys_at_any_depth(name):
    with pytest.raises(ValueError, match='Private or order-level key'):
        safe_json({'aggregate': [{'nested': {name: 'do-not-publish'}}]})


def test_rejects_new_response_section_until_reviewed():
    with pytest.raises(ValueError, match='response shape changed'):
        require_aggregate_shape('dashboard', {'meta': {}, 'orders': []})


def test_committed_demo_files_are_bounded_aggregate_snapshots():
    manifest = json.loads((SNAPSHOTS / 'manifest.json').read_text(encoding='utf-8'))
    options = json.loads((SNAPSHOTS / 'options.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 1
    assert manifest['data_source'] == options['data_source'] == 'olist'
    assert manifest['data_version'] == options['data_version']
    assert manifest['preset_count'] == len(PRESETS) == len(options['static_presets'])
    assert [x['id'] for x in PRESETS] == [x['id'] for x in options['static_presets']]
    assert len(manifest['files']) == 1 + len(PRESETS) * 5
    assert len({preset['id'] for preset in PRESETS}) == len(PRESETS)
    assert any((date.fromisoformat(preset['end']) - date.fromisoformat(preset['start'])).days >= 90
               for preset in PRESETS)
    assert all('/orders/' not in key and not key.endswith('orders.json') for key in manifest['files'])
    for relative, digest in manifest['files'].items():
        path = SNAPSHOTS / relative
        raw = path.read_bytes()
        assert len(raw) == digest['bytes']
        assert hashlib.sha256(raw).hexdigest() == digest['sha256']
        payload = json.loads(raw)
        assert safe_json(payload) == payload
    for preset in PRESETS:
        folder = SNAPSHOTS / preset['id']
        dashboards = {grain: json.loads((folder / f'dashboard-{grain}.json').read_text(encoding='utf-8'))
                      for grain in ('day', 'week', 'month')}
        customer = json.loads((folder / 'customers.json').read_text(encoding='utf-8'))
        report = json.loads((folder / 'reports.json').read_text(encoding='utf-8'))
        kpis = dashboards['day']['kpis']
        for grain, dashboard in dashboards.items():
            require_aggregate_shape('dashboard', dashboard)
            assert dashboard['meta']['grain'] == grain
            assert dashboard['meta']['data_version'] == manifest['data_version']
            assert dashboard['kpis'] == kpis
            assert dashboard['meta']['start'] == preset['start']
            assert dashboard['meta']['end'] == preset['end']
        assert customer['summary']['revenue_cents'] == report['current']['revenue_cents'] == kpis['revenue_cents']
        require_aggregate_shape('customers', customer)
        require_aggregate_shape('reports', report)
        assert customer['summary']['order_count'] == report['current']['order_count'] == kpis['order_count']
        assert customer['summary']['customer_count'] == kpis['customer_count']
        assert all(customer['meta'][key] == report['meta'][key] == preset[key]
                   for key in ('start', 'end', 'category', 'state'))
        assert sum(group['customer_count'] for group in customer['segments']) == customer['summary']['customer_count']
        assert len(report['rendered']['html']) and len(report['rendered']['markdown'])
    long_window = json.loads((SNAPSHOTS / 'feb-jul-2018' / 'customers.json').read_text(encoding='utf-8'))
    older = sum(group['customer_count'] for group in long_window['segments'] if group['key'].startswith('0'))
    recent = sum(group['customer_count'] for group in long_window['segments'] if group['key'].startswith('1'))
    assert (older, recent) == (32460, 6100)
    assert long_window['distribution']['recency_days']['max'] > 30
