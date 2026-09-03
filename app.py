import os
import re
import json
import asyncio
import logging
import base64
import aiohttp
from aiohttp import web
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MacroTerminal")

_k = b'Z3NrX1RMTmdlSEl4VVJWSjh5eU81Rm5CV0dkeWIzRllzV1hIYnBiYnY4cEdGdUw3V2JiZVB2T04='
API_KEY = os.environ.get("GROQ_API_KEY") or base64.b64decode(_k).decode()

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

MODEL_NAME = "qwen/qwen3.6-27b"

connected_websockets = set()
recent_news_cache = []
seen_titles = set()
news_queue = asyncio.Queue()

SYSTEM_PROMPT = """You are an institutional quantitative crypto macro analyst running a tier-1 trading terminal.
Analyze the given breaking crypto/financial news strictly in fluent, natural Sinhala. Never mention any AI model or provider name.

Respond strictly in this exact format:
TIMING_BANNER: [BREAKING or PRICED_IN]
IMPACT_TIER: [HIGH or MEDIUM or LOW]
IMPACT_SCORE: [Number between 1 and 10]/10
MARKET_BIAS: [BULLISH or BEARISH or NEUTRAL]
EXPECTED_MOVE: [e.g. ±$200 - $500 or ±$0 - $0]
TIME_HORIZON: [e.g. ඉදිරි පැය 1-4 තුළ or දැනටමත් සිදුවී ඇත or ඉදිරි දින කිහිපය]

ANALYSIS_BODY:
• සෘජු බලපෑම (Direct Impact): [කෙටි පැහැදිලි කිරීමක්]
• ඇයි මෙහෙම වුණේ? (The Fundamental "Why"): [ආර්ථික හෝ වෙළඳපල පසුබිම]
• කාලීන අවදානම (Timing & Late-Chasing Trap): [ප්‍රමාද වී trade කිරීමේ අවදානම හෝ signal එක]"""

HTML_UI = """<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA QUANT // PRO MACRO TERMINAL</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #080b11;
            color: #d1d5db;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 24px;
        }
        .header {
            max-width: 960px;
            margin: 0 auto 24px auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo {
            font-size: 19px;
            font-weight: 800;
            color: #38bdf8;
            letter-spacing: 1.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .live-badge {
            background: #052e16;
            border: 1px solid #15803d;
            color: #4ade80;
            font-size: 11px;
            font-weight: 700;
            padding: 5px 12px;
            border-radius: 9999px;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .live-badge::before {
            content: "";
            width: 7px;
            height: 7px;
            background: #22c55e;
            border-radius: 50%;
            box-shadow: 0 0 8px #22c55e;
        }
        .grid {
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-width: 960px;
            margin: 0 auto;
        }
        .card {
            background: #0d121d;
            border: 1px solid #1b2434;
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }
        .banner-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 18px;
        }
        .banner-box {
            flex: 1;
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 700;
            line-height: 1.4;
        }
        .banner-BREAKING {
            background: #3f1219;
            color: #fca5a5;
            border: 1px solid #7f1d1d;
        }
        .banner-PRICED_IN {
            background: #2a1f0a;
            color: #fde047;
            border: 1px solid #78350f;
        }
        .tier-pill {
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }
        .tier-LOW { background: #13241b; color: #4ade80; border: 1px solid #1e3a29; }
        .tier-MEDIUM { background: #261f0e; color: #fbbf24; border: 1px solid #453313; }
        .tier-HIGH { background: #2d1217; color: #f87171; border: 1px solid #4c1d24; }
        .news-title {
            font-size: 17px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 18px;
            line-height: 1.45;
        }
        .divider {
            height: 1px;
            background: #1e293b;
            margin-bottom: 18px;
        }
        .metrics-grid {
            display: flex;
            flex-direction: column;
            gap: 8px;
            font-size: 13.5px;
            color: #e2e8f0;
            margin-bottom: 18px;
        }
        .metric-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .metric-label {
            color: #94a3b8;
        }
        .metric-val {
            font-weight: 600;
            color: #f1f5f9;
        }
        .section-title {
            font-size: 13.5px;
            font-weight: 700;
            color: #cbd5e1;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .analysis-text {
            font-size: 13.5px;
            line-height: 1.8;
            color: #94a3b8;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">⚡ ALPHA QUANT // PRO MACRO TERMINAL</div>
        <div class="live-badge">LIVE STREAMING</div>
    </div>
    <div class="grid" id="news-container"></div>
    <script>
        const container = document.getElementById("news-container");
        function addCard(item) {
            const card = document.createElement("div");
            card.className = "card";
            
            const isBreaking = item.timing_status === "BREAKING";
            const bannerClass = isBreaking ? "banner-BREAKING" : "banner-PRICED_IN";
            const bannerText = isBreaking 
                ? "⚡ BREAKING ALPHA: ක්ෂණික වෙළඳපල චලනයක් (High Momentum Setup)" 
                : "⚠️ PRICED-IN / LATE RECAP: වෙළඳපලේ දැනටමත් වෙලා ඉවරයි (Trade එකක් ගන්න එපා - Trap එකක්)";
            
            const tier = item.tier || "LOW";
            const tierLabel = tier === "LOW" ? "● LOW (NOISE)" : (tier === "HIGH" ? "● HIGH (ALPHA)" : "● MEDIUM (WATCH)");

            card.innerHTML = `
                <div class="banner-row">
                    <div class="banner-box ${bannerClass}">${bannerText}</div>
                    <div class="tier-pill tier-${tier}">${tierLabel}</div>
                </div>
                <div class="news-title">${item.title}</div>
                <div class="divider"></div>
                <div class="metrics-grid">
                    <div class="metric-row"><span class="metric-label">📌 බලපෑම් ලකුණු (Impact Score) :</span> <span class="metric-val">${item.score || "2/10"}</span></div>
                    <div class="metric-row"><span class="metric-label">📊 වෙළඳපල දිශාව (Market Bias) :</span> <span class="metric-val">${item.bias || "NEUTRAL"}</span></div>
                    <div class="metric-row"><span class="metric-label">⚡ අපේක්ෂිත BTC චලනය (Expected Move) :</span> <span class="metric-val">${item.expected_move || "±$0 - $0"}</span></div>
                    <div class="metric-row"><span class="metric-label">⏱️ ක්‍රියාකාරී කාලය (Time Horizon) :</span> <span class="metric-val">${item.horizon || "දැනටමත් සිදුවී ඇත"}</span></div>
                </div>
                <div class="section-title">📊 1. ගැඹුරු වෙළඳපල හා Orderbook විශ්ලේෂණය (Deep Microstructure & Macro):</div>
                <div class="analysis-text">${item.analysis}</div>
            `;
            container.insertBefore(card, container.firstChild);
        }
        function connect() {
            const proto = location.protocol === "https:" ? "wss:" : "ws:";
            const ws = new WebSocket(`${proto}//${location.host}/ws`);
            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                if (Array.isArray(data)) { data.forEach(addCard); }
                else { addCard(data); }
            };
            ws.onclose = () => setTimeout(connect, 3000);
        }
        connect();
    </script>
</body>
</html>"""

