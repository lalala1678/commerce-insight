"""Bounded full-file audit of the nine declared Olist CSVs. No raw mutation or ETL.

Run: python -m scripts.audit_data
Outputs only aggregate statistics, declared column names and input fingerprints.
"""
import argparse
import csv
import hashlib
import json
import platform
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd
from .audit_schema import TABLES, FIELDS
from .render_audit import render_report

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 1_200_000
STATES = ['delivered','shipped','canceled','unavailable','invoiced','processing','created','approved']
DATES = {'orders':['order_purchase_timestamp','order_approved_at','order_delivered_carrier_date',
 'order_delivered_customer_date','order_estimated_delivery_date'],
 'items':['shipping_limit_date'], 'reviews':['review_creation_date','review_answer_timestamp']}

def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(file.read()).hexdigest()

def inspect_csv(path, root):
    root=root.resolve()
    if path.is_symlink() or path.resolve().parent != root or not path.is_file() or path.stat().st_nlink>1:
        raise ValueError('Input must be a regular non-linked CSV in the explicit raw root')
    if path.stat().st_size>MAX_BYTES:raise ValueError('File exceeds the 64 MiB audit bound')
    before=digest(path)
    csv.field_size_limit(1_000_000)
    count=0
    with path.open(encoding='utf-8-sig',newline='') as file:
        reader=csv.reader(file,strict=True)
        columns=next(reader)
        if not 1<=len(columns)<=64 or len(columns)!=len(set(columns)):
            raise ValueError('Invalid column layout')
        if any(column not in FIELDS for column in columns):raise ValueError('Undeclared field: update audit schema first')
        for row in reader:
            if len(row)!=len(columns):raise ValueError('Non-rectangular CSV')
            count+=1
            if count>MAX_ROWS:raise ValueError('Audit row bound exceeded; no truncated report is published')
    df=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig',on_bad_lines='error')
    if len(df)!=count:raise ValueError('CSV parser row-count disagreement')
    profile=[]
    for col in columns:
        s=df[col];missing=s.str.strip().eq('')
        profile.append({'name':col,'missing':int(missing.sum()),'missing_rate':float(missing.mean()),
          'distinct_nonmissing':int(s[~missing].nunique())})
    return df,{'file':path.name,'bytes':path.stat().st_size,'sha256':before,'rows':count,
               'columns':profile,'exact_duplicate_rows':int(df.duplicated().sum()),'full_scan':True}

def missing(series):return series.str.strip().eq('')

def money_values(series):
    result=[];invalid=0;negative=0
    for value in series:
        try:
            amount=Decimal(value)*100
            if not amount.is_finite() or amount!=amount.to_integral_value():raise InvalidOperation
            negative+=int(amount<0);result.append(int(amount))
        except (InvalidOperation,ValueError):invalid+=1;result.append(None)
    return pd.Series(result,index=series.index,dtype='Int64'),invalid,negative

def describe_numeric(series):
    s=series.dropna().astype(float)
    if s.empty:return {'count':0}
    median=float(s.median());q1=float(s.quantile(.25));q3=float(s.quantile(.75));iqr=q3-q1
    return {'count':len(s),'min':float(s.min()),'median':median,'mean':float(s.mean()),
     'p95':float(s.quantile(.95)),'p99':float(s.quantile(.99)),'max':float(s.max()),
     'q1':q1,'q3':q3,'mad':float((s-median).abs().median()),
     'iqr_flag_count':int(((s<q1-1.5*iqr)|(s>q3+1.5*iqr)).sum())}

def relationship(child,child_col,parent,parent_col):
    s=child[child_col];mask=missing(s);other=~mask & ~s.isin(parent[parent_col])
    return {'child_rows':len(child),'missing_child_keys':int(mask.sum()),
      'unmatched_child_rows':int(other.sum()),'unmatched_distinct_keys':int(s[other].nunique()),
      'parent_duplicate_key_rows':int(parent.duplicated([parent_col]).sum())}

