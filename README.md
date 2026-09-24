# 商析 · 电商经营分析与诊断平台

**八周主线成果：数据审计 → 可靠导入 → 统一指标 → 四页看板 → 经营诊断 → 可复现发布。** 面向数据分析／商业分析求职，使用 Olist 真实历史订单，展示从原始 CSV 到可追溯经营建议的完整流程。

- [在线历史演示](https://lalala1678.github.io/commerce-insight/) · 仅支持预先导出的六个筛选范围，不提供订单级数据。
- [GitHub 仓库](https://github.com/lalala1678/commerce-insight) · [三分钟字幕演示视频](docs/portfolio/demo-screenshots.mp4) · [项目架构](docs/portfolio/ARCHITECTURE.md)。

技术栈：**Python + Pandas + MySQL + FastAPI + Vue3 + Element Plus + ECharts + Docker Compose**。SQLite 用于本地入门和快速测试；GitHub Pages 使用同一前端和预计算聚合快照。

当前有四个页面：

- **经营概览**：成交商品金额、已交付订单、客单价、购买客户数，日／周／月趋势，品类与地区贡献。
- **商品与履约**：TOP 商品、低销量商品，延迟交付率、配送时长、评分分布，以及订单列表和商品项明细。
- **客户分析**：数据内新老客、观察期复购率、购买频次与 RFM 八组，规则和窗口公开。
- **经营报告**：销售变化拆解、历史同星期异常提示、履约诊断，下载 Markdown／HTML／JSON。

本地四页共用日期、品类和客户州筛选，支持订单与商品项明细。在线演示只允许六个已导出范围，隐藏订单明细。默认查看 2018 年 7 月；数据使用最终已交付状态，按下单日归属，金额为 BRL 且不含运费。失败时不会回退为模拟数据。

真实 MySQL 8.0.41 已完成两次全量导入，表行数与金额保持一致：**99,441 笔原始订单、112,650 条商品明细、96,478 笔已交付订单，已交付商品金额 R$ 13,221,498.11**。这些是全文件核对数，不是默认 7 月页面的金额。证据见 [重复导入记录](docs/core/etl_idempotence.json)；第2–4周测试、接口核对与页面检查结果见 [核心版本验收记录](docs/core/VERIFICATION.md)。

两份案例给出有据可查的经营诊断：2018 年 7 月商品总额较 6 月增长 **1.39%**，但日均金额下降 **1.88%**；延迟交付组的评价较低，但样本构成不同，不能据此认定因果。报告将事实、建议、验证办法和局限分别呈现。没有库存、真实退款、广告成本和利润数据，因而不声称这些指标或已实现的经营收益。

第5步验收：56 项测试通过；6 组原始 CSV 独立核对通过。参阅 [客户规则与分布](docs/CUSTOMER_ANALYSIS.md) 和 [客户阶段验收](docs/customers/VERIFICATION.md)。

第6步验收：64 项测试通过，6组原始文件独立核对与四个页面浏览器检查通过。资料：[报告规则与样例](docs/REPORTS.md)、[销售变化案例](docs/reports/CASE_SALES.md)、[履约评价案例](docs/reports/CASE_DELIVERY.md)、[验收记录](docs/reports/VERIFICATION.md)。

第7–8步验收：**82 项测试通过**；6 个预设范围的 30 份静态响应与 FastAPI 一致；三分钟字幕视频已核对时长与关键数字。GitHub Actions 的常规测试、Docker Compose 容器验收和 Pages 发布均通过，在线四页及手机布局已实测。证据见[公开发布验收](docs/RELEASE_VERIFICATION.md)、[静态快照核对](docs/pages/VERIFICATION.md)与[视频说明](docs/portfolio/VIDEO.md)。

## 学习资料

- [每一步做什么、如何验收、推荐模型](docs/ROADMAP.md)
- [统一指标口径](docs/METRICS.md)
- [分析表与 ETL 规则](docs/WAREHOUSE.md)、[核心接口说明](docs/API.md)
- [真实数据来源、获取方式与许可](docs/DATA_SOURCE.md)
- [第 1 周数据审计](docs/DATA_AUDIT.md)、[数据字典与表关系](docs/DATA_DICTIONARY.md)、[需求与字段映射](docs/BUSINESS_REQUIREMENTS.md)
- [第 2–4 周验收记录](docs/core/VERIFICATION.md)
- [公开发布和线上验收](docs/RELEASE_VERIFICATION.md)、[静态演示的范围与导出方法](docs/pages/DEPLOYMENT.md)、[三服务 Docker 启动](docs/deploy/COMPOSE.md)
- [简历项目描述与面试问答](docs/portfolio/RESUME_AND_INTERVIEW.md)、[三分钟演示脚本](docs/portfolio/DEMO_SCRIPT.md)

## 数据如何流到页面

```mermaid
flowchart LR
    A[Olist 原始 CSV] --> B[Pandas 校验与质量标记]
    B --> C[事务导入 MySQL / SQLite]
    C --> D[维度表与订单/明细事实表]
    D --> E[日汇总与统一筛选 SQL]
    E --> F[FastAPI 只读接口]
    F --> G[Vue + ECharts 四个分析页面]
    G --> H[筛选订单与商品项明细]
```

商品、支付、评价先分别整理到适当粒度，再关联订单，避免连接放大金额。金额以整数分存储。缺支付不补成 0，缺送达日期仍保留销售，履约指标使用各自有效样本；订单级评价不能直接归责给某一件商品或某一位卖家。

ETL 先校验，再在一个事务中刷新真实数据表并核对总量；失败时保留此前有效数据。同一批原始文件重跑不会累加入库。**一次只运行一个导入任务**。原始文件只读，文件指纹和质量统计随导入记录保存；历史 `demo_` 表保持独立。

## 本地入门：SQLite，无需 MySQL 或 Docker

准备 Python 3.10+、Node.js 22。以下命令从项目根目录开始运行。

### 1. 取得真实数据

按 [数据来源说明](docs/DATA_SOURCE.md)，从 Olist 的 Kaggle 发布页下载数据，将 CSV 直接解压到 `data/raw/`。不要在表格软件中另存后替换原始文件。其他人克隆仓库后也需要自行下载；仓库不包含原始数据。

ETL 使用订单、订单明细、客户、商品、卖家、支付、评价和品类翻译共 8 个文件。地理明细暂不入库，第 1 周审计仍检查全部 9 个文件。

### 2. 安装后端依赖并导入

Windows PowerShell：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m backend.etl data/raw
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend.etl data/raw
```

未设置 `DATABASE_URL` 时默认使用 `data/demo.db`；文件名沿用地基版本，真实数据与合成数据仍是不同的表。导入结束会输出实际行数、金额、质量标记和文件版本。不要用 `backend.seed` 代替真实数据导入。

### 3. 启动后端

```powershell
.venv/Scripts/python.exe -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

保持此终端运行。macOS / Linux 把 Python 路径替换为 `.venv/bin/python`。打开 [接口文档](http://127.0.0.1:8000/docs)：

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 数据库连接与真实仓库是否就绪 |
| `GET /api/reports` | 经营报告、贡献、异常与分层；可导出 Markdown/HTML |
| `GET /api/customers` | 新老客、观察窗复购、RFM 汇总与频次分布 |
| `GET /api/options` | 数据版本、观察窗口、品类与地区选项 |
| `GET /api/dashboard` | 同一筛选范围的指标、趋势、排名与履约 |
| `GET /api/orders` | 已交付订单列表与分页 |
| `GET /api/orders/{order_id}` | 订单详情与当前品类商品项 |

例如查询 2018 年 7 月：`/api/dashboard?start=2018-07-01&end=2018-07-31&grain=day`。品类和州可追加 `category`、`state` 参数；留空表示全部。日期首尾都包含。

### 4. 启动前端并检查主流程

在另一个终端进入项目根目录，再执行：

```powershell
cd frontend
npm ci
npm run dev
```

Windows 如果 `npm` 受脚本策略限制，使用 `npm.cmd`。打开终端显示的网址，通常为 [本地页面](http://127.0.0.1:5173/)。

依次检查：看到 Olist 历史数据标识 → 改日期并应用筛选 → 切换日／周／月趋势 → 选择品类和客户州 → 打开商品与履约 → 查看订单及商品项。金额随品类变化，支付列仍明确标为整单支付；空数据、无效日期和服务失败均有提示。

## 使用 MySQL

已在原生 MySQL 8.0.41 上验证全量导入。请为本项目准备专用空数据库和账户，设置 `DATABASE_URL` 后，再运行相同 ETL 与后端启动命令。不要连接已有业务库；ETL 会刷新本项目的真实分析表。

PowerShell 示例，替换自己的用户名、密码、端口和数据库名：

```powershell
$env:DATABASE_URL = 'mysql+pymysql://YOUR_USER:YOUR_PASSWORD@127.0.0.1:3306/YOUR_DATABASE?charset=utf8mb4'
.venv/Scripts/python.exe -m backend.etl data/raw
.venv/Scripts/python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

密码中的特殊字符需要 URL 编码。凭证只保存在本地环境，不写进代码或提交 Git。普通 Python 启动不会自动读取 `.env`，需要如上设置环境变量；`.env` 在下面的 Compose 路径中由 Docker 读取。

### Docker Compose：MySQL、API 与网页一起启动

准备 `data/raw/`，复制 `.env.example` 为 `.env`，把两个占位密码改成不同的字母数字密码。然后在项目根目录运行：

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose exec api python -m backend.etl data/raw
```

打开 [本地容器网页](http://127.0.0.1:8080/)；同一地址的 `/api/*` 和 `/docs` 会转发到 API。MySQL 不向宿主机开放端口，原始文件只读挂载。完整检查和常见问题见 [Docker 启动说明](docs/deploy/COMPOSE.md)。开发机没有安装 Docker；[GitHub Actions 容器验收](https://github.com/lalala1678/commerce-insight/actions/runs/36030867207)已在 Ubuntu 上通过合成样例的完整三服务检查，原生 MySQL 全量 Olist 导入另行实测。

## 检查与复现

项目根目录运行后端测试：

```powershell
.venv/Scripts/python.exe -m pytest -q
```

前端目录运行 `npm run build` 检查本地 API 版。静态版从已提交的汇总快照构建：在前端目录设置 `VITE_STATIC_DEMO=1` 后运行 `npm run build`。它不连接 MySQL，且只显示页面列出的六个筛选范围；导出与核对方式见 [Pages 说明](docs/pages/DEPLOYMENT.md)。

需要复核原始文件时，执行 `python -m scripts.audit_data` 和 `python -m scripts.verify_audit`，它们不写数据库；前者刷新第 1 周审计资料，后者使用标准库独立核对。新文件版本可能产生不同结果，不应强行匹配旧报告。

API 运行后，执行 `python -m scripts.verify_pipeline` 独立核对 CSV、SQL、接口的金额与数量；执行 `python -m scripts.verify_core_details` 核对周/月趋势、履约与评价。前者的 DATABASE_URL 需与 API 指向同一数据库。

原有 `python -m backend.seed` 仅用于合成数据练习与回归测试，刷新 `demo_orders`、`demo_items`，对应已弃用的 `/api/overview`。合成数据的 450／3／150 不用于当前真实数据页面或经营结论。

## 仓库结构与发布

```text
backend/          真实仓库、ETL、SQL 查询和 FastAPI；保留独立合成样例
frontend/src/     四页看板及 API／静态双模式
frontend/public/  六个预设范围的聚合 JSON 与口径说明
sql/              可直接阅读的指标查询
tests/            粒度、金额、重复导入、回滚、接口及静态快照检查
docs/             路线图、口径、业务案例、验收和求职展示材料
sample_data/      可提交 Git 的合成样例
data/             真实原始文件与本地数据库；忽略提交
```

公开源码位于 [GitHub](https://github.com/lalala1678/commerce-insight)，静态演示由 [Pages 工作流](.github/workflows/pages.yml)构建；完整本地后台可用 SQLite、原生 MySQL 或 Docker Compose 运行。仓库不含 Olist 原始 CSV、本地数据库、`.env` 或依赖目录。在线聚合快照及图表注明 Olist 来源和 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)；本项目清洗、聚合和解释了公开历史数据，未修改原始文件。该数据许可不自动授权本项目代码，代码目前未单独设置开源许可证。

## 你现在要掌握什么

1. 沿一笔多商品订单，解释“原始 CSV → ETL → SQL → API → 页面”的完整路径。
2. 说明商品、支付和评价为什么必须先归一粒度，以及金额如何独立核对。
3. 找一个品类筛选，解释当前品类商品金额为何可能小于整单商品金额或支付金额。
4. 说明缺送达日期、缺评价与缺支付分别影响哪些指标，为什么不能整单删除。
5. 亲自重跑导入和检查，确认订单数与金额不累加。

如要继续扩展，可按 [路线图](docs/ROADMAP.md) 第 9 步研究品类周销量预测，先建立季节性朴素基线，再进行滚动时间验证；这不是当前版本的已完成功能。模板报告目前按需生成，没有定时发送；不要把建议或观察关联写成已经产生的营收收益。
