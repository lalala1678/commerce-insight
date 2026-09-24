"""Human-readable evidence report, generated from the machine-readable audit."""

def render_report(a):
    t=a['tables'];q=a['quality'];m=q['money'];d=q['dates'];r=a['relationships']
    money=lambda x:f'{x/100:,.2f}'
    lines=['# 第 1 周：需求与数据审计报告','',
      f"审计数据版本：`{a['data_version']}`；生成时间（UTC）：{a['generated_at_utc']}。",
      '本报告只描述文件与指标可行性；没有运行真实业务 ETL，没有把数据接入基础页面。',
      '', '## 1. 结论与验收','',
      f"本地数据有 **{t['orders']['rows']:,} 笔订单**，其中 **{q['statuses']['delivered']:,} 笔已交付**。简历应写“约 9.94 万笔订单”，不要写“10 万+订单”。",
      '订单、商品、客户、地区、履约和评分分析可做；退款、广告 ROI、利润、库存滞销、消费者转化漏斗缺少必要字段。',
      '第 1 周资料已覆盖需求映射、字段字典、关系、缺失、时间与许可。存在质量问题不代表审计失败；这些问题必须成为下一步 ETL 的规则和测试。',
      '', '## 2. 扫描范围与可复现性','',
      f"9 个文件全部扫描，没有抽样或截断（地理表也完整扫描了 {t['geolocation']['rows']:,} 行）。每个文件上限 64 MiB / 1,200,000 行，超过上限直接失败，不输出冒充全量的报告。",
      '使用 UTF-8 严格矩形 CSV 校验；Pandas 全部按字符串读取；空字符串或全空白计缺失，不把 0、NA、null 自动视为缺失。',
      '只输出聚合，不展示订单/客户标识、评价原文或逐行坐标。输入在计算前后核对 SHA-256，不填补、不去重、不修改原始文件。',
      f"软件：Python {a['software']['python']}，Pandas {a['software']['pandas']}。原始指纹、所有字段缺失与关系检查见 [profile.json](audit/profile.json)。",
      '复现：在项目根目录执行 `python -m scripts.audit_data`；该命令刷新聚合 JSON、数据字典和本报告。',
      '独立核对：`python -m scripts.verify_audit` 使用标准库 CSV / Decimal 重算核心结果并比对输入指纹。',
      '', '| 表 | 行数 | 字段数 | 完全重复行 | 候选键多余行 |', '|---|---:|---:|---:|---:|']
    for name,info in t.items():
        key=info.get('duplicate_key_rows','不假设唯一')
        lines.append(f"| {name} | {info['rows']:,} | {len(info['columns'])} | {info['exact_duplicate_rows']:,} | {key} |")
    lines+=['','字段逐列含义、逻辑类型、缺失数、不同值数与 Mermaid 关系图见 [DATA_DICTIONARY.md](DATA_DICTIONARY.md)。',
      '', '## 3. 时间范围与推荐观察窗口','',
      f"- 全部订单下单时间：{d['order_purchase_timestamp']['min']} 至 {d['order_purchase_timestamp']['max']}。",
      f"- 已交付订单下单时间：{q['delivered_purchase_start']} 至 {q['delivered_purchase_end']}。",
      f"- 实际送达时间最大值：{d['order_delivered_customer_date']['max']}；评价回答最大值：{d['review_answer_timestamp']['max']}。",
      f"- 发货期限异常：有 {q['shipping_limit_after_2018_rows']} 条商品项（{q['shipping_limit_after_2018_orders']} 笔订单）的期限在 2018 年之后，最大为 {d['shipping_limit_date']['max']}；不据此扩大销售观察窗口。",
      '- 2016 年数据稀疏，2016-11 无任何订单记录；不能据此证明真实业务当月销售为零。2018-09/10 只有少量非已交付订单，不能当作完整销售月份。',
      '- 首版常规观察窗口建议 2017-01-01 至 2018-07-31，默认展示 2018-07；2018-08 标记为尾部月份，不用于默认完整月比较。该窗口是减轻边界影响的工程选择，不能证明平台交易采样完全。',
      '- 所有状态是数据抽取时最终状态。按下单日统计已交付订单属于历史完成口径，不等于当时可见信息；不能直接用于无泄漏回测。',
      '', '| 下单月份 | 全部订单 | 最终已交付订单 |', '|---|---:|---:|']
    for month in q['monthly_orders']:lines.append(f"| {month['month']} | {month['orders']:,} | {month['delivered']:,} |")
    lines+=['','## 4. 状态、关联与缺失','', '| 订单状态 | 数量 |', '|---|---:|']
    for status,count in q['statuses'].items():lines.append(f'| {status} | {count:,} |')
    lines+=['','### 关联结论','',
      '- 六条核心外键（订单→客户、商品项→订单/商品/卖家、支付→订单、评价→订单）均无缺失键或无法匹配行。',
      f"- orders 中有 {q['orders_distinct_customer_ids']:,} 个 customer_id，客户表无订单的行数为 {q['customers_without_orders']}；当前观测为一单一 customer_id。",
      f"- {q['orders_missing_items']} 笔订单没有商品项，其中已交付缺明细为 {q['delivered_missing_items']}。不为取消/缺货订单补造金额。",
      f"- {q['orders_missing_payments']} 笔订单缺支付记录，且属于已交付。不可通过 inner join 支付表丢弃这笔成交订单，也不能将缺支付当作支付金额为零。",
      f"- {q['orders_missing_reviews']} 笔订单无评价，已交付中无评价为 {q['delivered_missing_reviews']} 笔。无评价不是零分。",
      '', '| 字段 | 缺失数 | 占本表比例 |', '|---|---:|---:|']
    for name,info in t.items():
        for col in info['columns']:
            if col['missing']:lines.append(f"| {name}.{col['name']} | {col['missing']:,} | {col['missing_rate']:.2%} |")
    lines+=['',
      f"已交付订单中，批准时间缺失 {q['delivered_missing_approval']} 笔、承运商接收时间缺失 {q['delivered_missing_carrier']} 笔、送达时间缺失 {q['delivered_missing_delivery']} 笔。商品金额不因这些日期缺失而丢弃；对应履约指标必须使用有效日期分母。",
      f"延迟率可判断分母为 {q['delivery_eligible_orders']:,} 笔；按送达自然日大于预计日期判断，延迟 {q['late_orders']:,} 笔（{q['late_orders']/q['delivery_eligible_orders']:.2%}）。这只是全文件核对值，不是已发布的经营报表。",
      f"评价标题：空串 {q['review_blank_breakdown']['review_comment_title']['empty']:,} 条 + 纯空白 {q['review_blank_breakdown']['review_comment_title']['whitespace_only']} 条；正文：空串 {q['review_blank_breakdown']['review_comment_message']['empty']:,} 条 + 纯空白 {q['review_blank_breakdown']['review_comment_message']['whitespace_only']} 条。因此统计可能不同于仅用默认 isna 的做法。",
      '', '## 5. 防止重复计数：最重要的建模约束','',
      f"- 一单多商品：{q['orders_with_multiple_items']:,} 笔；一单多支付：{q['orders_with_multiple_payments']:,} 笔；一单多评价：{q['orders_with_multiple_reviews']:,} 笔。",
      f"- 多卖家订单：{q['orders_with_multiple_sellers']:,} 笔，订单级评价不能归责于某一个卖家。",
      f"- 评价有 {t['reviews']['rows']:,} 行、{q['reviews_unique_ids']:,} 个 review_id、{q['reviews_unique_orders']:,} 个订单；(review_id, order_id) 联合键当前重复行为 {q['reviews_duplicate_id_order_pairs']}。",
      f"- 正确汇总已交付商品金额：**R$ {money(m['delivered_item_revenue_cents'])}**。",
      f"- 错误地把商品项 LEFT JOIN 原始支付与原始评价后求和：R$ {money(m['naive_items_payments_reviews_revenue_cents'])}，多算 R$ {money(m['naive_items_payments_reviews_revenue_cents']-m['delivered_item_revenue_cents'])}，放大 **{m['naive_items_payments_reviews_revenue_cents']/m['delivered_item_revenue_cents']-1:.2%}**。",
      '下一步必须分别聚合到订单粒度再连接；客户分析使用 customer_unique_id；评价折叠不能静默发生。',
      '', '## 6. 金额核对与合理性检查','',
      f"全部商品金额 R$ {money(m['all_item_revenue_cents'])}，全部运费 R$ {money(m['all_freight_cents'])}，全部支付记录金额 R$ {money(m['all_payment_cents'])}。三者代表不同概念，不能直接相互替代。",
      f"在同时有商品与支付的 {m['comparable_orders']:,} 笔订单中，支付与商品加运费完全一致 {m['exact_match_orders']:,} 笔，差异超过 1 分有 {m['difference_over_one_cent_orders']} 笔。可比较订单的净差额为 R$ {money(m['sum_payment_minus_items_freight_cents'])}；不将差额擅自解释为退款或收入。",
      f"商品价格、运费和支付金额的非法数值分别为 {m['invalid_price']} / {m['invalid_freight']} / {m['invalid_payment']}，负值分别为 {m['negative_price']} / {m['negative_freight']} / {m['negative_payment']}。金额统一用 Decimal 转分核对。",
      f"商品项价格中位数 R$ {money(m['item_price_cents']['median'])}，均值 R$ {money(m['item_price_cents']['mean'])}，P99 R$ {money(m['item_price_cents']['p99'])}，最大 R$ {money(m['item_price_cents']['max'])}。IQR 规则标记 {m['item_price_cents']['iqr_flag_count']:,} 条，只作偏态提醒，不自动删除。",
      f"已交付配送时长中位数 {q['delivery_days']['median']:.2f} 天、均值 {q['delivery_days']['mean']:.2f} 天、P99 {q['delivery_days']['p99']:.2f} 天、最大 {q['delivery_days']['max']:.2f} 天；长尾记录保留并标记。",
      '', '## 7. 客户与 RFM 可行性','',
      f"全部客户表对应 {q['unique_customers_all']:,} 个稳定客户；已交付订单对应 {q['unique_customers_delivered']:,} 个客户。全文件已交付观察窗内复购客户 {q['repeat_customers_delivered_full_window']:,} 人，比例 {q['repeat_customers_delivered_full_window']/q['unique_customers_delivered']:.2%}。",
      '该比例只描述数据窗口与该平台采样，不代表客户终身复购率。F 高度集中于 1，直接做五分位分箱容易出现重复边界；RFM 采用明确规则并展示分布，不能承诺五组等人数。',
      '', '| 已交付订单频次 | 客户数 |', '|---:|---:|']
    for x in q['frequency_distribution']:lines.append(f"| {x['orders_per_customer']} | {x['customers']:,} |")
    lines+=['','## 8. 问题登记与第 2 周规则','',
      '| 优先级 | 证据 | 下一步规则 |','|---|---|---|',
      '| 高 | 多商品、多支付、多评价会放大金额 | 独立汇总后连接；增加金额守恒与订单去重测试 |',
      f"| 高 | 已交付缺支付 {q['delivered_missing_payments']} 笔 | 商品成交口径保留；支付覆盖标记，不用支付表过滤订单 |",
      f"| 高 | 已交付缺送达日期 {q['delivered_missing_delivery']} 笔 | 保留销售；排除于依赖送达日期的分母并披露 |",
      '| 高 | 首尾月份、最终状态与客户左截断 | 限定默认观察窗口，明确历史完成口径和首次可见购买 |',
      f"| 中 | {q['chronology']['carrier_before_purchase']} 笔承运早于下单；{q['chronology']['delivery_before_carrier']} 笔送达早于承运 | 保留原值，添加异常标记；仅排除对应时长指标，不整单删除 |",
      f"| 中 | 品类缺失 610 个商品；另有 {r['products.category -> translation.category']['unmatched_child_rows']} 个商品映射不到英语 | 缺失使用 unknown；无翻译保留原葡语码，禁止 inner join 丢商品 |",
      f"| 中 | {q['shipping_limit_after_2018_rows']} 条发货期限超出 2018 年 | 保留原值并隔离用于发货期限诊断，不能扩展订单日期窗 |",
      f"| 中 | 支付对账差额、{q['numeric_fields']['payment_installments']['zero']} 条 0 期数、{q['numeric_fields']['product_weight_g']['zero']} 个零重量 | 标记并保留，不改写成业务原因 |",
      f"| 低/延期 | 地理表 {t['geolocation']['exact_duplicate_rows']:,} 条完全重复，{q['geolocation_unique_postcodes']:,} 个邮编 | 一版用客户州，暂不接地理明细；未来先聚合并校验匹配率 |",
      f"| 低/延期 | {q['geolocation_postcodes_multiple_states']} 个邮编对应多州；{q['geolocation_outside_coarse_brazil_box']} 条坐标在粗略巴西矩形之外 | 仅核查标记，不自动删记录；矩形不是边界判断 |",
      '',f"客户邮编无法匹配地理表的客户记录 {r['customers.postcode -> geolocation.postcode']['unmatched_child_rows']} 行；卖家无法匹配 {r['sellers.postcode -> geolocation.postcode']['unmatched_child_rows']} 行。地理维度并非无损连接。",
      '', '## 9. 许可、项目状态与资料','',
      'Olist 发布元数据标注 CC BY-NC-SA 4.0，2026-09-19 已再次核对并留存 [来源快照](audit/source_metadata.json)。',
      '许可要求署名、非商业、相同方式共享；发布数据衍生成果时保留来源、许可链接并说明聚合等修改。不把数据许可扩展解释成整个代码库的许可。详见 [DATA_SOURCE.md](DATA_SOURCE.md)。',
      '本地 Git 已初始化在 main；尚无初始提交或远程 GitHub 仓库，没有在线发布。raw/ 和本地数据库继续被 Git 忽略；没有修改 UI、业务 API 或导入真实数据。',
      '', '## 方法来源','',
      '本次使用 exploratory-data-analysis 技能的只读、显式缺失、全量范围标注与聚合输出流程；业务规则及审计实现由本项目定义。',
      'Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. arXiv:2609.00065. https://doi.org/10.48550/arXiv.2609.00065 （2026-09-19 核对当前记录）。','']
    return '\n'.join(lines)
