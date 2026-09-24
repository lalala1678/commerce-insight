"""Window-based customer analysis. No customer identifiers leave this module."""
from collections import Counter
from pathlib import Path
from statistics import median

from . import analytics

CUSTOMER_SQL = (Path(__file__).resolve().parents[1] / 'sql/customers.sql').read_text(encoding='utf-8')
RECENT_DAYS = 30
AMOUNT_CENTS = 20000


def segment_key(recency, frequency, monetary):
    return f'{int(recency <= RECENT_DAYS)}{int(frequency >= 2)}{int(monetary >= AMOUNT_CENTS)}'


def describe(values):
    values = sorted(values)
    if not values:
        return {'min': None, 'median': None, 'p75': None, 'max': None}
    # Nearest-rank percentile, deterministic even for small/tied populations.
    return {'min': values[0], 'median': median(values),
            'p75': values[(3 * len(values) + 3) // 4 - 1], 'max': values[-1]}


def customer_analysis(db, start='2018-07-01', end='2018-07-31', category='', state=''):
    start, end = analytics._range(start, end)
    with analytics.read_snapshot(db) as conn:
        dataset = analytics._meta(conn)
        rows = analytics._rows(conn, CUSTOMER_SQL, analytics._params(start, end, category, state))
    groups = {}
    for recent in (1, 0):
        for repeat in (1, 0):
            for amount in (1, 0):
                key = f'{recent}{repeat}{amount}'
                groups[key] = {'key': key, 'label': ' / '.join([
                    '距末次购买≤30天' if recent else '距末次购买>30天',
                    '购买≥2次' if repeat else '购买1次',
                    '金额≥R$200' if amount else '金额<R$200']),
                    'customer_count': 0, 'order_count': 0, 'revenue_cents': 0}
    new = repeat_count = total_orders = total_money = 0
    recencies, frequencies, amounts = [], [], []
    for row in rows:
        r = (end - analytics._date(row['last_day'])).days
        f, m = int(row['frequency']), int(row['monetary_cents'])
        new += analytics._date(row['first_day']) >= start
        repeat_count += f >= 2
        total_orders += f
        total_money += m
        recencies.append(r); frequencies.append(f); amounts.append(m)
        group = groups[segment_key(r, f, m)]
        group['customer_count'] += 1
        group['order_count'] += f
        group['revenue_cents'] += m
    n = len(rows)
    warnings = ['首次购买仅指数据内首次已交付购买，不代表注册或终身首次购买。',
                'RFM仅描述本窗口购买客户；不包含窗口内未购买的历史客户，不能据此识别全部流失客户。',
                '分组阈值为探索性规则，不是预测模型或已验证的客户价值标准。']
    coverage = analytics._coverage(dataset)
    if not coverage or start < coverage[0] or end > coverage[1]:
        warnings.append('日期超出推荐观察窗；历史抽样、稀疏及尾部记录可能影响客户指标。')
    if (end-start).days <= RECENT_DAYS:
        warnings.append('当前窗口不超过31天，纳入客户的R均≤30天；可扩大日期范围观察R差异。')
    if category or state:
        warnings.append('F、M、R跟随当前筛选；首次购买仍按截止日之前的全品类、全地区历史计算。')
    return {'meta': {'data_source': 'olist', 'data_version': dataset['data_version'],
                    'start': start.isoformat(), 'end': end.isoformat(), 'cutoff': end.isoformat(),
                    'category': category, 'state': state, 'currency': 'BRL', 'warnings': warnings,
                    'rules': {'version': 'rfm-window-v1', 'recent_days_lte': RECENT_DAYS,
                              'repeat_orders_gte': 2, 'amount_cents_gte': AMOUNT_CENTS,
                              'percentile_method': 'nearest_rank'}},
            'summary': {'customer_count': n, 'new_customers': int(new), 'returning_customers': n-int(new),
                        'repeat_customers': int(repeat_count), 'repeat_rate': repeat_count/n if n else None,
                        'order_count': total_orders, 'revenue_cents': total_money,
                        'single_purchase_share': (n-repeat_count)/n if n else None},
            'frequency_distribution': [{'frequency': f, 'customer_count': count}
                                       for f, count in sorted(Counter(frequencies).items())],
            'distribution': {'recency_days': describe(recencies), 'frequency': describe(frequencies),
                             'monetary_cents': describe(amounts)},
            'segments': list(groups.values())}