def build_audit(root):
    root=Path(root).resolve()
    tables={};frames={}
    for name,(filename,grain,key) in TABLES.items():
        df,info=inspect_csv(root/filename,root)
        if key:
            info['candidate_key']=key
            info['duplicate_key_rows']=int(df.duplicated(key).sum())
            info['missing_key_rows']=int(df[key].apply(lambda s:s.str.strip().eq('')).any(axis=1).sum())
        info['grain']=grain;tables[name]=info;frames[name]=df
    o,i,c,p,s,pay,r,g,tr=[frames[name] for name in TABLES]
    relations={}
    for name,child,cc,parent,pc in [
      ('orders.customer_id -> customers.customer_id',o,'customer_id',c,'customer_id'),
      ('items.order_id -> orders.order_id',i,'order_id',o,'order_id'),
      ('items.product_id -> products.product_id',i,'product_id',p,'product_id'),
      ('items.seller_id -> sellers.seller_id',i,'seller_id',s,'seller_id'),
      ('payments.order_id -> orders.order_id',pay,'order_id',o,'order_id'),
      ('reviews.order_id -> orders.order_id',r,'order_id',o,'order_id'),
      ('products.category -> translation.category',p,'product_category_name',tr,'product_category_name'),
      ('customers.postcode -> geolocation.postcode',c,'customer_zip_code_prefix',g,'geolocation_zip_code_prefix'),
      ('sellers.postcode -> geolocation.postcode',s,'seller_zip_code_prefix',g,'geolocation_zip_code_prefix')]:
        relations[name]=relationship(child,cc,parent,pc)
    parsed={};date_stats={}
    for table,cols in DATES.items():
        for col in cols:
            raw=frames[table][col];dt=pd.to_datetime(raw.mask(missing(raw)),format='%Y-%m-%d %H:%M:%S',errors='coerce')
            parsed[col]=dt
            date_stats[col]={'missing':int(missing(raw).sum()),'invalid_nonmissing':int((~missing(raw)&dt.isna()).sum()),
                'min':dt.min().isoformat(' ') if dt.notna().any() else None,
                'max':dt.max().isoformat(' ') if dt.notna().any() else None}
    delivered=o.order_status.eq('delivered');delivered_ids=set(o.loc[delivered,'order_id'])
    status_counts={status:int(o.order_status.eq(status).sum()) for status in STATES}
    status_counts['other']=int((~o.order_status.isin(STATES)).sum())
    month=parsed['order_purchase_timestamp'].dt.strftime('%Y-%m')
    monthly=pd.crosstab(month,o.order_status)
    months=[{'month':m,'orders':int(row.sum()),'delivered':int(row.get('delivered',0))} for m,row in monthly.iterrows()]
    price,bad_price,neg_price=money_values(i.price)
    freight,bad_freight,neg_freight=money_values(i.freight_value)
    payment,bad_payment,neg_payment=money_values(pay.payment_value)
    item_counts=i.groupby('order_id').size();pay_counts=pay.groupby('order_id').size();rev_counts=r.groupby('order_id').size()
    totals=(price+freight).groupby(i.order_id).sum(min_count=1)
    paid=payment.groupby(pay.order_id).sum(min_count=1)
    comparison=pd.DataFrame({'items_and_freight':totals,'payments':paid}).dropna()
    diff=comparison.payments-comparison.items_and_freight
    delivered_items=i.order_id.isin(delivered_ids)
    weights=i.order_id.map(pay_counts).fillna(1).astype(int)*i.order_id.map(rev_counts).fillna(1).astype(int)
    eligible=delivered & parsed['order_delivered_customer_date'].notna() & parsed['order_estimated_delivery_date'].notna()
    lag=parsed['order_delivered_customer_date']-parsed['order_purchase_timestamp']
    late=(parsed['order_delivered_customer_date'].dt.normalize()>parsed['order_estimated_delivery_date'].dt.normalize())
    chronology={name:int(mask.sum()) for name,mask in {
      'approval_before_purchase':parsed['order_approved_at']<parsed['order_purchase_timestamp'],
      'carrier_before_purchase':parsed['order_delivered_carrier_date']<parsed['order_purchase_timestamp'],
      'delivery_before_purchase':parsed['order_delivered_customer_date']<parsed['order_purchase_timestamp'],
      'delivery_before_carrier':parsed['order_delivered_customer_date']<parsed['order_delivered_carrier_date'],
      'estimate_before_purchase_day':parsed['order_estimated_delivery_date'].dt.normalize()<parsed['order_purchase_timestamp'].dt.normalize(),
      'review_answer_before_creation':parsed['review_answer_timestamp']<parsed['review_creation_date'],
    }.items()}
    order_customer=o[['order_id','customer_id']].merge(c[['customer_id','customer_unique_id']],on='customer_id',validate='many_to_one')
    f=order_customer[order_customer.order_id.isin(delivered_ids)].groupby('customer_unique_id').size()
    reviewed=set(r.order_id)
    score=pd.to_numeric(r.review_score,errors='coerce')
    lat=pd.to_numeric(g.geolocation_lat,errors='coerce');lng=pd.to_numeric(g.geolocation_lng,errors='coerce')
    quality={
      'statuses':status_counts,'monthly_orders':months,'dates':date_stats,'chronology':chronology,
      'delivered_purchase_start':parsed['order_purchase_timestamp'][delivered].min().isoformat(' '),
      'delivered_purchase_end':parsed['order_purchase_timestamp'][delivered].max().isoformat(' '),
      'orders_missing_items':int((~o.order_id.isin(i.order_id)).sum()),
      'delivered_missing_items':int((delivered&~o.order_id.isin(i.order_id)).sum()),
      'orders_missing_payments':int((~o.order_id.isin(pay.order_id)).sum()),
      'delivered_missing_payments':int((delivered&~o.order_id.isin(pay.order_id)).sum()),
      'orders_missing_reviews':int((~o.order_id.isin(reviewed)).sum()),
      'delivered_missing_reviews':int((delivered&~o.order_id.isin(reviewed)).sum()),
      'delivered_missing_approval':int((delivered&parsed['order_approved_at'].isna()).sum()),
      'delivered_missing_carrier':int((delivered&parsed['order_delivered_carrier_date'].isna()).sum()),
      'delivered_missing_delivery':int((delivered&parsed['order_delivered_customer_date'].isna()).sum()),
      'delivery_eligible_orders':int(eligible.sum()),'late_orders':int((eligible&late).sum()),
      'delivery_days':describe_numeric(lag[delivered].dt.total_seconds()/86400),
      'unique_customers_all':int(c.customer_unique_id.nunique()),'unique_customers_delivered':len(f),
      'repeat_customers_delivered_full_window':int((f>=2).sum()),
      'frequency_distribution':[{'orders_per_customer':int(k),'customers':int(v)} for k,v in f.value_counts().sort_index().items()],
      'orders_with_multiple_items':int((item_counts>1).sum()),'orders_with_multiple_payments':int((pay_counts>1).sum()),
      'orders_with_multiple_reviews':int((rev_counts>1).sum()),
      'orders_with_multiple_sellers':int((i.groupby('order_id').seller_id.nunique()>1).sum()),
      'orders_distinct_customer_ids':int(o.customer_id.nunique()),
      'customers_without_orders':int((~c.customer_id.isin(o.customer_id)).sum()),
      'orders_missing_items_by_status':{status:int((o.order_status.eq(status)&~o.order_id.isin(i.order_id)).sum()) for status in STATES},
      'order_date_missing_by_status':{status:{col:int((o.order_status.eq(status)&parsed[col].isna()).sum())
          for col in DATES['orders']} for status in STATES},
      'shipping_limit_after_2018_rows':int((parsed['shipping_limit_date']>=pd.Timestamp('2019-01-01')).sum()),
      'shipping_limit_after_2018_orders':int(i.loc[parsed['shipping_limit_date']>=pd.Timestamp('2019-01-01'),'order_id'].nunique()),
      'review_blank_breakdown':{col:{'empty':int(r[col].eq('').sum()),'whitespace_only':int((r[col].ne('')&missing(r[col])).sum())}
          for col in ['review_comment_title','review_comment_message']},
      'reviews_unique_orders':int(r.order_id.nunique()),'reviews_unique_ids':int(r.review_id.nunique()),
      'reviews_duplicate_id_order_pairs':int(r.duplicated(['review_id','order_id']).sum()),
      'reviews_invalid_scores':int((score.isna()|~score.between(1,5)|score.mod(1).ne(0)).sum()),
      'raw_categories':int(p.loc[~missing(p.product_category_name),'product_category_name'].nunique()),
      'geolocation_unique_postcodes':int(g.geolocation_zip_code_prefix.nunique()),
      'geolocation_postcodes_multiple_states':int((g.groupby('geolocation_zip_code_prefix').geolocation_state.nunique()>1).sum()),
      'geolocation_postcodes_multiple_city_spellings':int((g.groupby('geolocation_zip_code_prefix').geolocation_city.nunique()>1).sum()),
      'geolocation_invalid_global_coordinates':int((lat.isna()|lng.isna()|~lat.between(-90,90)|~lng.between(-180,180)).sum()),
      'geolocation_outside_coarse_brazil_box':int((~lat.between(-34,6)|~lng.between(-74,-34)).sum()),
      'geolocation_box_note':'粗略矩形只用于待核查标记，不是国界判定，不删记录。',
      'money':{'currency':'BRL','unit':'cents',
        'invalid_price':bad_price,'negative_price':neg_price,'invalid_freight':bad_freight,'negative_freight':neg_freight,
        'invalid_payment':bad_payment,'negative_payment':neg_payment,
        'all_item_revenue_cents':int(price.sum()),'all_freight_cents':int(freight.sum()),'all_payment_cents':int(payment.sum()),
        'delivered_item_revenue_cents':int(price[delivered_items].sum()),
        'delivered_item_rows':int(delivered_items.sum()),
        'naive_items_payments_reviews_revenue_cents':int((price[delivered_items]*weights[delivered_items]).sum()),
        'comparable_orders':len(comparison),'exact_match_orders':int(diff.eq(0).sum()),
        'difference_over_one_cent_orders':int(diff.abs().gt(1).sum()),
        'sum_payment_minus_items_freight_cents':int(diff.sum()),
        'difference_cents':describe_numeric(diff),'item_price_cents':describe_numeric(price)},
    }
    for table,columns in {'items':['order_item_id'],'payments':['payment_sequential','payment_installments'],
       'products':['product_name_lenght','product_description_lenght','product_photos_qty','product_weight_g','product_length_cm','product_height_cm','product_width_cm']}.items():
        for col in columns:
            raw=frames[table][col];num=pd.to_numeric(raw.mask(missing(raw)),errors='coerce')
            quality.setdefault('numeric_fields',{})[col]={'invalid_nonmissing':int((~missing(raw)&num.isna()).sum()),
              'negative':int(num.lt(0).sum()),'zero':int(num.eq(0).sum()),'fractional':int(num.dropna().mod(1).ne(0).sum())}
    for name,info in tables.items():
        if digest(root/info['file'])!=info['sha256']:raise ValueError('Raw file changed during audit')
    version=hashlib.sha256(''.join(tables[n]['sha256'] for n in sorted(tables)).encode()).hexdigest()[:16]
    return {'schema_version':1,'data_version':version,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'software':{'python':platform.python_version(),'pandas':pd.__version__},
      'scope':{'files':9,'full_scan':True,'truncated':False,'max_rows_per_file':MAX_ROWS,'max_bytes_per_file':MAX_BYTES,
        'missing_policy':'空字符串或全空白；不把 NA/null/0 自动当缺失','raw_modified':False,
        'output_policy':'仅聚合、字段定义、文件摘要；不导出客户/订单标识、自由评价或逐行位置'},
      'tables':tables,'relationships':relations,'quality':quality}

