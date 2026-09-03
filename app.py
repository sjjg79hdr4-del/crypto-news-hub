import os
import asyncio
import json
import logging
from datetime import datetime
from aiohttp import web, ClientSession, WSMsgType
from groq import AsyncGroq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CryptoNewsApp")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

connected_clients = set()
news_history = []

SYSTEM_PROMPT = """
You are an institutional crypto quant analyst. Analyze breaking crypto news specifically for Bitcoin (BTC) impact.
Write your analysis clearly and concisely in SINHALA (සිංහල භාෂාවෙන්).

Format strictly as:
🎯 බලපෑම (Impact): [1-10]/10 - [ඉතා ඉහළ / මධ්‍යස්ථ / අඩු]
📈 දිශාව (Bias): [Bullish / Bearish / Neutral]
⚡ අපේක්ෂිත වෙනස: [උදා: ±$100-$300] | කාලය: [උදා: මිනිත්තු 1-5]

📊 වෙළඳපල හා Orderbook:
• හේතුව: (පුවතේ සෘජු බලපෑම සරල සිංහලෙන්)
• Buyers/Sellers: (Volume & Liquidity තත්ත්වය)
• උගුල් (Traps): (Fake pump/dump අවදානම)

💡 Quant තීරණය:
• නිර්දේශය: [BUY / SELL / WAIT]
• උපදෙස: (වෙළඳුන් කළ යුතු ක්‍රියාමාර්ගය)
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
            max_tokens=550
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return f"විශ්ලේෂණ දෝෂයකි: {str(e)}"

async def broadcast(data_dict):
    if not connected_clients:
        return
    msg = json.dumps(data_dict)
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send_str(msg)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)

async def handle_incoming_news(raw_title):
    time_display = datetime.now().strftime("%I:%M:%S %p")
    news_id = f"news_{int(asyncio.get_event_loop().time() * 1000)}"
    
    # 1. පුවත ආ සැනින් Browser එකට යැවීම (Instant UI update)
    initial_item = {
        "type": "news_pending",
        "id": news_id,
        "title": raw_title,
        "analysis": "⏳ AI විශ්ලේෂණය සකස් වෙමින් පවතී (Analyzing with Quant Engine)...",
        "time": time_display
    }
    await broadcast(initial_item)
    
    # 2. AI විශ්ලේෂණය ලබා ගැනීම
    analysis = await analyze_news(raw_title)
    
    # 3. Analysis එක සම්පූර්ණ වූ පසු update කිරීම
    completed_item = {
        "type": "news_update",
        "id": news_id,
        "title": raw_title,
        "analysis": analysis,
        "time": time_display
    }
    
    # History update
    news_history.insert(0, completed_item)
    if len(news_history) > 20:
        news_history.pop()
        
    await broadcast(completed_item)

async def treeofalpha_stream():
    url = "wss://news.treeofalpha.com/ws"
    while True:
        try:
            async with ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20.0) as ws:
                    logger.info("Connected to Tree of Alpha")
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                title = data.get("title") or data.get("body") or ""
                                if title:
                                    asyncio.create_task(handle_incoming_news(title))
                            except Exception as parse_err:
                                logger.error(f"JSON Parse err: {parse_err}")
                        elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            break
        except Exception as e:
            logger.error(f"Connection lost: {e}, retrying in 3s...")
            await asyncio.sleep(3)

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
        .container { width: 100%; max-width: 950px; }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #30363d;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }
        .title { font-size: 24px; font-weight: 800; color: #58a6ff; letter-spacing: 1px; }
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
        .timestamp { font-size: 13px; color: #8b949e; margin-top: 12px; text-align: right; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">⚡ ALPHA QUANT TERMINAL</div>
            <div class="live-badge" id="status">● LIVE STREAMING</div>
        </div>
        <div id="feed">
            <div id="empty-msg" style="text-align:center; padding: 40px; color:#8b949e; font-size:16px;">
                සජීවී පුවත් බලාපොරොත්තුවෙන් පවතී...
            </div>
        </div>
    </div>
    <script>
        const feed = document.getElementById('feed');
        const emptyMsg = document.getElementById('empty-msg');
        let ws;

        function connect() {
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${proto}//${window.location.host}/ws`);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (emptyMsg) emptyMsg.style.display = 'none';

                if (data.type === 'history') {
                    feed.innerHTML = '';
                    data.items.forEach(item => renderCard(item));
                } else if (data.type === 'news_pending') {
                    renderCard(data, true);
                } else if (data.type === 'news_update') {
                    updateCard(data);
                }
            };

            ws.onclose = () => {
                document.getElementById('status').innerText = '○ RECONNECTING...';
                document.getElementById('status').style.color = '#e3b341';
                setTimeout(connect, 2000);
            };

            ws.onopen = () => {
                document.getElementById('status').innerText = '● LIVE STREAMING';
                document.getElementById('status').style.color = '#3fb950';
            };
        }

        function renderCard(data, prepend = false) {
            let existing = document.getElementById(data.id);
            if (existing) return;

            const card = document.createElement('div');
            card.className = 'news-card';
            card.id = data.id || ('temp_' + Math.random());
            card.innerHTML = `
                <div class="news-raw">${data.title}</div>
                <div class="analysis-box" id="box_${data.id}">${data.analysis}</div>
                <div class="timestamp">${data.time || ''}</div>
            `;
            if (prepend) {
                feed.insertBefore(card, feed.firstChild);
            } else {
                feed.appendChild(card);
            }
        }

        function updateCard(data) {
            const box = document.getElementById(`box_${data.id}`);
            if (box) {
                box.innerText = data.analysis;
            } else {
                renderCard(data, true);
            }
        }

        connect();
    </script>
</body>
</html>
"""

async def index(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)
    connected_clients.add(ws)
    if news_history:
        await ws.send_str(json.dumps({"type": "history", "items": news_history}))
    try:
        async for msg in ws:
            pass
    finally:
        connected_clients.discard(ws)
    return ws

async def start_background_tasks(app):
    app['stream_task'] = asyncio.create_task(treeofalpha_stream())

async def cleanup_background_tasks(app):
    app['stream_task'].cancel()
    await app['stream_task']

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
