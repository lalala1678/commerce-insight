# 公开发布与复现验收

验收日期：2026-09-25（Asia/Shanghai）。公开仓库：[lalala1678/commerce-insight](https://github.com/lalala1678/commerce-insight)；在线演示：[GitHub Pages](https://lalala1678.github.io/commerce-insight/)。首次发布提交为 `ff5fc5fac9ddced4d4b7278c82869fcb1acd0699`，数据版本为 `2ca51e3f812486e6`。远程 Git 树与本地已验收提交的 173 个文件按对象哈希逐一一致。

| 验收项 | 证据与结果 |
|---|---|
| 后端与前端 | [Analytics checks](https://github.com/lalala1678/commerce-insight/actions/runs/36030867191) 成功：`pytest -q` 与默认前端生产构建均通过；本地为 82 项测试通过。 |
| 容器复现 | [Docker Compose smoke](https://github.com/lalala1678/commerce-insight/actions/runs/36030867207) 成功：Ubuntu 中启动 MySQL、API、Nginx，用可手算的合成 Olist 结构样例导入两次，核对 5 笔原始订单、3 笔已交付订单、45000 分商品金额及网页/API 入口。 |
| 静态发布 | [Publish historical demo](https://github.com/lalala1678/commerce-insight/actions/runs/36030978481) 成功：检查已提交快照、运行静态隐私与完整性测试、构建并部署 Pages。 |
| 在线访问 | 页面返回 HTTP 200。桌面 1440×1000 和手机 390×844 浏览器实测四页、六范围预设切换、周报下载、周趋势及口径说明；无 `/api/` 请求、页面异常、HTTP 错误或手机水平溢出。 |
| 在线数据 | 线上 `manifest.json`、`options.json`、默认 7 月的 dashboard／customers／reports 五个文件与本地快照逐字节一致；默认显示 6159 笔已交付订单、R$ 867,953.46 商品金额。 |
| 发布隐私 | 远程文件清单不含原始 CSV、本地数据库、`.env` 或依赖目录；在线数据仅为限定筛选的聚合快照，不暴露订单详情与稳定客户标识。 |

首次自动 Pages 工作流在 `configure-pages` 步骤失败，因为新仓库尚未启用 Pages。随后将仓库 Pages 来源设为 GitHub Actions，并手动重新运行工作流；上述成功运行和站点实测才是发布完成证据。

开发机没有 Docker 命令，因此本机未运行容器；容器成功证据来自 GitHub Actions 的 Ubuntu 环境。真实 Olist 全量数据另在原生 MySQL 8.0.41 上重复导入并核对，见[核心验收](core/VERIFICATION.md)。CI 的小样例只验证容器链路及关键粒度、金额规则，不能代替真实全量数据的审计。静态六范围与 API 的 30 份响应核对及本地浏览器测试见[静态演示验收](pages/VERIFICATION.md)。

该站点为公共历史数据的非商业演示，并非实时经营后台。数据来源为 [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，许可 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)；本项目对数据进行了清洗、聚合和解释。没有实施建议、预测收益或证明履约与评分之间的因果关系。

## 产品迭代与再次发布（2026-09-25）

功能与静态数据提交：[`5a49c5e`](https://github.com/lalala1678/commerce-insight/commit/5a49c5e89ccdb4bf8cdb6ed8c134a895f74c3797)。这次将报告发现整理成有证据指针的核查任务，页面可在当前浏览器暂存负责人代号、进度和备注并另行导出；增加 2018 年 2–7 月长观察窗，修正短窗口让所有 R>30 天分群均为零的展示问题；同步明确非商业作品集、数据许可与尚未验证的产品价值，并更新三分钟无声演示视频。

| 验收项 | 证据与结果 |
|---|---|
| 本地计算与构建 | `pytest -q`：83 项通过；API 模式和静态模式前端生产构建均成功。`python -m scripts.verify_static`：7 个预设范围 × 5 类响应，35 次与本地 FastAPI 一致。报告的 68 个任务证据指针均能对应报告数值。 |
| GitHub Actions | [Analytics checks](https://github.com/lalala1678/commerce-insight/actions/runs/36040311888)、[Docker Compose smoke](https://github.com/lalala1678/commerce-insight/actions/runs/36040311570)、[Publish historical demo](https://github.com/lalala1678/commerce-insight/actions/runs/36040311713) 均为 `completed / success`。 |
| 线上内容 | GitHub Pages 的 `options.json`、`manifest.json`、长观察窗的 `customers.json` 与 `reports.json` 和已提交文件逐字一致。2018 年 2–7 月范围有 38,560 位购买客户，其中 R>30 天 32,460 位；另用本地分析表独立 SQL 核对。 |
| 线上交互 | Edge 无头浏览器检查四页、范围切换、最近完整周、趋势粒度、报告下载；经营报告两项任务的证据链接、负责人代号、备注、进度、刷新恢复、清空备注后的状态回退及核查记录 JSON 导出均通过。手机 390×844 无整体水平溢出；过程无 `/api/` 请求、HTTP 错误或页面异常。 |
| 展示材料 | 新视频抽帧复核关键数字和画面，时长 180 秒、180 帧、960×540、无音轨。截图与脚本分别标明 7 月单月和 2–7 月长窗口，不把待核查任务说成已被真实商家采纳。 |

本次结果仍只证明历史样本分析与演示链路可复现。负责人和备注保存在浏览器本地，不是商家任务管理服务；公开聚合快照不能直接用于非公开商家数据，后者需要权限、隔离与小样本抑制。当前尚无真实商家试用、提效、经营收益或付费意愿证据，后续验证步骤见[产品验证计划](PRODUCT_VALIDATION_PLAN.md)。
