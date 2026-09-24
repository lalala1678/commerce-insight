# 本地三服务运行：MySQL、API、网页

`compose.yaml` 提供独立的 MySQL 8.0.41、FastAPI 与 Nginx 网页服务。网页在 `http://127.0.0.1:8080/`，`/api/*`、`/docs` 和 `/openapi.json` 由 Nginx 转发到容器内 API。MySQL 不向宿主机开放端口；网页仅绑定本机回环地址。数据文件只读挂载到 API，数据库内容保存在命名卷中。

## 首次启动

1. 安装 Docker Desktop 或 Docker Engine，并确认 `docker compose version` 可用。
2. 按 [数据来源](../DATA_SOURCE.md)自行下载 Olist CSV，将原始文件放在项目根目录 `data/raw/`。仓库不包含原始数据。不要在网页中把合成样例当作真实经营结果。
3. 复制 `.env.example` 为 `.env`，将两个占位密码替换成**不同的、足够长的纯字母数字密码**。Compose 从同一个 `MYSQL_PASSWORD` 生成数据库用户密码和 API 连接地址，因此无需另写 `DATABASE_URL`。不要提交 `.env`。
4. 在项目根目录依次运行：

```powershell
Copy-Item .env.example .env
# 编辑 .env，并先将原始 CSV 放入 data/raw/
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec api python -m backend.etl data/raw
```

在 macOS / Linux 中将复制命令改为 `cp .env.example .env`，后续命令相同。首次构建需要下载镜像与依赖；全量导入所需时间取决于机器。ETL 完成后打开 [本地网页](http://127.0.0.1:8080/) 和 [接口文档](http://127.0.0.1:8080/docs)。

## 验收

```powershell
docker compose ps
docker compose exec api python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health')))"
docker compose exec api python -m scripts.verify_pipeline
docker compose exec api python -m scripts.verify_core_details
```

`mysql` 和 `api` 应为 healthy，`/api/health` 应显示 `warehouse_ready: true`。网页在 2018 年 7 月能展示经营概览、商品与履约、客户分析、经营报告；更改日期、品类和州后数据应随之变化。核对脚本直接读取只读挂载的 CSV、数据库和 API，以避免只凭网页截图判断成功。停止时运行 `docker compose down`，命名卷仍保留数据；再次运行导入可验证幂等性。

## 常见边界

- MySQL 初始化时只在**空卷**创建用户及密码。已有卷中修改 `.env` 不会自动重置数据库账户；保留现有密码，或先有意识地备份并重建该专用卷。不要对含数据的卷随手执行 `down -v`。
- `data/raw/` 缺文件时，页面会提示仓库未就绪，ETL 会报告缺失文件。请先取得所需的 8 个 CSV；地理数据文件只用于审计。
- `.env` 密码采用字母数字，是为了让 Compose 生成的 URL 无需额外编码；如果自行使用特殊字符，必须按 URL 规则编码并检查 `docker compose config`，且不要把配置输出贴到公开日志。
- API 仅在容器网络中运行；本机通过网页同源的 `/api/*` 访问。若本机 8080 端口被占用，修改 `compose.yaml` 中 `web.ports` 左侧端口。
- 本仓库的静态 GitHub Pages 演示是预计算的历史聚合快照，与这里的本地 MySQL 服务独立；Pages 不连接容器或数据库。

## 当前验证状态

开发机未安装 Docker 命令；[GitHub Actions 容器验收](https://github.com/lalala1678/commerce-insight/actions/runs/36030867207)已在 Ubuntu 上实际启动 MySQL、API 和 Nginx，并用合成 Olist 结构样例验证两次导入、商品金额、接口及网页入口。真实 Olist 全量数据在原生 MySQL 8.0.41 上导入和核对通过，见[核心验收](../core/VERIFICATION.md)。两项证据范围不同：CI 证明容器链路可运行，本地原生 MySQL 证明全量数据处理；本机没有容器全量数据实测。没有 Docker 的开发机可按根目录 README 中的 SQLite 或原生 MySQL 路径运行同一 ETL、API 和页面。
