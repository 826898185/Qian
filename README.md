# K13 Web MVP（K线 1+3 模型）

这是一个可运行的最小版本（MVP），包含：

- `backend`：FastAPI + K13 因子引擎 + 风险分级接口
- `frontend`：Vite + ECharts 可视化页面（K线、1/2/3 标注、支撑线、风险展示）

> 当前支持双数据源：`demo`（内置模拟）和 `tushare`（真实A股日线）。

## 目录结构

```text
.
├── backend
│   ├── app
│   │   ├── factor_engine.py   # 1+3规则与风险信号
│   │   ├── data_service.py    # 模拟行情数据服务
│   │   └── main.py            # API入口
│   └── requirements.txt
└── frontend
    ├── src
    │   ├── main.js            # 页面逻辑与图表渲染
    │   └── styles.css
    └── package.json
```

## 后端启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 可选：切换到 Tushare 数据源

在 `backend` 目录创建 `.env`（可复制 `.env.example`）：

```bash
K13_DATA_SOURCE=tushare
TUSHARE_TOKEN=你的token
# 可选：限定扫描股票池（逗号分隔；留空表示全A股）
# K13_SYMBOLS=600519.SH,000858.SZ,300750.SZ
# 可选：股票池上限（0 表示不限制，即全市场）
# K13_SCAN_LIMIT=0
# 可选：默认拉取日线长度
# K13_LOOKBACK_DAYS=260
```

然后启动：

```bash
cd backend
set -a
source .env
set +a
uvicorn app.main:app --reload --port 8000
```

后端 API：

- `GET /api/health`
- `GET /api/symbols`
- `GET /api/signals`
- `GET /api/stocks/{symbol}/patterns?lookback=220`
- `GET /api/stocks/{symbol}/risk?lookback=220`
- `POST /api/config`

其中 `GET /api/health` 会返回当前数据源（`demo/tushare`）及股票池过滤统计，方便你确认筛选是否生效。

### 全A股自动过滤规则（Tushare 模式）

当使用 `K13_DATA_SOURCE=tushare` 且未设置 `K13_SYMBOLS` 时，系统默认从全A股筛选：

1. 剔除 ST（名称包含 `ST` / `*ST`）  
2. 剔除上市不满 60 天  
3. 剔除停牌（以最近交易日成交量 `vol > 0` 作为可交易条件）

如需调试可设置 `K13_SCAN_LIMIT` 限制扫描数量；生产建议保持 `0`（全市场）。

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

前端通过 Vite 代理将 `/api` 请求转发到 `http://127.0.0.1:8000`。

## 你可以先验证的关键点

1. 左侧“今日动量信号榜”是否按 score 排序；
2. 右侧 K 线图是否标出“核心1、1、2、3”；
3. 支撑线是否展示为“3开盘/3收盘/1开盘/1收盘/1最低点”；
4. 风险标签是否随最新收盘位置变化（HOLD / WARN / REDUCE / SELL / SELL_HARD）。

## 下一步建议

1. 在 Tushare 模式下接入你的完整股票池（或指数成分股池）；
2. 在 `FactorConfig` 中继续细化你定义的“十字星、大阳/大阴合并重叠”等规则；
3. 增加每日定时任务（收盘后跑批）和历史回测页面。
