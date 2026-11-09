# Wealth- Forex Analysis MVP

A small Flask dashboard that calculates **experimental BUY / SELL / HOLD indicators** for selected currency pairs. It combines hourly Yahoo Finance price history with basic keyword scoring of Google News RSS headlines. It does not execute trades.

## Important—read before using

This does **not** provide 100% accurate signals. No forex system can promise no false signals or guaranteed profit. The scoring is a simple, unvalidated heuristic—not a probability or calibrated confidence estimate. News keyword matching can misread context, and free data feeds can be delayed, missing, or changed. The displayed stop/target levels are illustrative ATR calculations, not a recommendation. Test in a backtest and paper-trading account before considering any real-money use. Leveraged forex trading can lose money rapidly.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
DEMO=1 python app.py
```

Open `http://localhost:5000`. `DEMO=1` uses synthetic prices and a sample headline; it is only for checking the app, not market analysis. For live-source mode, omit `DEMO=1`. Yahoo Finance and Google News RSS are free/unofficial sources with no uptime or latency guarantee.

## Deploy on Render

The included `render.yaml` describes a free web service. Connect this repository to Render and deploy the blueprint. Free instances may sleep, delaying background refreshes; this is not a real-time alerting or execution service. Change `PAIRS` and `REFRESH_MIN` in the service environment if needed. Refresh intervals below five minutes are clamped to five minutes.

## Endpoints

- `/` — dashboard
- `/api/signals` — current analysis as JSON, including source candle time and any warnings
- `/health` — health check (does not guarantee that market feeds are available)

The app only analyzes supported six-character currency pairs composed of USD, EUR, GBP, JPY, AUD, CAD, and CHF. Use a provider with suitable licensing, reliable timestamps, and a documented API if you need production-grade data. This MVP deliberately has no broker connection or automatic order placement.
