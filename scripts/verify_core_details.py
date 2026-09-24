"""Independently compare raw CSV to real HTTP trend/fulfillment responses.

No serving SQL, ETL functions, metric functions or database credentials are used.
Run: python -m scripts.verify_core_details --api-url http://127.0.0.1:8000
The output contains aggregates only, never order/customer/review identifiers.
"""
import argparse
import calendar
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import median

import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = ('olist_orders_dataset.csv', 'olist_order_items_dataset.csv', 'olist_order_reviews_dataset.csv')
CORE_START, CORE_END = date(2017, 1, 1), date(2018, 7, 31)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def records(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def timestamp(value):
    return datetime.strptime(value.strip(), '%Y-%m-%d %H:%M:%S') if value.strip() else None


def raw_data(directory):
    orders = {row['order_id']: row for row in records(directory / FILES[0])}
    revenue = defaultdict(int)
    for row in records(directory / FILES[1]):
        pennies = Decimal(row['price']) * 100
        require(pennies == pennies.to_integral_value(), 'Raw price is not exact cents')
        revenue[row['order_id']] += int(pennies)
    latest = {}
    review_counts = Counter()
    for index, row in enumerate(records(directory / FILES[2])):
        review_counts[row['order_id']] += 1
        # Latest answer; ties by creation date, review ID, then source row order.
        key = (timestamp(row['review_answer_timestamp']) or datetime.min,
               timestamp(row['review_creation_date']) or datetime.min, row['review_id'], index)
        existing = latest.get(row['order_id'])
        if existing is None or key > existing[0]:
            latest[row['order_id']] = (key, int(row['review_score']))
    delivered = []
    for oid, row in orders.items():
        if row['order_status'] != 'delivered':
            continue
        purchase = timestamp(row['order_purchase_timestamp'])
        arrival = timestamp(row['order_delivered_customer_date'])
        estimate = timestamp(row['order_estimated_delivery_date'])
        duration = int((arrival-purchase).total_seconds()) if arrival and arrival >= purchase else None
        late = int(arrival.date() > estimate.date()) if arrival and estimate and arrival >= purchase else None
        delivered.append({'day': purchase.date(), 'revenue_cents': revenue[oid], 'seconds': duration,
                          'late': late, 'score': latest[oid][1] if oid in latest else None,
                          'review_count': review_counts[oid], 'missing_delivery': arrival is None})
    return delivered


def mean(values):
    return sum(values) / len(values) if values else None


def expected_fulfillment(rows):
    durations = [row['seconds'] for row in rows if row['seconds'] is not None]
    scores = [row['score'] for row in rows if row['score'] is not None]
    eligible = [row['late'] for row in rows if row['late'] is not None]
    groups = []
    for value, label in ((0, '准时交付'), (1, '延迟交付'), (None, '日期不足')):
        members = [row for row in rows if row['late'] == value]
        group_scores = [row['score'] for row in members if row['score'] is not None]
        groups.append({'label': label, 'order_count': len(members), 'reviewed_orders': len(group_scores),
                       'average_review_score': mean(group_scores)})
    distribution = Counter(scores)
    return {'eligible_orders': len(eligible), 'late_orders': sum(eligible),
            'late_rate': mean(eligible), 'delivery_sample_count': len(durations),
            'average_delivery_days': mean(durations)/86400 if durations else None,
            'median_delivery_days': median(durations)/86400 if durations else None,
            'reviewed_orders': len(scores), 'average_review_score': mean(scores), 'groups': groups,
            'scores': [{'score': score, 'order_count': distribution[score]} for score in range(1, 6)]}


def period_bounds(day, grain):
    if grain == 'week':
        begin = day-timedelta(days=day.weekday())
        return begin, begin+timedelta(days=6)
    begin = day.replace(day=1)
    return begin, day.replace(day=calendar.monthrange(day.year, day.month)[1])


def expected_trend(rows, start, end, grain, observed_start, observed_end):
    values = defaultdict(lambda: {'revenue_cents': 0, 'order_count': 0})
    for row in rows:
        begin, _ = period_bounds(row['day'], grain)
        values[begin]['revenue_cents'] += row['revenue_cents']
        values[begin]['order_count'] += 1
    recommended_start = max(CORE_START, observed_start)
    recommended_end = min(CORE_END, observed_end)
    expected = []
    begin, _ = period_bounds(start, grain)
    while begin <= end:
        _, last = period_bounds(begin, grain)
        complete = start <= begin and last <= end and recommended_start <= begin and last <= recommended_end
        covered_part = max(start, begin) >= recommended_start and min(end, last) <= recommended_end
        counts = values.get(begin)
        expected.append({'period': begin.isoformat(), 'complete': complete,
                         'revenue_cents': counts['revenue_cents'] if counts else (0 if covered_part else None),
                         'order_count': counts['order_count'] if counts else (0 if covered_part else None)})
        begin = last+timedelta(days=1)
    return expected


def compare_fulfillment(actual, expected, path='fulfillment'):
    for key, value in expected.items():
        if isinstance(value, list):
            require(len(actual[key]) == len(value), f'{path}.{key}: length mismatch')
            for index, member in enumerate(value):
                compare_fulfillment(actual[key][index], member, f'{path}.{key}[{index}]')
        elif isinstance(value, float):
            # MySQL AVG(integer score) retains four decimal places by default.
            tolerance = .000051 if key == 'average_review_score' else 1e-8
            require(actual[key] is not None and math.isclose(actual[key], value, rel_tol=0, abs_tol=tolerance),
                    f'{path}.{key}: numeric mismatch')
        else:
            require(actual[key] == value, f'{path}.{key}: exact mismatch')


def verify(api_url, output):
    directory = ROOT / 'data' / 'raw'
    fingerprints = {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in FILES}
    delivered = raw_data(directory)
    require(bool(delivered), 'This acceptance script requires the published Olist delivered dataset')
    observed_start = min(row['day'] for row in delivered)
    observed_end = max(row['day'] for row in delivered)
    cases = [('july', date(2018, 7, 1), date(2018, 7, 31)),
             ('all_delivered', date(2016, 9, 4), date(2018, 10, 17))]
    results, versions = [], set()
    session = requests.Session()
    for name, start, end in cases:
        rows = [row for row in delivered if start <= row['day'] <= end]
        expected = expected_fulfillment(rows)
        trends = []
        for grain in ('week', 'month'):
            response = session.get(api_url.rstrip('/') + '/api/dashboard', params={
                'start': start.isoformat(), 'end': end.isoformat(), 'grain': grain}, timeout=120)
            response.raise_for_status()
            data = response.json()
            versions.add(data['meta']['data_version'])
            require(data['meta']['data_source'] == 'olist', 'Unexpected data source')
            require(data['kpis']['order_count'] == len(rows), name + ': raw order count differs')
            require(data['kpis']['revenue_cents'] == sum(row['revenue_cents'] for row in rows), name + ': raw money differs')
            require(data['trend'] == expected_trend(rows, start, end, grain, observed_start, observed_end),
                    name + '/' + grain + ': trend buckets or completeness differ')
            require(sum(row['revenue_cents'] or 0 for row in data['trend']) == data['kpis']['revenue_cents'], 'Trend money does not reconcile')
            require(sum(row['order_count'] or 0 for row in data['trend']) == len(rows), 'Trend count does not reconcile')
            compare_fulfillment(data['fulfillment'], expected)
            trends.append({'grain': grain, 'bucket_count': len(data['trend']),
                           'incomplete_buckets': sum(not row['complete'] for row in data['trend']),
                           'every_bucket_matches_raw': True, 'sums_reconcile': True})
        results.append({'name': name, 'start': start.isoformat(), 'end': end.isoformat(), 'orders': len(rows),
                        'missing_delivery_dates': sum(row['missing_delivery'] for row in rows),
                        'orders_with_multiple_reviews': sum(row['review_count'] > 1 for row in rows),
                        'raw_expected_fulfillment': expected, 'api_matches_raw': True, 'trends': trends})
    require(len(versions) == 1, 'Dataset version changed between requests; rerun on a stable import')
    require(fingerprints == {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in FILES},
            'Raw files changed during verification')
    artifact = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'data_version': versions.pop(),
                'independent_source': 'standard-library CSV/Decimal/datetime; HTTP only; no backend metric reuse',
                'source_sha256': fingerprints, 'mean_score_absolute_tolerance': .000051,
                'exact_counts_and_cents': True, 'cases': results}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'cases': len(results), 'http_checks': len(results)*2, 'all_trend_buckets_match': True,
                      'fulfillment_and_latest_reviews_match': True,
                      'full_delivered_orders': len(delivered)}, ensure_ascii=False))
    return artifact


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', default=str(ROOT/'docs/core/detail_acceptance.json'))
    args = parser.parse_args()
    verify(args.api_url, args.output)
