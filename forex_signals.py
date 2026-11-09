#!/usr/bin/env python3
"""Experimental forex analysis: price trend + simple RSS headline scoring.

This is educational software, not financial advice or an automated trading system.
Signals can be wrong. It does not execute orders. Yahoo Finance and Google News
RSS are unofficial/free sources and may be delayed, incomplete, or unavailable.

Install: pip install -r requirements.txt
Run locally: DEMO=1 python app.py  (synthetic data; no internet required)
"""
import html
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DEFAULT_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
TECH_WEIGHT, NEWS_WEIGHT = 0.7, 0.3
THRESHOLD = 0.25
SL_ATR, TP_ATR = 1.5, 2.5
MIN_BARS = 60
MAX_DATA_AGE_HOURS = 4
CCY_KEYS = {
    "USD": ["fed", "dollar", "usd", "powell", "treasury", "payroll"],
    "EUR": ["ecb", "euro", "eur", "lagarde", "eurozone"],
    "GBP": ["boe", "bank of england", "pound", "sterling", "gbp", "bailey"],
    "JPY": ["boj", "yen", "jpy", "ueda"],
    "AUD": ["rba", "aussie", "aud", "australia"],
    "CAD": ["boc", "loonie", "cad", "canada", "canadian"],
    "CHF": ["snb", "franc", "chf", "swiss"],
}
POS = ["hike", "hawkish", "raises rates", "strong", "beats", "surge", "rises", "growth", "rally", "gains", "jumps", "upbeat", "higher inflation", "stronger"]
NEG = ["cut", "dovish", "slashes", "weak", "misses", "falls", "slump", "recession", "slows", "drops", "losses", "downbeat", "weaker", "slides"]


def get_prices(pair, demo=False):
    if len(pair) != 6 or pair[:3] not in CCY_KEYS or pair[3:] not in CCY_KEYS:
        raise ValueError(f"Unsupported currency pair: {pair}; use six-letter pairs from supported currencies")
    if demo:
        seed = sum((i + 1) * ord(ch) for i, ch in enumerate(pair))
        rng = np.random.default_rng(seed)
        n = 500
        close = 1.1 * np.exp(np.cumsum(rng.normal(0.0001, 0.0015, n)))
        idx = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n, freq="h")
        df = pd.DataFrame({"Close": close}, index=idx)
        df["High"] = df.Close * (1 + abs(rng.normal(0, 0.0008, n)))
        df["Low"] = df.Close * (1 - abs(rng.normal(0, 0.0008, n)))
        return df
    import yfinance as yf
    df = yf.download(f"{pair}=X", period="60d", interval="1h", progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    required = {"Close", "High", "Low"}
    if df.empty or not required.issubset(df.columns):
        raise RuntimeError(f"No usable price data for {pair} from Yahoo Finance")
    return df.dropna(subset=["Close", "High", "Low"])


def get_headlines(ccy, demo=False):
    if demo:
        return ["Fed signals rate cut as jobs growth slows"] if ccy == "USD" else []
    import requests
    query = f'{ccy} {CCY_KEYS[ccy][0]} forex when:1d'.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; WealthForexSignals/1.0)"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return [item.findtext("title", "") for item in root.iter("item")][:15]