def dictionary(a):
    lines=['# Olist 数据字典与表关系','',f"数据版本：`{a['data_version']}`。9 个 CSV 全文件扫描；所有 CSV 先按字符串读取，以下为业务逻辑类型。",
      '','金额单位 BRL；邮编前缀保留前导零；时间源未携带时区，不擅自转 UTC。仅报告聚合，不展示原始标识和评价。','',
      '## 表关系','', '```mermaid','erDiagram',
      '    CUSTOMERS ||--|| ORDERS : customer_id',
      '    ORDERS ||--o{ ITEMS : order_id',
      '    PRODUCTS ||--o{ ITEMS : product_id',
      '    SELLERS ||--o{ ITEMS : seller_id',
      '    ORDERS ||--o{ PAYMENTS : order_id',
      '    ORDERS ||--o{ REVIEWS : order_id','```','',
      'customers.customer_id 在当前文件与订单是一对一；customer_unique_id 可对应多个 customer_id，分析客户时使用 customer_unique_id 去重。',
      '翻译表与商品品类是可缺失映射；地理表邮编不唯一，不能作为现成维表直接连接，故不画作一对多约束。',
      '订单可能没有明细、支付或评价，图中为 0..N。所有关系均为观测文件事实，ETL 仍须重新校验。','']
    for name,info in a['tables'].items():
        lines += [f"## {name} — `{info['file']}`",'',f"粒度：{info['grain']}。共 {info['rows']:,} 行、{len(info['columns'])} 列。",
          f"候选键：{' + '.join(info.get('candidate_key',[])) or '不假设唯一键，参见审计报告'}；完全重复行：{info['exact_duplicate_rows']:,}。",'',
          '| 字段 | 含义 | 逻辑类型 / 单位 | 约束与用途 | 缺失数 | 非空不同值数 |','|---|---|---|---|---:|---:|']
        for col in info['columns']:
            meaning,kind,note=FIELDS[col['name']]
            lines.append(f"| `{col['name']}` | {meaning} | {kind} | {note} | {col['missing']:,} ({col['missing_rate']:.2%}) | {col['distinct_nonmissing']:,} |")
        lines.append('')
    lines += ['## 关联策略','',
      '1. 明细先汇总成订单金额，支付先按订单汇总，评价先明确保留规则，再连接订单事实。',
      '2. 若按品类筛选，金额仅累加命中明细，订单数使用命中订单去重；不同品类订单数可能重叠，不能简单相加。',
      '3. 一版地区分析直接使用 customer_state；不需要接入百万行地理表。',
      '4. review_id 非唯一不等于可随意去重。暂保留全部原始评价；未来服务层按回答时间取最近一条，并记录并列规则与折叠数量。','']
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=ROOT/'data/raw')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/audit')
    args=parser.parse_args()
    if args.raw.is_symlink():raise ValueError('Raw root must not be a symlink')
    out=args.output.resolve()
    if not out.is_relative_to(ROOT.resolve()) or out.is_relative_to(args.raw.resolve()):
        raise ValueError('Output must be in project, outside raw directory')
    a=build_audit(args.raw)
    out.mkdir(parents=True,exist_ok=True)
    (out/'profile.json').write_text(json.dumps(a,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (ROOT/'docs/DATA_DICTIONARY.md').write_text(dictionary(a),encoding='utf-8')
    (ROOT/'docs/DATA_AUDIT.md').write_text(render_report(a),encoding='utf-8')
    print(json.dumps({'data_version':a['data_version'],'table_rows':{k:v['rows'] for k,v in a['tables'].items()},
      'order_states':a['quality']['statuses'],'full_scan':True},ensure_ascii=False))

if __name__=='__main__':main()
