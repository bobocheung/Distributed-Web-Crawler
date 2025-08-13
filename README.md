## 個人化新聞聚合器 (Personalized News Aggregator)

一個根據用戶興趣聚合新聞的應用：
- 爬蟲：RSS 聚合（`crawler/fetch_feeds.py`）
- NLP：簡單文本分類模型（`ml/train_classifier.py` -> `ml/model.joblib`）
- 後端 API：Flask + SQLAlchemy（`backend/app.py`）
- 推薦：基於內容與用戶偏好（`backend/recommendation.py`）

### 快速開始
1) 建立虛擬環境並安裝依賴
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2) 可選：訓練分類模型（也可先跳過）
```bash
python ml/train_classifier.py
```
這會在 `ml/model.joblib` 生成模型，用於對文章分類。如果沒有模型，系統會回退為 `general` 類別。

3) 啟動後端
```bash
python backend/app.py
```
後端預設在 `http://127.0.0.1:5000`，提供簡單首頁以及 REST API。

4) 執行爬蟲導入新聞
```bash
python crawler/fetch_feeds.py
```
預設抓取 BBC/NYTimes 的 RSS，並呼叫後端 `/articles/bulk` 導入。

5) 在瀏覽器開啟
- `http://127.0.0.1:5000/`：最簡 UI，可建立使用者、瀏覽新聞、按喜好回饋。

### API 速覽
- POST `/users`：建立或取回使用者
  - 請求：`{ "email": "you@example.com", "preferences": { "technology": 1.5 } }`（`preferences` 可省略）
  - 回應：`{ "id": 1, "email": "you@example.com" }`
- GET `/articles?user_id=1&limit=50`：取得新聞（有 `user_id` 則為個人化排序）
- POST `/feedback`：回饋喜好
  - 請求：`{ "user_id": 1, "article_id": 123, "liked": true }`
- POST `/articles/bulk`：批量導入新聞（供爬蟲使用）

### 設計說明與延伸
- 分類：`ml/train_classifier.py` 使用 `LinearSVC + TF-IDF`。可替換為 spaCy、Transformers 或深度學習模型。
- 推薦：目前採內容/類別偏好 + 新聞時效加權。可延伸加入協同過濾、向量召回等。
- 資料庫：SQLite（`data/app.db`）。可改為 PostgreSQL，設定 `DATABASE_URL` 環境變數即可。

### 環境變數
- `PORT`：Flask 服務端口（預設 5000）
- `DATABASE_URL`：資料庫連線字串，預設為專案內 SQLite
- `BACKEND_URL`（爬蟲使用）：後端服務位址（預設 `http://127.0.0.1:5000`）

### 測試資料
- `ml/data/sample.csv` 供範例訓練用，類別包含 `technology`、`business`、`sports`、`entertainment`、`world`。

### 注意
- 若使用更大量爬取與部署，建議：
  - 使用佇列（如 Celery/RQ）與排程（cron）
  - 儲存全文正文、去重與來源歸一
  - 加入語言偵測、多語處理
  - 改善冷啟動與偏好冷啟策略（熱門/多樣性混排）
