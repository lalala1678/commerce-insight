"""Compare every published static aggregate with the actual local FastAPI response."""

import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import make_engine
from scripts.export_static import DEFAULT_OUTPUT, GRAINS, PRESETS


def compare(client, path, params, file):
    response = client.get(path, params=params)
    response.raise_for_status()
    live = response.json()
    frozen = json.loads(file.read_text(encoding='utf-8'))
    if path == '/api/reports':
        # Generation timestamp and the template text containing it are expected
        # to differ on a later request; all numeric and rule fields must match.
        del live['meta']['generated_at'], frozen['meta']['generated_at']
        del live['rendered'], frozen['rendered']
    assert live == frozen, f'Static snapshot differs from live API: {file.name} {params}'


def verify():
    client = TestClient(create_app(make_engine()))
    options = client.get('/api/options')
    options.raise_for_status()
    frozen_options = json.loads((DEFAULT_OUTPUT / 'options.json').read_text(encoding='utf-8'))
    assert options.json()['data_version'] == frozen_options['data_version']
    for preset in PRESETS:
        params = {key: preset[key] for key in ('start', 'end', 'category', 'state')}
        folder = DEFAULT_OUTPUT / preset['id']
        for grain in GRAINS:
            compare(client, '/api/dashboard', {**params, 'grain': grain}, folder / f'dashboard-{grain}.json')
        compare(client, '/api/customers', params, folder / 'customers.json')
        compare(client, '/api/reports', params, folder / 'reports.json')
        print(f"Verified API parity: {preset['id']}")


if __name__ == '__main__':
    verify()
