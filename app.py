import os
import asyncio
import json
import logging
from aiohttp import web, ClientSession
from groq import AsyncGroq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CryptoNewsApp")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

connected_clients = set()

SYSTEM_PROMPT = """
You are an expert institutional crypto quantitative analyst. Analyze the breaking crypto news specifically for Bitcoin (BTC) price action impact.
Write your analysis clearly and naturally in SINHALA (සිංහල භාෂාවෙන්). Minimize technical English jargon, or explain them simply in Sinhala so any trader can understand instantly.

Structure the response exactly as follows:
🎯 බලපෑම (Impact): [1-10] / 10 - [ඉතා ඉහළ / මධ්‍යස්ථ / අඩු]
📈 වෙළඳපල දිශාව (Bias): [Bullish (ඉහළට) / Bearish (පහළට) / Neutral (වෙනසක් නැත)]
⚡ අපේක්ෂිත මිල වෙනස: [උදා: ±$100-$300] | කාලය: [උදා: මිනිත්තු 1-5 ඇතුළත]

📊 වෙළඳපල හා Orderbook විශ්ලේෂණය:
• ප්‍රධාන හේතුව: (පුවත නිසා වෙළඳපලට සිදුවන සෘජු බලපෑම සරල සිංහලෙන්)
• Buyers/Sellers හැසිරීම: (Orderbook එකට සහ Volume එකට සිදුවන දේ)
• Liquidity සහ උගුල් (Traps): (Fake pump/dump හෝ Liquidations අවදානම)

💡 Quant තීරණය (Verdict):
• නිර්දේශය: [BUY (මිලදී ගන්න) / SELL (විකුණන්න) / WAIT (ඉවසන්න)]
• කළ යුතු දේ: (වෙළෙන්දන් ගත යුතු සෘජු ක්‍රියාමාර්ගය පැහැදිලි සිංහලෙන්)
"""

async def analyze_news(text):
    if not client:
        return "⚠️ GROQ_API_KEY සකසා නැත."
    try:
        completion = await client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Breaking Crypto News:\n{text}"}
            ],
            temperature=0.2,
            max_tokens=650
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return f"විශ්ලේෂණය කිරීමේ දෝෂයක්: {str(e)}"

HTML_PAGE = """
<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA QUANT // CRYPTO TERMINAL</title>
    <style>
        body {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans Sinhala", sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 950px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #30363d;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }
        .title {
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #58a6ff;
        }
        .live-badge {
            background: rgba(46, 160, 67, 0.2);
            color: #3fb950;
            border: 1px solid #2ea043;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
        }
        .news-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 25px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.4);
            animation: fadeIn 0.4s ease-in-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .news-raw {
            font-size: 18px;
            font-weight: 600;
            color: #f0f6fc;
            line-height: 1.6;
            margin-bottom: 18px;
            border-left: 4px solid #58a6ff;
            padding-left: 14px;
        }
        .analysis-box {
            background: #0d1117;
            border: 1px solid #21262d;
            border-radius: 8px;
            padding: 18px;
            font-size: 16px;
            line-height: 1.8;
            color: #e6edf3;
            white-space: pre-wrap;
        }
        .timestamp {
            font-size: 13px;
            color: #8b949e;
            margin-top: 12px;
            text-align: right;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">⚡ ALPHA QUANT TERMINAL</div>
            <div class="live-badge">● LIVE STREAMING</div>
        </div>
        <div id="feed">
            <div style="text-align:center; padding: 40px; color:#8b949e; font-size:16px;">
                සජීවී පුවත් බලාපොරොත්තුවෙන් පවතී... (Waiting for live news)
            </div>
        </div>
    </div>
    <script>
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
        let first = true;

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const feed = document.getElementById('feed');
            if (first) { feed.innerHTML = ''; first = false; }

            const card = document.createElement('div');
            card.className = 'news-card';
            card.innerHTML = `
                <div class="news-raw">${data.title}</div>
                <div class="analysis-box">${data.analysis}</div>
                <div class="timestamp">${new Date().toLocaleTimeString()}</div>
            `;
            feed.insertBefore(card, feed.firstChild);
        };
    </script>
</body>
</html>
"""

async def index(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)
    try:
        async for msg in ws:
            pass
    finally:
        connected_clients.remove(ws)
    return ws

async def broadcast_news(title, analysis):
    if not connected_clients:
        return
    payload = json.dumps({"title": title, "analysis": analysis})
    await asyncio.gather(*[client.send_str(payload) for client in connected_clients], return_exceptions=True)

async def treeofalpha_stream():
    url = "wss://news.treeofalpha.com/ws"
    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    logger.info("Connected to Tree of Alpha WS")
                    async for msg in ws:
                        if msg.type == web.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            title = data.get("title") or data.get("body") or ""
                            if title:
                                analysis = await analyze_news(title)
                                await broadcast_news(title, analysis)
        except Exception as e:
            logger.error(f"Stream error: {e}, reconnecting in 5s...")
            await asyncio.sleep(5)

async def start_background_tasks(app):
    app['tree_task'] = asyncio.create_task(treeofalpha_stream())

async def cleanup_background_tasks(app):
    app['tree_task'].cancel()
    await app['tree_task']

def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/ws', websocket_handler)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    return app

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    web.run_app(create_app(), host='0.0.0.0', port=port)
