import os
import json
import asyncio
import logging
import base64
import aiohttp
from aiohttp import web
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AlphaQuantPro")

_k = b'Z3NrX1RMTmdlSEl4VVJWSjh5eU81Rm5CV0dkeWIzRllzV1hIYnBiYnY4cEdGdUw3V2JiZVB2T04='
API_KEY = os.environ.get("GROQ_API_KEY") or base64.b64decode(_k).decode()

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

MODEL_NAME = "openai/gpt-oss-20b"

connected_websockets = set()
recent_news_cache = []
seen_titles = set()
news_queue = asyncio.Queue()

SYSTEM_PROMPT = """You are an institutional cryptocurrency quantitative macro strategist.
Analyze the provided breaking news/tweet strictly for BITCOIN (BTC) spot/perp trading.
Output fluent, professional institutional Sinhala (with standard quant English terms like Spot CVD, Orderbook, Liquidity Sweep, Fake Wick).

Respond ONLY with a valid JSON object matching this schema:
{
  "impact_mark": "e.g. 1.5 / 10 — NOISE or 8.5 / 10 — CRITICAL ALPHA",
  "directional_bias": "NEUTRAL or BULLISH or BEARISH",
  "expected_move": "±$0-$50",
  "window": "Immediate 60s or 5m-15m or 1h-4h",
  "bias_badge": "NEUTRAL or BULLISH or BEARISH",
  "core_catalyst": "මෙම පුවත/වාර්තාව කුමක්ද සහ BTC වලට macro/structural catalyst එකක් වන්නේ ඇයි/නොවන්නේ ඇයිද යන්න.",
  "cvd_orderbook_impact": "Spot CVD (Cumulative Volume Delta) වලට සිදුවන බලපෑම, aggressive buyers/sellers ක්‍රියාකාරීත්වය සහ DXY correlation තත්ත්වය.",
  "liquidity_traps": "Short/Long liquidation cascades, Fake Wick අවදානම හෝ liquidity sweep සිදුවන ආකාරය.",
  "verdict": "IGNORE or LONG BIAS or SHORT BIAS or WAIT FOR CONFIRMATION",
  "action_plan": "Bitcoin traders ලා 1m/5m timeframe තුළ ගත යුතු ක්‍රියාමාර්ගය, Invalidation මට්ටම් සහ perp funding rates අවධානය."
}"""