def rsi(series, n=14):
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def technical(df):
    if len(df) < MIN_BARS:
        raise ValueError(f"Insufficient price history ({len(df)} bars; need {MIN_BARS})")
    close = df["Close"].astype(float)
    ema20, ema50 = close.ewm(span=20, adjust=False).mean(), close.ewm(span=50, adjust=False).mean()
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    r = float(rsi(close).iloc[-1])
    tr = pd.concat([df.High - df.Low, (df.High - close.shift()).abs(), (df.Low - close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    if not np.isfinite(r) or not np.isfinite(atr) or atr <= 0:
        raise ValueError("Indicators could not be calculated from current price history")
    score, why = 0.0, []
    if ema20.iloc[-1] > ema50.iloc[-1]:
        score += 0.4; why.append("uptrend (EMA20 above EMA50)")
    else:
        score -= 0.4; why.append("downtrend (EMA20 below EMA50)")
    if hist.iloc[-1] > 0:
        score += 0.3; why.append("MACD momentum positive")
    else:
        score -= 0.3; why.append("MACD momentum negative")
    if r < 30:
        score += 0.3; why.append(f"RSI {r:.0f} oversold")
    elif r > 70:
        score -= 0.3; why.append(f"RSI {r:.0f} overbought")
    else:
        why.append(f"RSI {r:.0f} neutral")
    return score, atr, why


def headline_score(headline):
    text = headline.lower()
    return sum(word in text for word in POS) - sum(word in text for word in NEG)


def currency_sentiment(ccy, demo=False):
    try:
        headlines = get_headlines(ccy, demo)
    except Exception:
        return 0.0, 0, "news feed unavailable"
    relevant = [h for h in headlines if any(k in h.lower() for k in CCY_KEYS[ccy])]
    if not relevant:
        return 0.0, 0, "no relevant headlines"
    value = float(np.clip(np.mean([headline_score(h) for h in relevant]) / 2, -1, 1))
    return value, len(relevant), None


def analyse(pair, demo=False):
    pair = pair.upper()
    base, quote = pair[:3], pair[3:]
    df = get_prices(pair, demo)
    tech, atr, why = technical(df)
    nb, base_count, base_warning = currency_sentiment(base, demo)
    nq, quote_count, quote_warning = currency_sentiment(quote, demo)
    news = float(np.clip(nb - nq, -1, 1))
    score = TECH_WEIGHT * tech + NEWS_WEIGHT * news
    price = float(df["Close"].iloc[-1])
    signal = "BUY" if score > THRESHOLD else "SELL" if score < -THRESHOLD else "HOLD"
    timestamp = df.index[-1]
    if getattr(timestamp, "tzinfo", None) is None:
        timestamp = timestamp.tz_localize("UTC")
    age = (pd.Timestamp.now(tz="UTC") - timestamp).total_seconds() / 3600
    warnings = []
    if age > MAX_DATA_AGE_HOURS:
        signal = "HOLD"
        warnings.append("price data is stale; no trade signal")
    for item in (base_warning, quote_warning):
        if item:
            warnings.append(item)
    # News feed outages/missing headlines must not be presented as confirmed news neutrality.
    if base_warning == "news feed unavailable" or quote_warning == "news feed unavailable":
        warnings.append("news unavailable; score is based on incomplete information")
    sl = tp = None
    if signal != "HOLD":
        direction = 1 if signal == "BUY" else -1
        sl, tp = price - direction * SL_ATR * atr, price + direction * TP_ATR * atr
    return {
        "pair": pair, "price": price, "signal": signal, "score": score,
        "tech": tech, "news": news, "sl": sl, "tp": tp,
        "why": why, "base": (base, nb), "quote": (quote, nq),
        "series": df.Close.tail(120).astype(float).tolist(),
        "ema20": df.Close.ewm(span=20, adjust=False).mean().tail(120).astype(float).tolist(),
        "ema50": df.Close.ewm(span=50, adjust=False).mean().tail(120).astype(float).tolist(),
        "data_time": timestamp.isoformat(), "data_age_hours": round(age, 1),
        "news_count": base_count + quote_count,
        "warning": "; ".join(dict.fromkeys(warnings)) or None,
    }


def escape_text(text):
    return html.escape(str(text))


CSS = """
:root{--bg:#f4f5f7;--card:#fff;--text:#1a1d23;--mute:#6b7280;--line:#e5e7eb;--buy:#16a34a;--sell:#dc2626;--hold:#9ca3af;--p:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#181b21;--text:#e8eaed;--mute:#9aa0a6;--line:#2a2e36;--buy:#22c55e;--sell:#f87171;--hold:#6b7280;--p:#60a5fa}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif}h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mute);margin-bottom:16px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}.top{display:flex;justify-content:space-between;align-items:center}.pair{font-weight:700;font-size:17px}.price{color:var(--mute);font-size:13px}.badge{color:#fff;font-weight:700;padding:3px 12px;border-radius:99px;font-size:13px}.BUY{background:var(--buy)}.SELL{background:var(--sell)}.HOLD{background:var(--hold)}.bar{position:relative;height:8px;background:var(--line);border-radius:4px;margin:12px 0 4px}.bar i{position:absolute;top:0;bottom:0;border-radius:4px}.bar b{position:absolute;left:50%;top:-3px;bottom:-3px;width:2px;background:var(--mute)}.row{display:flex;justify-content:space-between;color:var(--mute);font-size:12px}.why{font-size:12px;color:var(--mute);margin:8px 0}.lv{display:flex;gap:14px;font-size:12px;margin-top:6px}.warning{color:#b45309;font-size:12px;margin-top:6px}svg{width:100%;height:90px;display:block;margin-top:8px}.notice{border:1px solid var(--line);border-radius:8px;padding:10px;margin:0 0 14px;color:var(--mute)}
"""


def spark(result):
    values = result["series"] + result["ema20"] + result["ema50"]
    lo, hi = min(values), max(values)
    def points(series):
        n = len(series)
        return " ".join(f"{i * 300 / max(n - 1, 1):.1f},{88 - (x - lo) / (hi - lo or 1) * 84:.1f}" for i, x in enumerate(series))
    return ('<svg viewBox="0 0 300 90" preserveAspectRatio="none" aria-label="Price chart">'
            f'<polyline points="{points(result["series"])}" fill="none" stroke="var(--text)" stroke-width="1.5"/>'
            f'<polyline points="{points(result["ema20"])}" fill="none" stroke="var(--p)" stroke-width="1"/>'
            f'<polyline points="{points(result["ema50"])}" fill="none" stroke="var(--hold)" stroke-width="1" stroke-dasharray="3 2"/></svg>')


def render_dashboard(results, updated=None):
    cards = []
    for r in results:
        decimals = 3 if r["pair"].endswith("JPY") else 5
        width = min(abs(r["score"]), 1) * 50
        left = 50 if r["score"] >= 0 else 50 - width
        color = "var(--buy)" if r["score"] >= 0 else "var(--sell)"
        levels = f'<div class="lv"><span>Illustrative stop {r["sl"]:.{decimals}f}</span><span>Illustrative target {r["tp"]:.{decimals}f}</span></div>' if r["sl"] is not None else ""
        warning = f'<div class="warning">{escape_text(r["warning"])}</div>' if r.get("warning") else ""
        cards.append(f'<section class="card"><div class="top"><div><div class="pair">{escape_text(r["pair"])}</div><div class="price">{r["price"]:.{decimals}f}</div></div><span class="badge {r["signal"]}">{r["signal"]}</span></div>'
            f'<div class="bar"><b></b><i style="left:{left}%;width:{width}%;background:{color}"></i></div>'
            f'<div class="row"><span>SELL</span><span>score {r["score"]:+.2f}</span><span>BUY</span></div>'
            f'<div class="row" style="margin-top:6px"><span>Technical {r["tech"]:+.2f}</span><span>News {r["news"]:+.2f}</span></div>'
            f'<div class="why">{escape_text(", ".join(r["why"]))}<br>{r["base"][0]} headline score {r["base"][1]:+.2f} · {r["quote"][0]} headline score {r["quote"][1]:+.2f}<br>Price candle: {escape_text(r["data_time"])}</div>{warning}{spark(r)}{levels}</section>')
    stamp = escape_text(updated or "unknown")
    page = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="300"><title>Experimental Forex Analysis</title>'
            f'<style>{CSS}</style></head><body><h1>Experimental Forex Analysis</h1><div class="sub">Dashboard refreshed: {stamp} · Analysis refreshes every 15 minutes by default.</div>'
            '<p class="notice"><strong>Important:</strong> These are unvalidated experimental indicators, not guaranteed predictions or financial advice. They can be wrong; price/news feeds may be delayed or incomplete. No trades are placed. Verify data and manage risk independently.</p>'
            f'<main class="grid">{"".join(cards)}</main></body></html>')
    return page
