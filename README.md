## 個人化新聞聚合器 (Personalized News Aggregator)

端到端新聞聚合：RSS 收集、內容抽取/去重/語言偵測、推薦與 UI。支援 Docker Compose 一鍵部署（web/worker/beat/redis/db）。

### 功能
- Flask API + SQLAlchemy（PostgreSQL）+ Alembic 遷移
- Celery + Redis 背景任務；Celery Beat 每 15 分鐘排程抓取
- RSS 解析、URL canonical、語言偵測、simhash 去重、來源歸一
- 個人化推薦與熱門排序；前端支援分類/來源/國家/語言/搜尋/排序/無限捲動/骨架屏/主題與密度切換/統計卡

### Docker 快速開始
1) 啟動服務
```bash
docker compose up -d --build db redis web worker beat
```
UI: `http://127.0.0.1:5080`

2) 套用遷移（在容器內）
```bash
docker compose run --rm -e DATABASE_URL=postgresql+psycopg2://news:news@db:5432/news web bash -lc \
  "/app/.venv/bin/alembic upgrade head"
```

3) 立即導入一次新聞（容器內）
```bash
docker compose run --rm -e BACKEND_URL=http://web:5000 web bash -lc \
  "/app/.venv/bin/python -m crawler.fetch_feeds"
```
之後 Celery Beat 會每 15 分鐘自動抓取。

### 常用指令
```bash
docker compose logs web --tail=100
docker compose logs worker --tail=100
docker compose logs beat --tail=100
# 立即觸發一次抓取
curl -X POST http://127.0.0.1:5080/crawl
```

### 環境
- DATABASE_URL: `postgresql+psycopg2://news:news@db:5432/news`
- REDIS_URL: `redis://redis:6379/0`
- BACKEND_URL（worker/beat 用）: `http://web:5000`

### 本機開發（可選）
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///data/local.db
python -m backend.app
```

### 專案結構
- `backend/`：Flask app、models、recommendation、text_utils、templates
- `crawler/`：RSS 抓取與導入
- `tasks/`：Celery app 與任務（fetch_feed、fetch_article、schedule）
- `alembic/`：遷移

### 備註
- 部分來源需要授權或會擋 RSS；會跳過不影響其他來源。
- Compose 使用 trust auth 僅供開發，勿用於生產。