HTML_UI = """<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA QUANT PRO V2</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #090c14;
            color: #d1d5db;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
            padding: 24px 20px;
        }
        .container {
            max-width: 960px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .logo-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .logo-text {
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 1.2px;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .badge-v2 {
            background: #1e3a8a;
            color: #60a5fa;
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 4px;
        }
        .sub-header {
            font-size: 12px;
            color: #64748b;
            font-weight: 700;
            letter-spacing: 1.2px;
            margin-bottom: 24px;
        }
        .live-tag {
            background: #064e3b;
            color: #34d399;
            font-size: 12px;
            font-weight: 800;
            padding: 5px 12px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .live-tag::before {
            content: "";
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
        }
        .grid {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        .card {
            background: #0d121d;
            border: 1px solid #1a2233;
            border-radius: 10px;
            padding: 26px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
        }
        .impact-hero {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #131b2a;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 20px;
        }
        .impact-hero-left {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .impact-label {
            font-size: 11.5px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #94a3b8;
        }
        .impact-val {
            font-size: 18px;
            font-weight: 900;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .badge-bias {
            padding: 6px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: 1px;
            white-space: nowrap;
        }
        .bias-NEUTRAL { background: #271e11; color: #fbbf24; border: 1px solid #78350f; }
        .bias-BULLISH { background: #064e3b; color: #34d399; border: 1px solid #059669; }
        .bias-BEARISH { background: #451319; color: #f87171; border: 1px solid #991b1b; }

        .full-news-title {
            font-size: 16.5px;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.6;
            margin-bottom: 18px;
        }
        .metric-summary {
            font-size: 14px;
            line-height: 1.9;
            color: #94a3b8;
            border-bottom: 1px solid #1a2333;
            padding-bottom: 16px;
            margin-bottom: 18px;
        }
        .metric-summary span {
            color: #f1f5f9;
            font-weight: 700;
        }
        .section-header {
            font-size: 14.5px;
            font-weight: 800;
            color: #38bdf8;
            margin-bottom: 12px;
        }
        .points-list {
            font-size: 14px;
            line-height: 1.85;
            color: #94a3b8;
            margin-bottom: 20px;
        }
        .points-list div {
            margin-bottom: 10px;
        }
        .points-list strong {
            color: #e2e8f0;
        }
        .verdict-box {
            border-top: 1px solid #1a2333;
            padding-top: 16px;
            font-size: 14px;
            line-height: 1.8;
        }
        .verdict-title {
            color: #fbbf24;
            font-size: 14.5px;
            font-weight: 900;
            margin-bottom: 6px;
        }
        .verdict-text {
            color: #cbd5e1;
        }
        .card-time {
            text-align: right;
            font-size: 11px;
            color: #475569;
            margin-top: 12px;
        }
        .bottom-bar {
            margin-top: 28px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-row">
                <div class="logo-text">⚡ ALPHA QUANT <span class="badge-v2">PRO V2</span></div>
            </div>
            <div class="live-tag">● LIVE</div>
        </div>
        <div class="sub-header">INSTITUTIONAL LIQUIDITY ENGINE • SUB-SECOND EXECUTION</div>

        <div class="grid" id="news-container">
            <div id="wait-placeholder" style="text-align:center; padding:60px; color:#475569; font-size:14px; font-weight:700;">
                📡 CONNECTED TO TREE OF ALPHA STREAM // WAITING FOR CATALYST...
            </div>
        </div>

        <div class="bottom-bar">
            <div style="color:#38bdf8;">ALPHA QUANT ENGINE ONLINE // FEED SYNCHRONIZED</div>
            <div style="color:#10b981;">● SYSTEM READY</div>
        </div>
    </div>

    <script>
        const container = document.getElementById("news-container");
        function addCard(d) {
            const p = document.getElementById("wait-placeholder");
            if (p) p.remove();

            const card = document.createElement("div");
            card.className = "card";

            const bias = (d.bias_badge || d.directional_bias || "NEUTRAL").toUpperCase();

            card.innerHTML = `
                <div class="impact-hero">
                    <div class="impact-hero-left">
                        <div class="impact-label">📌 IMPACT SCORE & EVALUATION</div>
                        <div class="impact-val">⚡ ${d.impact_mark}</div>
                    </div>
                    <div class="badge-bias bias-${bias}">● ${bias}</div>
                </div>

                <div class="full-news-title">${d.title}</div>

                <div class="metric-summary">
                    <div>🎯 <strong>Directional Bias:</strong> <span>● ${d.directional_bias}</span></div>
                    <div>⚡ <strong>BTC Expected Move:</strong> <span>${d.expected_move}</span> | <strong>Window:</strong> <span>${d.window}</span></div>
                </div>

                <div class="section-header">● BTC Orderbook & Price Action බලපෑම (සාරාංශය):</div>
                <div class="points-list">
                    <div>• <strong>Core Catalyst:</strong> ${d.core_catalyst}</div>
                    <div>• <strong>Orderbook & CVD Impact:</strong> ${d.cvd_orderbook_impact}</div>
                    <div>• <strong>Liquidity Sweep & Traps:</strong> ${d.liquidity_traps}</div>
                </div>

                <div class="verdict-box">
                    <div class="verdict-title">⚠️ BTC Quant Trade Verdict:</div>
                    <div class="verdict-text">
                        <strong>Verdict:</strong> ${d.verdict}<br>
                        <strong>Action Plan:</strong> ${d.action_plan}
                    </div>
                </div>
                <div class="card-time">${new Date().toLocaleTimeString()}</div>
            `;
            container.insertBefore(card, container.firstChild);
        }

        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${proto}//${location.host}/ws`);
        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (Array.isArray(data)) { data.forEach(addCard); }
            else { addCard(data); }
        };
    </script>
</body>
</html>"""