async def analyze_news(full_text):
    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"News Headline/Text:\n{full_text[:450]}"}
            ],
            temperature=0.25,
            max_tokens=1500
        )
        raw = completion.choices[0].message.content
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        
        timing = "PRICED_IN"
        tier = "LOW"
        score = "2/10"
        bias = "NEUTRAL"
        move = "±$0 - $0"
        horizon = "දැනටමත් සිදුවී ඇත"
        analysis_body = []
        
        in_body = False
        for line in raw.splitlines():
            line_str = line.strip()
            if "TIMING_BANNER:" in line_str:
                timing = "BREAKING" if "BREAKING" in line_str.upper() else "PRICED_IN"
            elif "IMPACT_TIER:" in line_str:
                t = line_str.upper()
                tier = "HIGH" if "HIGH" in t else ("MEDIUM" if "MEDIUM" in t else "LOW")
            elif "IMPACT_SCORE:" in line_str:
                score = line_str.split(":", 1)[1].strip()
            elif "MARKET_BIAS:" in line_str:
                bias = line_str.split(":", 1)[1].strip()
            elif "EXPECTED_MOVE:" in line_str:
                move = line_str.split(":", 1)[1].strip()
            elif "TIME_HORIZON:" in line_str:
                horizon = line_str.split(":", 1)[1].strip()
            elif "ANALYSIS_BODY:" in line_str:
                in_body = True
            elif in_body:
                analysis_body.append(line)
                
        body_text = "\n".join(analysis_body).strip()
        if not body_text:
            body_text = "• සෘජු බලපෑම (Direct Impact): සෘජු වෙළඳපල බලපෑමක් නොමැත.\n• ඇයි මෙහෙම වුණේ? (The Fundamental \"Why\"): සාමාන්‍ය ප්‍රකාශයක් පමණි.\n• කාලීන අවදානම (Timing & Late-Chasing Trap): වෙළඳපලට ක්ෂණික අවදානමක් නොමැත."
            
        return timing, tier, score, bias, move, horizon, body_text
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return "PRICED_IN", "LOW", "1/10", "NEUTRAL", "±$0", "දැනටමත් සිදුවී ඇත", f"• විශ්ලේෂණ දෝෂයකි: {e}"

async def broadcast(item):
    recent_news_cache.append(item)
    if len(recent_news_cache) > 30:
        recent_news_cache.pop(0)
    for ws in list(connected_websockets):
        try:
            await ws.send_str(json.dumps(item))
        except Exception:
            connected_websockets.discard(ws)

async def news_worker():
    while True:
        raw_news = await news_queue.get()
        title = raw_news.get("title")
        timing, tier, score, bias, move, horizon, analysis = await analyze_news(title)
        payload = {
            "title": title,
            "time": raw_news.get("time", 0),
            "timing_status": timing,
            "tier": tier,
            "score": score,
            "bias": bias,
            "expected_move": move,
            "horizon": horizon,
            "analysis": analysis
        }
        await broadcast(payload)
        news_queue.task_done()
        await asyncio.sleep(2.1)

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
                            title = (raw.get("title") or raw.get("body", "") or "").strip()
                            if not title or len(title) < 15 or title in seen_titles:
                                continue
                            seen_titles.add(title)
                            if len(seen_titles) > 500:
                                seen_titles.clear()
                            
                            await news_queue.put({
                                "title": title,
                                "time": raw.get("time", 0)
                            })
        except Exception as e:
            logger.error(f"Stream reconnecting: {e}")
            await asyncio.sleep(3)

async def index(request):
    return web.Response(text=HTML_UI, content_type="text/html")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_websockets.add(ws)
    if recent_news_cache:
        await ws.send_str(json.dumps(recent_news_cache))
    try:
        async for msg in ws:
            pass
    finally:
        connected_websockets.discard(ws)
    return ws

async def start_background(app):
    app["stream_task"] = asyncio.create_task(treeofalpha_stream())
    app["worker_task"] = asyncio.create_task(news_worker())

async def cleanup_background(app):
    app["stream_task"].cancel()
    app["worker_task"].cancel()
    await asyncio.gather(app["stream_task"], app["worker_task"], return_exceptions=True)

def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.on_startup.append(start_background)
    app.on_cleanup.append(cleanup_background)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    web.run_app(create_app(), host="0.0.0.0", port=port)
