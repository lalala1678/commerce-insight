# 真实数据来源与许可核对

- 发布者：Olist。
- 数据集：https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- 许可：CC BY-NC-SA 4.0（2026-09-19 再次查询 Kaggle 发布者元数据，见 [来源快照](audit/source_metadata.json)）。
- 原始数据不提交 Git；后续可再现脚本应提供下载指引与版本摘要。
- 基础版 sample_data 为自行创建的合成数据，与 Olist 无关。

当前工作环境已下载真实 ZIP，解压文件放在 data/raw/，该目录被 .gitignore 忽略。
它没有进入 demo 数据库。第 1 周已对全部 9 个文件完成只读审计。其他人克隆仓库后需自行从发布页下载并解压。

第一步先看：

1. olist_orders_dataset.csv：每行一笔订单，核对状态与时间字段。
2. olist_order_items_dataset.csv：每行一个订单商品项，一笔订单可能多行。
3. olist_customers_dataset.csv：区分 customer_id 与跨订单客户身份 customer_unique_id。

随后才加入商品、卖家、支付、评价。原始评价文本和位置细节不要直接发布到网页。
本数据集不提供完整退款流水、库存、成本、消费者广告点击，不应补造这些业务指标。

只把样例用来验证代码，不用它证明真实数据分析能力。本次全量审计确认订单为 99,441 笔、已交付 96,478 笔，证据见 [审计报告](DATA_AUDIT.md)。

## 许可核对记录

- 发布者元数据的 currentVersionNumber 为 2，lastUpdated 为 2021-10-01T19:08:27.97Z；这是发布元数据，不是订单日期，也不是每个 CSV 的内容证明。
- 9 个本地 CSV 的完整 SHA-256、大小和行数单独记录在 [profile.json](audit/profile.json)，组合文件指纹对应的数据版本为 `0884b628bb036f39`。
- [CC BY-NC-SA 4.0 官方说明](https://creativecommons.org/licenses/by-nc-sa/4.0/)要求署名、非商业用途，并对分发的改编成果采用相同许可；署名还应给出许可链接并指出所作修改。
- 仓库仍不上传原始数据；未来发布由 Olist 派生的示例 JSON、图表和分析时，标明 Olist 来源、CC BY-NC-SA 4.0、聚合/筛选等修改，不暗示 Olist 背书。
- 当前用途限定为非商业学习与作品展示，不将此核对理解为对未来商业用途的授权。数据许可不能直接代替项目代码许可；本阶段不另行替代码选择许可证。

署名模板：

> 数据来源：Olist，Brazilian E-Commerce Public Dataset by Olist，https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce 。许可：CC BY-NC-SA 4.0，https://creativecommons.org/licenses/by-nc-sa/4.0/ 。本项目对原始数据进行了只读统计、缺失与关系审计；未修改源文件。分析结论由本项目独立形成。

## 复现准备

从发布页下载并将 9 个 CSV 直接放到 `data/raw/`，不要在电子表格软件中另存后再替换原始文件，以免改变邮编、日期或编码。
运行 `python -m scripts.audit_data`；如果哈希不同，应视为新版本并重新确认报告，不强行写回本次数量。
再运行 `python -m scripts.verify_audit`，它使用标准库独立核对所有字段缺失、行数和核心金额。