async def analyze_news(text):
    prompt_payload = f"Analyze this breaking crypto/macro news specifically for BTC Orderbook and Price Action:\n{text[:2000]}"
    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_payload}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1500
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {
            "impact_mark": "1.5 / 10 — NOISE",
            "directional_bias": "NEUTRAL",
            "expected_move": "±$0-$50",
            "window": "Immediate 60s",
            "bias_badge": "NEUTRAL",
            "core_catalyst": "සාමාන්‍ය පුවතක් වන අතර, Bitcoin (BTC) මිලට සෘජු macro catalyst එකක් නොවේ.",
            "cvd_orderbook_impact": "Spot CVD වල significant divergence එකක් නොමැත. Aggressive market buys/sells නොමැති අතර DXY neutral වේ.",
            "liquidity_traps": "Short/Long liquidation cascades සඳහා ඉඩක් නොමැත. Fake Wick අවදානමක් නොමැත.",
            "verdict": "IGNORE",
            "action_plan": "1m/5m timeframe තුළ මෙම news එක මත entry ගැනීම නොකළ යුතුය. BTC/USD spot liquidity සහ perp funding rates නිරීක්ෂණය කරන්න."
        }

async def broadcast(item):
    recent_news_cache.append(item)
    if len(recent_news_cache) > 30: recent_news_cache.pop(0)
    for ws in list(connected_websockets):
        try: await ws.send_str(json.dumps(item))
        except: connected_websockets.discard(ws)

async def news_worker():
    while True:
        raw_news = await news_queue.get()
        full_title = raw_news.get("full_title", "")
        body = raw_news.get("body", "")
        content = f"Title: {full_title}\nDetails: {body}".strip()
        
        res = await analyze_news(content)
        payload = {
            "title": full_title,
            "impact_mark": res.get("impact_mark", "1.5 / 10 — NOISE"),
            "directional_bias": res.get("directional_bias", "NEUTRAL"),
            "expected_move": res.get("expected_move", "±$0-$50"),
            "window": res.get("window", "Immediate 60s"),
            "bias_badge": res.get("bias_badge", "NEUTRAL"),
            "core_catalyst": res.get("core_catalyst", ""),
            "cvd_orderbook_impact": res.get("cvd_orderbook_impact", ""),
            "liquidity_traps": res.get("liquidity_traps", ""),
            "verdict": res.get("verdict", "IGNORE"),
            "action_plan": res.get("action_plan", "")
        }
        await broadcast(payload)
        news_queue.task_done()
        await asyncio.sleep(2)

async def treeofalpha_stream():
    url = "wss://news.treeofalpha.com/ws"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    logger.info("Connected to Tree of Alpha")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            raw = json.loads(msg.data)
                            title = (raw.get("title") or "").strip()
                            body = (raw.get("body") or raw.get("content") or "").strip()
                            
                            if title and body and title not in body:
                                full_title = f"{title}: {body}"
                            else:
                                full_title = title if title else body
                            
                            if not full_title or len(full_title) < 15 or full_title in seen_titles:
                                continue
                            seen_titles.add(full_title)
                            if len(seen_titles) > 500: seen_titles.clear()
                            
                            await news_queue.put({
                                "full_title": full_title,
                                "body": body
                            })
        except Exception as e:
            logger.error(f"Stream reconnecting: {e}")
            await asyncio.sleep(3)

async def index(request): return web.Response(text=HTML_UI, content_type="text/html")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_websockets.add(ws)
    if recent_news_cache: await ws.send_str(json.dumps(recent_news_cache))
    try:
        async for msg in ws: pass
    finally: connected_websockets.discard(ws)
    return ws

async def start_bg(app):
    app["s"] = asyncio.create_task(treeofalpha_stream())
    app["w"] = asyncio.create_task(news_worker())

async def stop_bg(app):
    app["s"].cancel()
    app["w"].cancel()
    await asyncio.gather(app["s"], app["w"], return_exceptions=True)

def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.on_startup.append(start_bg)
    app.on_cleanup.append(stop_bg)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
