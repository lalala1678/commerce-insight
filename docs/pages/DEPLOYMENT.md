# 第 7 步：GitHub Pages 静态演示

在线页沿用经营概览、商品与履约、客户分析、经营报告四个页面。它读取当前仓库已提交的 `frontend/public/static-data/` 汇总快照，仅支持页面下拉菜单中的六个观察范围。完整本地后台仍通过 FastAPI 和数据库查询任意可用日期、品类、州，并提供订单详情。

## 导出范围与边界

| 范围 | 用途 |
|---|---|
| 2018 年 7 月，全部 | 默认经营概览、客户与报告 |
| 2018 年 6 月，全部 | 相邻月份对比 |
| 2018 年 7 月，SP | 地区筛选例子 |
| 2018 年 7 月，床上与卫浴＋SP | 同时筛选品类和地区 |
| 2018 年 7 月 23–29 日 | 完整周报例子 |
| 2017 年 11 月 20–26 日 | 历史异常提示核查例子 |

每个范围保存三种趋势粒度及客户、经营报告汇总，共 31 个 JSON 文件，另有哈希清单。导出器使用与本地接口同一套分析函数，核对三个模块的商品金额、订单数与客户数，强制校验已知的 7 月和品类＋SP 数据。清单中的 SHA-256 能发现截断或意外修改；文件都是整型分金额和聚合维度。导出器递归拒绝订单 ID、稳定客户 ID、原始评价文本、地址与地理坐标等字段。静态站不提供订单明细。

数据来源为 [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，以 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 署名、非商业、相同方式共享。在线页脚及说明页保留署名和许可链接。历史最终状态不能当成实时经营数据；异动、履约评分与建议均无因果或已实施收益主张。

## 本地复现

先按 README 导入 Olist 数据。`DATABASE_URL` 未设置时，导出器读取 `data/demo.db` 的真实仓库；设置时读取对应 MySQL 数据库。

```powershell
python -m scripts.export_static
python -m pytest tests/test_static_export.py -q
python -m scripts.verify_static
cd frontend
$env:VITE_STATIC_DEMO = '1'
npm ci
npm run build
npm run preview
```

`VITE_STATIC_DEMO=1` 明确选择静态版。默认 `npm run build` 仍构建本地 FastAPI 版。GitHub Pages 项目路径固定为 `/commerce-insight/`；Vite 在静态构建时使用该前缀。可用浏览器访问 `http://127.0.0.1:4173/commerce-insight/` 检查预览。

## 仓库发布

`.github/workflows/pages.yml` 在 `main` 分支提交或手动触发时，先运行静态快照隐私和哈希测试，再以 Node 22 构建静态版并上传 Pages artifact。GitHub 仓库 Settings → Pages 的 Build and deployment → Source 选择 **GitHub Actions**。工作流需要 `pages: write` 与 `id-token: write` 权限，发布地址预期为 `https://lalala1678.github.io/commerce-insight/`。远程仓库及线上发布是否成功，必须查看实际 Actions 运行与页面请求，不能从本地构建推出。

发布步骤参考 [GitHub Pages 自定义工作流文档](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) 与 [deploy-pages action](https://github.com/actions/deploy-pages)。

本仓库现已发布，实际工作流、线上浏览器与快照核对结果见[公开发布验收](../RELEASE_VERIFICATION.md)。
