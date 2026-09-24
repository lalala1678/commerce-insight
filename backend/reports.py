"""Historical diagnostic reports: deterministic rules, one read snapshot."""
from collections import defaultdict
from datetime import timedelta, datetime, timezone
from fractions import Fraction
from html import escape
from pathlib import Path
from statistics import median

from . import analytics as a

SQL_DIR = Path(__file__).resolve().parents[1] / 'sql'
DAILY_SQL = (SQL_DIR/'report_daily.sql').read_text(encoding='utf-8')
DELIVERY_SQL = (SQL_DIR/'report_delivery.sql').read_text(encoding='utf-8')
RULE_VERSION = 'same-weekday-mad-v1'


def contributions(current, previous):
    now={x['name']:x for x in current}; old={x['name']:x for x in previous}
    rows=[]
    for name in sorted(now.keys() | old.keys()):
        n=int(now.get(name,{}).get('revenue_cents',0)); p=int(old.get(name,{}).get('revenue_cents',0))
        rows.append(dict(name=name,label=now.get(name,old.get(name)).get('label',name),
                         current_cents=n,previous_cents=p,delta_cents=n-p))
    return sorted(rows,key=lambda x:(-abs(x['delta_cents']),x['name']))


def decompose(current, previous):
    if not previous or not current['order_count'] or not previous['order_count']:
        return None
    n1,n0=current['order_count'],previous['order_count']
    a1=Fraction(current['revenue_cents'],n1); a0=Fraction(previous['revenue_cents'],n0)
    volume=(n1-n0)*(a1+a0)/2; value=(a1-a0)*(n1+n0)/2
    assert volume+value == current['revenue_cents']-previous['revenue_cents']
    return {'order_effect_cents':float(volume),'aov_effect_cents':float(value),
            'method':'对称分解：Δ订单×平均客单价 + Δ客单价×平均订单数；仅算术归因'}


def detect_anomalies(daily, start, end, coverage):
    """Only eight strictly previous same weekdays; no current/future baseline."""
    result=[]
    for offset in range((end-start).days+1):
        day=start+timedelta(days=offset)
        history=[day-timedelta(days=7*k) for k in range(1,9)]
        known=lambda d:bool(coverage and coverage[0]<=d<=coverage[1])
        n=sum(known(d) for d in history)
        actual=daily.get(day.isoformat(),{}).get('order_count',0) if known(day) else None
        entry=dict(day=day.isoformat(),order_count=actual,baseline_n=n,baseline_median=None,
                   threshold=None,status='insufficient',reason='目标日或8个历史同星期日不在推荐覆盖内',
                   history_start=history[-1].isoformat(),history_end=history[0].isoformat())
        if known(day) and n==8:
            values=[daily.get(d.isoformat(),{}).get('order_count',0) for d in history]
            center=median(values); mad=median(abs(v-center) for v in values)
            threshold=max(3*1.4826*mad,.5*center,10)
            entry.update(baseline_median=center,threshold=threshold)
            if center<5:
                entry['reason']='历史同星期订单中位数小于5，样本过稀'
            else:
                delta=actual-center
                entry.update(status=('high' if delta>0 else 'low') if abs(delta)>threshold else 'normal',
                             reason='偏离历史基线，待核查' if abs(delta)>threshold else '未触发规则')
        result.append(entry)
    return result


