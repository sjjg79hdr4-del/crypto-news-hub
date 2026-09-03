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

SYSTEM_PROMPT = """You are an institutional crypto analyst.
Analyze the provided tweet/news headline strictly in fluent, natural Sinhala.
Read the ACTUAL news content carefully. Never return generic placeholders.

Respond strictly in this format:
STATUS: [BREAKING or PRICED_IN]
TIER: [HIGH or MEDIUM or LOW]
SCORE: [1-10]/10
BIAS: [BULLISH or BEARISH or NEUTRAL]
MOVE: [e.g. ±$300 - $800 or ±$0 - $50]
HORIZON: [e.g. ඉදිරි පැය කිහිපය තුළ or දැනටමත් අවසන්]

• සෘජු බලපෑම (Direct Impact): [Tweet එකේ කියන දේ වෙළඳපලට බලපාන හැටි]
• ඇයි මෙහෙම වුණේ? (The Fundamental "Why"): [සිදුවීම පිටුපස ඇති සැබෑ ආර්ථික හෝ නීතිමය හේතුව]
• කාලීන අවදානම (Timing & Late-Chasing Trap): [දැන් trade එකක් ගත්තොත් trap වෙයිද නැද්ද යන්න]"""

HTML_UI = """<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA QUANT // PRO MACRO TERMINAL</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #080c13;
            color: #d1d5db;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 30px 20px;
        }
        .header {
            max-width: 900px;
            margin: 0 auto 24px auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo {
            font-size: 19px;
            font-weight: 800;
            color: #38bdf8;
            letter-spacing: 1.2px;
        }
        .live-badge {
            background: #064e3b;
            color: #34d399;
            font-size: 11px;
            font-weight: 700;
            padding: 5px 14px;
            border-radius: 9999px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .live-badge::before {
            content: "";
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 6px #10b981;
        }
        .grid {
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-width: 900px;
            margin: 0 auto;
        }
        .card {
            background: #0e1422;
            border: 1px solid #1a2233;
            border-radius: 8px;
            padding: 24px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45);
        }
        .banner-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
            margin-bottom: 16px;
        }
        .banner-box {
            flex: 1;
            padding: 10px 14px;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 700;
        }
        .banner-BREAKING { background: #3f1219; color: #fca5a5; border: 1px solid #7f1d1d; }
        .banner-PRICED_IN { background: #251c09; color: #fef08a; border: 1px solid #78350f; }
        .tier-pill {
            padding: 6px 14px;
            border-radius: 4px;
            font-size: 11.5px;
            font-weight: 800;
            white-space: nowrap;
        }
        .tier-LOW { background: #0f2318; color: #4ade80; border: 1px solid #14532d; }
        .tier-MEDIUM { background: #261f0e; color: #fbbf24; border: 1px solid #78350f; }
        .tier-HIGH { background: #2d1217; color: #f87171; border: 1px solid #7f1d1d; }
        .source-tag { font-size: 12px; color: #38bdf8; font-weight: 700; margin-bottom: 6px; }
        .news-title { font-size: 17px; font-weight: 700; color: #ffffff; margin-bottom: 14px; line-height: 1.5; }
        .tweet-box {
            background: #090d16;
            border-left: 3px solid #38bdf8;
            padding: 12px 14px;
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 18px;
            white-space: pre-wrap;
        }
        .divider { height: 1px; background: #1e293b; margin-bottom: 18px; }
        .metrics-grid {
            display: flex;
            flex-direction: column;
            gap: 8px;
            font-size: 13.5px;
            margin-bottom: 20px;
        }
        .metric-row { display: flex; align-items: center; gap: 6px; }
        .metric-label { color: #94a3b8; }
        .metric-val { font-weight: 700; color: #ffffff; }
        .section-title { font-size: 13.5px; font-weight: 700; color: #cbd5e1; margin-bottom: 12px; }
        .analysis-text { font-size: 14px; line-height: 1.85; color: #cbd5e1; white-space: pre-wrap; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">⚡ ALPHA QUANT // PRO MACRO TERMINAL</div>
        <div class="live-badge">● LIVE STREAMING</div>
    </div>
    <div class="grid" id="news-container">
        <div id="loading-state" style="text-align:center; padding: 60px 20px; color:#64748b;">
            📡 සජීවී පුවත් සංග්‍රහයට සම්බන්ධ වී ඇත. අලුත් පුවතක් පැමිණි විගස විශ්ලේෂණය මෙහි දිස්වනු ඇත...
        </div>
    </div>
    <script>
        const container = document.getElementById("news-container");
        function addCard(item) {
            const loader = document.getElementById("loading-state");
            if (loader) loader.remove();

            const card = document.createElement("div");
            card.className = "card";
            const isBreaking = item.status === "BREAKING";
            const bannerClass = isBreaking ? "banner-BREAKING" : "banner-PRICED_IN";
            const bannerText = isBreaking 
                ? "⚡ BREAKING ALPHA: ක්ෂණික වෙළඳපල චලනයක් (High Momentum Setup)" 
                : "⚠️ PRICED-IN / LATE RECAP: වෙළඳපලේ දැනටමත් වෙලා ඉවරයි (Trade එකක් ගන්න එපා - Trap එකක්)";

            const tier = item.tier || "LOW";
            const tierLabel = tier === "LOW" ? "● LOW (NOISE)" : (tier === "HIGH" ? "● HIGH (ALPHA)" : "● MEDIUM (WATCH)");

            const tweetBox = item.raw_body ? `<div class="tweet-box">💬 ${item.raw_body}</div>` : '';

            card.innerHTML = `
                <div class="banner-row">
                    <div class="banner-box ${bannerClass}">${bannerText}</div>
                    <div class="tier-pill tier-${tier}">${tierLabel}</div>
                </div>
                <div class="source-tag">📌 SOURCE: ${item.source}</div>
                <div class="news-title">${item.title}</div>
                ${tweetBox}
                <div class="divider"></div>
                <div class="metrics-grid">
                    <div class="metric-row"><span class="metric-label">📌 බලපෑම් ලකුණු (Impact Score) :</span> <span class="metric-val">${item.score}</span></div>
                    <div class="metric-row"><span class="metric-label">📊 වෙළඳපල දිශාව (Market Bias) :</span> <span class="metric-val">${item.bias}</span></div>
                    <div class="metric-row"><span class="metric-label">⚡ අපේක්ෂිත BTC චලනය (Expected Move) :</span> <span class="metric-val">${item.move}</span></div>
                    <div class="metric-row"><span class="metric-label">⏱️ ක්‍රියාකාරී කාලය (Time Horizon) :</span> <span class="metric-val">${item.horizon}</span></div>
                </div>
                <div class="section-title">📊 1. ගැඹුරු වෙළඳපල හා Orderbook විශ්ලේෂණය (Deep Microstructure & Macro):</div>
                <div class="analysis-text">${item.analysis}</div>
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

async def analyze_news(title, body, source):
    try:
        content = f"Source: {source}\nHeadline: {title}\nFull Text: {body}"
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this specific news:\n{content[:1200]}"}
            ],
            temperature=0.2,
            max_tokens=1500
        )
        raw = completion.choices[0].message.content
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        
        status = "PRICED_IN"
        tier = "LOW"
        score = "2 / 10"
        bias = "NEUTRAL"
        move = "±$0 - $0"
        horizon = "දැනටමත් සිදුවී ඇත"
        body_lines = []

        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("STATUS:"): status = "BREAKING" if "BREAKING" in s else "PRICED_IN"
            elif s.startswith("TIER:"): tier = "HIGH" if "HIGH" in s else ("MEDIUM" if "MEDIUM" in s else "LOW")
            elif s.startswith("SCORE:"): score = s.replace("SCORE:", "").strip()
            elif s.startswith("BIAS:"): bias = s.replace("BIAS:", "").strip()
            elif s.startswith("MOVE:"): move = s.replace("MOVE:", "").strip()
            elif s.startswith("HORIZON:"): horizon = s.replace("HORIZON:", "").strip()
            else:
                if s: body_lines.append(s)

        actual_analysis = "\n".join(body_lines).strip()
        return status, tier, score, bias, move, horizon, actual_analysis
    except Exception as e:
        logger.error(f"Error: {e}")
        return "PRICED_IN", "LOW", "1/10", "NEUTRAL", "±$0", "දැනටමත් සිදුවී ඇත", f"විශ්ලේෂණ දෝෂයකි: {e}"

async def broadcast(item):
    recent_news_cache.append(item)
    if len(recent_news_cache) > 30: recent_news_cache.pop(0)
    for ws in list(connected_websockets):
        try: await ws.send_str(json.dumps(item))
        except: connected_websockets.discard(ws)

async def news_worker():
    while True:
        raw_news = await news_queue.get()
        title = raw_news.get("title", "")
        body = raw_news.get("body", "")
        source = raw_news.get("source", "Tree News")
        
        status, tier, score, bias, move, horizon, analysis = await analyze_news(title, body, source)
        payload = {
            "title": title,
            "raw_body": body if body and body != title else "",
            "source": source,
            "status": status,
            "tier": tier,
            "score": score,
            "bias": bias,
            "move": move,
            "horizon": horizon,
            "analysis": analysis
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
                            body = (raw.get("body") or "").strip()
                            source = raw.get("source") or "Tree of Alpha"
                            
                            key = title if title else body
                            if not key or len(key) < 10 or key in seen_titles:
                                continue
                            seen_titles.add(key)
                            if len(seen_titles) > 500: seen_titles.clear()
                            
                            await news_queue.put({
                                "title": title if title else body[:100] + "...",
                                "body": body,
                                "source": source
                            })
        except Exception as e:
            logger.error(f"Stream error: {e}")
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
