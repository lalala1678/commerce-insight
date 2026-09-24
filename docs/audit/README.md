# 审计证据

- profile.json：9 个 CSV 全文件扫描结果、SHA-256、字段缺失、关系与聚合质量检查。
- source_metadata.json：2026-09-19 查询发布者元数据的有限字段快照，不含授权令牌。
- verification.json：标准库 CSV / Decimal 对核心结果的独立核对记录。

只包含聚合信息、字段定义和文件指纹，不包含订单/客户 ID、评价原文或逐行坐标。
这些文件支持数据字典和 DATA_AUDIT.md，不是已经完成的 ETL 或经营后台数据。

数据来源：[Olist / Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。
基于该数据的本目录审计聚合成果采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，保留署名、非商业和相同方式共享条件。
修改说明：统计、分组、缺失与关系核查；源文件未修改。该声明不为整个项目代码赋予许可证。