def delivery_diagnosis(rows):
    def summarize(members):
        counts={i:0 for i in range(1,6)}; total=0
        for r in members:
            total+=int(r['order_count'])
            if r['review_score'] is not None:counts[int(r['review_score'])]+=int(r['order_count'])
        n=sum(counts.values()); score_sum=sum(k*v for k,v in counts.items())
        # Five-point histogram avoids exposing order-level reviews.
        mid=[]
        if n:
            positions=[(n-1)//2,n//2]; cumulative=0
            for score,count in counts.items():
                mid.extend(score for pos in positions if cumulative<=pos<cumulative+count)
                cumulative+=count
        variance=(sum(v*k*k for k,v in counts.items())-score_sum*score_sum/n)/(n-1) if n>1 else None
        return dict(order_count=total,reviewed_orders=n,missing_reviews=total-n,
                    mean_score=score_sum/n if n else None,median_score=sum(mid)/2 if n else None,
                    score_sd=max(variance,0)**.5 if variance is not None else None,
                    low_score_share=(counts[1]+counts[2])/n if n else None,
                    scores=[dict(score=k,count=v) for k,v in counts.items()])
    def groups(members):
        return {key:summarize([r for r in members if r['is_late']==value])
                for key,value in [('on_time',0),('late',1),('unknown',None)]}
    overall=groups(rows)
    stratified={}
    for dimension in ('category','state'):
        bins=defaultdict(list)
        for row in rows:bins[row[dimension]].append(row)
        strata=[]
        for name,members in bins.items():
            g=groups(members); late=g['late']; on=g['on_time']
            enough=min(late['reviewed_orders'],on['reviewed_orders'])>=20
            strata.append(dict(name=name,**g,comparison_eligible=enough,
                               score_gap=late['mean_score']-on['mean_score'] if enough else None))
        stratified[dimension]=sorted(strata,key=lambda x:(-x['late']['order_count'],x['name']))
    return dict(groups=overall,strata=stratified,
                note='订单按命中商品金额最大的品类唯一归组；同组至少20条有效评价才展示分组评分差。该门槛不是显著性检验。')


def build_report(db, start='2018-07-23', end='2018-07-29', category='', state=''):
    start,end=a._range(start,end)
    if (end-start).days>365:raise ValueError('经营报告单次范围不得超过366天。')
    prior_start,prior_end,label=a._comparison(start,end)
    with a.read_snapshot(db) as conn:
        dataset=a._meta(conn); coverage=a._coverage(dataset)
        comparable=bool(coverage and coverage[0]<=prior_start<=start and end<=coverage[1])
        params=a._params(start,end,category,state)
        current=a._kpis(conn,params)
        previous=a._kpis(conn,a._params(prior_start,prior_end,category,state)) if comparable else None
        rankings={}
        for dimension,sql in [('category','SELECT category AS name, SUM(price_cents) AS revenue_cents FROM scoped_items GROUP BY category'),
                              ('state','SELECT state AS name, SUM(scoped_revenue_cents) AS revenue_cents FROM scoped_orders GROUP BY state')]:
            now=a._rows(conn,sql,params)
            old=a._rows(conn,sql,a._params(prior_start,prior_end,category,state)) if comparable else []
            rankings[dimension]=contributions(now,old) if comparable else []
        daily=a._rows(conn,DAILY_SQL,a._params(start-timedelta(days=56),end,category,state))
        days={r['day']:{'order_count':int(r['order_count']),'revenue_cents':int(r['revenue_cents'])} for r in daily}
        delivery=delivery_diagnosis(a._rows(conn,DELIVERY_SQL,params))
    delta=current['revenue_cents']-previous['revenue_cents'] if previous else None
    alerts=detect_anomalies(days,start,end,coverage)
    return {'meta':dict(data_source='olist',data_version=dataset['data_version'],currency='BRL',
                       start=start.isoformat(),end=end.isoformat(),category=category,state=state,
                       comparison_start=prior_start.isoformat(),comparison_end=prior_end.isoformat(),comparison_label=label,
                       comparable=comparable,is_calendar_week=start.weekday()==0 and (end-start).days==6,
                       generated_at=datetime.now(timezone.utc).isoformat(),rule_version=RULE_VERSION),
            'current':current,'previous':previous,'delta_cents':delta,
            'revenue_change_rate':delta/previous['revenue_cents'] if previous and previous['revenue_cents'] else None,
            'daily_revenue_cents':current['revenue_cents']/((end-start).days+1),
            'previous_daily_revenue_cents':previous['revenue_cents']/((prior_end-prior_start).days+1) if previous else None,
            'decomposition':decompose(current,previous),'contributions':rankings,'anomalies':alerts,'delivery':delivery,
            'limitations':['历史最终已交付口径，按下单日归属；金额不含运费。',
                           '异常基线只使用目标日前8个同星期日，但历史最终状态不是当时可见快照，不能宣称实时预警回测。',
                           '覆盖外或历史样本不足时不判断异常；覆盖内缺记录按观察到的0单计算，不证明平台没有销售。',
                           '阈值是探索规则，异常仅表示待核查，不自动归因促销、欺诈或经营问题。',
                           '评价组差异为相关性描述，受品类、地区、客群、评价选择和历史抽样影响，不证明配送的因果效果。']}


def markdown(report):
    m=report['meta'];c=report['current'];p=report['previous']
    money=lambda n:'不可计算' if n is None else f'R$ {n/100:,.2f}'
    pct=lambda n:'不可计算' if n is None else f'{n*100:+.2f}%'
    safe=lambda s:str(s).replace('\n',' ').replace('\r',' ').replace('|','／')
    lines=[f"# {'经营周报' if m['is_calendar_week'] else '经营期间报告'}",'',
           f"期间：{m['start']} 至 {m['end']}；品类：{safe(m['category'] or '全部')}；客户州：{safe(m['state'] or '全部')}。",
           f"数据版本：{m['data_version']}；规则：{m['rule_version']}；生成时间：{m['generated_at']}。",'',
           '## 本期指标', '', '| 指标 | 本期 | 比较期 |','|---|---:|---:|',
           f"| 商品金额 | {money(c['revenue_cents'])} | {money(p['revenue_cents'] if p else None)} |",
           f"| 订单数 | {c['order_count']} | {p['order_count'] if p else '不可计算'} |",
           f"| 客单价 | {money(c['average_order_value_cents'])} | {money(p['average_order_value_cents'] if p else None)} |",
           f"| 日均商品金额 | {money(report['daily_revenue_cents'])} | {money(report['previous_daily_revenue_cents'])} |",'',
           f"比较期：{m['comparison_start']} 至 {m['comparison_end']}；{m['comparison_label']}。",
           f"商品金额变化：{money(report['delta_cents'])}（{pct(report['revenue_change_rate'])}）。" if p else '比较期或本期覆盖不足，不计算变化。']
    d=report['decomposition']
    if d:lines+=['',f"算术分解：订单量项 {money(d['order_effect_cents'])}；客单价项 {money(d['aov_effect_cents'])}。四舍五入前两项之和等于金额变化，非因果归因。"]
    for key,title in [('category','品类'),('state','地区')]:
        lines+=['',f'## {title}金额变化（绝对变动前5）','', '| 名称 | 比较期 | 本期 | 差额 |','|---|---:|---:|---:|']
        for row in report['contributions'][key][:5]:
            lines.append(f"| {safe(row['name'])} | {money(row['previous_cents'])} | {money(row['current_cents'])} | {money(row['delta_cents'])} |")
        lines+=['','完整贡献列表保留在配套 JSON；前5行不一定等于总变化。']
    groups=report['delivery']['groups']
    lines+=['','## 履约与评价','', '| 交付组 | 订单数 | 有评分 | 缺评分 | 平均分 |','|---|---:|---:|---:|---:|']
    for key,title in [('on_time','按期'),('late','延迟'),('unknown','日期不足')]:
        g=groups[key];score='不可计算' if g['mean_score'] is None else f"{g['mean_score']:.3f}"
        lines.append(f"| {title} | {g['order_count']} | {g['reviewed_orders']} | {g['missing_reviews']} | {score} |")
    flagged=[r for r in report['anomalies'] if r['status'] in ('high','low')]
    insufficient=sum(r['status']=='insufficient' for r in report['anomalies'])
    lines+=['','## 异常日期待核查','',f'触发规则 {len(flagged)} 天；数据不足 {insufficient} 天。',
            '规则：前8个同星期日订单量中位数≥5；偏差严格超过 max(3×1.4826×MAD, 50%×中位数, 10单) 才提示。']
    for row in flagged:lines.append(f"- {row['day']}：{row['order_count']}单；历史中位数{row['baseline_median']:g}单，阈值{row['threshold']:.2f}单；{'偏高' if row['status']=='high' else '偏低'}，待核查。")
    if not flagged:lines.append('未发现满足当前规则的日期；不表示经营没有问题。')
    lines+=['','## 建议与验证（尚未执行）','',
            '- 先核查贡献变化较大的品类/地区：检查订单明细、商品组合与周期天数，再决定是否需要经营动作。',
            '- 对异常日期先检查源数据完整性和订单状态；仅在获得活动、渠道或库存证据后讨论业务原因。',
            '- 履约改进可先选择可比品类和地区试点，预先固定延迟率与评价覆盖率，使用同期对照检验结果。',
            '', '## 数据与解释限制','']+['- '+s for s in report['limitations']]
    lines+=['', '数据来源：Olist Brazilian E-Commerce Public Dataset，CC BY-NC-SA 4.0。',
            'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce',
            '本报告对公开历史数据进行了清洗、聚合与展示；未修改原始文件。']
    return '\n'.join(lines)+'\n'


def html_report(report):
    """Small safe renderer for our fixed Markdown template; no raw HTML accepted."""
    blocks=[];table=False
    for line in markdown(report).splitlines():
        if line.startswith('|'):
            if line.startswith('|---'):continue
            if not table:blocks.append('<table>');table=True
            blocks.append('<tr>'+''.join('<td>'+escape(cell.strip())+'</td>' for cell in line.strip('|').split('|'))+'</tr>')
            continue
        if table:blocks.append('</table>');table=False
        if line.startswith('# '):blocks.append('<h1>'+escape(line[2:])+'</h1>')
        elif line.startswith('## '):blocks.append('<h2>'+escape(line[3:])+'</h2>')
        elif line:blocks.append('<p>'+escape(line)+'</p>')
    if table:blocks.append('</table>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>经营报告</title><style>body{max-width:960px;margin:40px auto;padding:0 20px;font:15px/1.8 system-ui;color:#294657}h1,h2{color:#167f77}table{width:100%;border-collapse:collapse}td{padding:9px;border-bottom:1px solid #dfe7eb}tr:first-child{background:#eef5f3;font-weight:bold}@media print{body{margin:0}h2{break-after:avoid}tr{break-inside:avoid}}</style><body>'+''.join(blocks)+'</body></html>'
