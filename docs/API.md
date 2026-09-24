# 核心版本接口

当前全部为只读 GET。交互文档在本地 http://127.0.0.1:8000/docs 。
输入在服务端校验；SQL 使用参数绑定。没有真实仓库时返回 503，不回退到合成数据。

## 共用筛选

| 参数 | 规则 |
|---|---|
| start / end | YYYY-MM-DD，首尾日期包含；缺省为 2018-07-01 / 2018-07-31 |
| category | 可省略；Olist 原始品类值，unknown 为未分类；只统计命中商品项 |
| state | 可省略；客户州编码，例如 SP；未命中时返回空集合 |
| grain | 仅 dashboard 使用；day / week / month，默认 day |

日期限制在 1900–2099 年，单次最长 1096 天，开始不得晚于结束。推荐窗为实际已交付观察窗与 2017-01-01 至 2018-07-31 的交集；范围外可查询，但不承诺覆盖完整。
货币 BRL。字段后缀 `_cents` 表示分；成交金额是整数分，客单价可为小数分。比例为 0–1 小数；null 表示不可计算或缺记录。

## 路由与返回

| 路由 | 内容 |
|---|---|
| /api/health | 服务和数据库连通；warehouse_ready 标识真实 ETL 是否提交成功 |
| /api/options | 品类、州、默认日期、实际观察日期、推荐日期、导入时间和数据版本 |
| /api/dashboard | meta、kpis、previous、trend、categories、regions、products、low_volume_products、fulfillment |
| /api/orders | 相同筛选的已交付订单分页；page 默认 1，page_size 默认 20、范围 1–100 |
| /api/orders/{order_id} | 指定订单及商品项；接受 category；未命中或非已交付订单返回 404 |
| /api/overview | 已弃用的地基合成样例接口，主页面不使用 |

`kpis` 包含 revenue_cents、order_count、item_count、customer_count、average_order_value_cents。
`previous` 使用完全相同的品类/地区；完整自然月对比前一自然月，并披露天数差；其他日期对比前一等长期间。任一期超出推荐覆盖则为 null。

`trend` 每项包含 period、revenue_cents、order_count、complete。周从星期一开始，月从 1 日开始；首尾被筛选截断的周期 complete=false。推荐覆盖外无记录的周期金额和订单数为 null，不能绘成零销售。

`fulfillment` 包含有效配送样本、延迟率分母、延迟订单数、时长均值和中位数、评价样本数、平均评分、交付分组与 1–5 分分布。缺日期只从相关分母排除，保留商品销售。分组评分不代表因果关系。

订单分页按下单日降序、订单 ID 升序，返回 rows、total、page、page_size。页码超过末页返回空 rows。
订单列表中的 revenue_cents/item_count 跟随品类筛选；payment_cents 是整单支付，不随品类拆分。
详情另有 total_order_revenue_cents 和 scope_note 说明差异。quality_flags 只表示待检查的源数据问题。

## 空数据与错误

- 没有记录：金额/订单/件数/客户数为 0，客单价及履约比例为 null，排名为空；空观察窗不产生有效比较期。
- 422：日期或参数不合法；404：订单详情不存在；503：数据库或仓库未就绪。
- 每个多查询响应使用一致性数据库快照。meta.data_version 标识当前响应的数据版本；前端旧请求会被取消或丢弃。
- 本地开发代理 `/api` 到 8000 端口；部署需配置同源反向代理。前端构建产物目前需要 API，不是独立静态演示。

原始 CSV → SQL → HTTP 的独立核对脚本是 `python -m scripts.verify_pipeline`，执行前确认 DATABASE_URL 与 API 指向同一仓库。

## 客户分析接口

`GET /api/customers` 复用 start/end/category/state 筛选，无额外粒度参数。返回 meta（数据和规则版本、截止日、阈值、说明）、summary（购买/新/老/复购客户、复购率、订单与金额）、frequency_distribution、distribution（R/F/M 的 min/median/p75/max）及8个 segments。分组包含 key、规则 label、客户数、订单数、商品金额分。无客户时复购率为 null、分组计数为0，不返回个人标识。详细语义见 [CUSTOMER_ANALYSIS.md](CUSTOMER_ANALYSIS.md)。

## 经营报告接口

`GET /api/reports` 共用 start/end/category/state，最多366天；format=json（默认）/markdown/html。JSON含 meta、current、previous、delta_cents、revenue_change_rate、两期日均金额、decomposition、contributions、anomalies、delivery、limitations 和 rendered（Markdown/HTML正文）。非JSON格式作为附件返回。完整语义见 [REPORTS.md](REPORTS.md)。比较不足/零基数保留null；异常不足标 insufficient；下载文本记录来源、许可、数据版本和规则。
