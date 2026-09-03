import os
import json
import asyncio
import logging
import aiohttp
from aiohttp import web
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CryptoNewsHub")

# Direct Hardcoded API Key to bypass Railway Variable whitespace bugs
API_KEY = "sk-pelmrylphluuoklrexttdcsvmnshpklddvzecrcmfzbbzthu"

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url="https://api.siliconflow.cn/v1"
)

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

connected_websockets = set()
recent_news_cache = []
seen_titles = set()

SYSTEM_PROMPT = """You are a senior institutional quantitative crypto analyst.
Analyze the given breaking crypto/financial news strictly in fluent, natural Sinhala.

Respond EXACTLY in this format:
TIMING_STATUS: [BREAKING or PRICED_IN]
IMPACT_TIER: [HIGH, MEDIUM, or LOW]

**ක්ෂණික වෙළඳපල බලපෑම:**
(පැහැදිලි සිංහලෙන් කෙටි විග්‍රහයක්)

**ප්‍රධාන ප්‍රතිලාභීන් / අලාභ ලබන්නන්:**
(බලපෑමට ලක්වන Cryptos / Tokens)

**Microstructure & Market Horizon:**
(කෙටි කාලීන සහ දිගු කාලීන බලපෑම)"""

HTML_UI = """<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <title>ALPHA QUANT // PRO MACRO TERMINAL</title>
    <style>
        body { background: #0b0e14; color: #d1d5db; font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 15px; margin-bottom: 20px; }
        .title { font-size: 20px; font-weight: bold; color: #10b981; letter-spacing: 1px; }
        .grid { display: flex; flex-direction: column; gap: 15px; max-width: 900px; margin: 0 auto; }
        .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 18px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-bottom: 8px; }
        .status-BREAKING { background: #ef4444; color: #fff; }
        .status-PRICED_IN { background: #6b7280; color: #fff; }
        .tier-HIGH { border-left: 4px solid #ef4444; }
        .tier-MEDIUM { border-left: 4px solid #f59e0b; }
        .tier-LOW { border-left: 4px solid #10b981; }
        .source { font-size: 12px; color: #9ca3af; margin-bottom: 6px; }
        .news-title { font-size: 16px; font-weight: bold; color: #f9fafb; margin-bottom: 12px; line-height: 1.4; }
        .analysis { background: #161f30; border-radius: 6px; padding: 12px; font-size: 14px; line-height: 1.6; color: #e5e7eb; white-space: pre-wrap; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">⚡ ALPHA QUANT // PRO MACRO TERMINAL</div>
        <div id="conn-status" style="color: #10b981; font-size: 13px;">● Live Streaming (SiliconFlow Qwen)</div>
    </div>
    <div class="grid" id="news-container"></div>
    <script>
        const container = document.getElementById('news-container');
        function addCard(data) {
            const card = document.createElement('div');
            card.className = 'card tier-' + (data.tier || 'LOW');
            card.innerHTML = `
                <div>
                    <span class="badge status-${data.status || 'BREAKING'}">${data.status || 'BREAKING'}</span>
                    <span class="badge" style="background:#374151;">IMPACT: ${data.tier || 'LOW'}</span>
                </div>
                <div class="source">${data.source || 'Tree of Alpha'} • ${new Date(data.time).toLocaleTimeString()}</div>
                <div class="news-title">${data.title}</div>
                <div class="analysis">${data.analysis}</div>
            `;
            container.insertBefore(card, container.firstChild);
        }
        function connect() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
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
                {"role": "user", "content": f"Crypto News:\n{full_text[:400]}"}
            ],
            temperature=0.2,
            max_tokens=450
        )
        raw = completion.choices[0].message.content
        status, tier = "BREAKING", "LOW"
        lines, remaining = raw.splitlines(), []
        for line in lines:
            if "TIMING_STATUS:" in line:
                status = "PRICED_IN" if "PRICED" in line.upper() else "BREAKING"
            elif "IMPACT_TIER:" in line:
                t = line.upper()
                tier = "HIGH" if "HIGH" in t else ("MEDIUM" if "MEDIUM" in t else "LOW")
            else:
                remaining.append(line)
        return status, tier, "\n".join(remaining).strip()
    except Exception as e:
        logger.error(f"SiliconFlow Error: {e}")
        return "BREAKING", "LOW", f"⚠️ දෝෂයකි: {e}"

async def broadcast(item):
    recent_news_cache.append(item)
    if len(recent_news_cache) > 30:
        recent_news_cache.pop(0)
    for ws in list(connected_websockets):
        try:
            await ws.send_str(json.dumps(item))
        except Exception:
            connected_websockets.discard(ws)

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
                            
                            status, tier, analysis = await analyze_news(title)
                            payload = {
                                "title": title,
                                "source": raw.get("source", "CryptoStream"),
                                "time": raw.get("time", 0),
                                "status": status,
                                "tier": tier,
                                "analysis": analysis
                            }
                            await broadcast(payload)
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
    app["task"] = asyncio.create_task(treeofalpha_stream())

async def cleanup_background(app):
    app["task"].cancel()
    await app["task"]

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
