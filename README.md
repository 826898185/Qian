# K13 Web MVP（K线 1+3 模型）

这是一个可运行的最小版本（MVP），包含：

- `backend`：FastAPI + K13 因子引擎 + 风险分级接口
- `frontend`：Vite + ECharts 可视化页面（K线、1/2/3 标注、支撑线、风险展示）

> 当前使用内置模拟数据源（A股代码风格），便于你先验证规则和交互。后续可无缝替换为 Tushare / AkShare / 自有数据库。

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

后端 API：

- `GET /api/health`
- `GET /api/symbols`
- `GET /api/signals`
- `GET /api/stocks/{symbol}/patterns?lookback=220`
- `GET /api/stocks/{symbol}/risk?lookback=220`
- `POST /api/config`

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

1. 将 `DataService` 替换为真实行情源；
2. 在 `FactorConfig` 中继续细化你定义的“十字星、大阳/大阴合并重叠”等规则；
3. 增加每日定时任务（收盘后跑批）和历史回测页面。
