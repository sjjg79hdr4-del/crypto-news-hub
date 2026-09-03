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
You are a Senior Quantitative Crypto Analyst & Market Microstructure Specialist at an institutional prop desk.
Your objective is to provide a deep, high-conviction, professional analysis of breaking crypto news for Bitcoin (BTC) traders.
You must output STRICTLY in clear, fluent, natural SINHALA (සිංහල). 

Break down the analysis systematically into this exact format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 [බලපෑමේ මට්ටම]: 🔴 HIGH IMPACT / 🟡 MEDIUM IMPACT / 🟢 LOW IMPACT (NOISE)
🎯 [Impact Score]: X / 10 | 📈 [දිශාව / Market Bias]: BULLISH / BEARISH / NEUTRAL
⚡ [අපේක්ෂිත BTC චලනය]: ±$XXX - $XXX | [ක්‍රියාකාරී කාලය]: ක්ෂණික මිනිත්තු X-XX ඇතුළත

🏛️ 1. ඓතිහාසික පසුබිම හා සංසන්දනය (Historical Precedent):
• අතීත චක්‍ර හැසිරීම: (මීට පෙර මෙවැනි සිදුවීම් - Regulatory, Exploit, ETF/Macro, Exchange listings - ආ විට BTC ප්‍රතිචාර දැක්වූයේ කෙසේද? උදා: Initial fake pump පසුව dump වීමක්ද, නැතහොත් trend එකක් හැදීමක්ද?)
• උත්ප්‍රේරකයේ ප්‍රබලතාව: (මෙය සැබෑ Structural Change එකක්ද නැතහොත් කෙටි කාලීන Market Noise පමණක්ද?)

📊 2. Orderbook & Microstructure විශ්ලේෂණය:
• Spot CVD & Volume Flow: (Aggressive Market Buyers ද Sellers ද dominate කරන්නේ? Spot සහ Futures divergence එකක් ඇත්ද?)
• Liquidity Traps & Hunt මට්ටම්: (Market Makers ලා විසින් Stop-hunt කිරීමට හෝ Long/Short liquidations cascade එකක් කිරීමට ඉඩ ඇති ප්‍රධාන කලාප)

🎯 3. Institutional Trade Setup & Action Plan:
• ක්‍රියාමාර්ගය: [AGGRESSIVE BUY / SCALP LONG / SHORT FADE / WAIT & WATCH]
• Trade Execution Blueprint: (වෙළඳුන් ගත යුතු තීරණය, Key Levels, සහ Trade Setup එක අවලංගු වන Invalidation / Stop-Loss මට්ටම සරල පැහැදිලි සිංහලෙන්)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

async def analyze_news(text):
    if not client:
        return "⚠️ GROQ_API_KEY සකසා නැත."
    try:
        completion = await client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Breaking Crypto News:\n{text}"}
            ],
            temperature=0.15,
            max_tokens=900
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
    
    initial_item = {
        "type": "news_pending",
        "id": news_id,
        "title": raw_title,
        "analysis": "⚡ ගැඹුරු Quant සහ Historical විශ්ලේෂණය සකස් වෙමින් පවතී (Processing Orderbook & Precedents)...",
        "time": time_display
    }
    await broadcast(initial_item)
    
    analysis = await analyze_news(raw_title)
    
    completed_item = {
        "type": "news_update",
        "id": news_id,
        "title": raw_title,
        "analysis": analysis,
        "time": time_display
    }
    
    news_history.insert(0, completed_item)
    if len(news_history) > 30:
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
    <title>ALPHA QUANT // ADVANCED CRYPTO TERMINAL</title>
    <style>
        body {
            background-color: #080b11;
            color: #d8e2ed;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans Sinhala", sans-serif;
            margin: 0;
            padding: 24px;
            display: flex;
            justify-content: center;
            -webkit-font-smoothing: antialiased;
        }
        .container { width: 100%; max-width: 1020px; }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #1c2436;
            padding-bottom: 18px;
            margin-bottom: 26px;
        }
        .title { font-size: 26px; font-weight: 800; color: #38bdf8; letter-spacing: 0.8px; }
        .live-badge {
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            border: 1px solid #22c55e;
            padding: 7px 18px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 700;
        }
        .news-card {
            background: #0f1523;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 26px;
            margin-bottom: 26px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.55);
            transition: border-color 0.25s ease;
        }
        .news-card:hover { border-color: #38bdf8; }
        .news-raw {
            font-size: 20px;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.55;
            margin-bottom: 20px;
            border-left: 5px solid #38bdf8;
            padding-left: 16px;
        }
        .analysis-box {
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 22px;
            font-size: 18px;
            line-height: 1.95;
            color: #f1f5f9;
            white-space: pre-wrap;
            font-weight: 400;
            letter-spacing: 0.2px;
        }
        .timestamp { font-size: 14px; color: #64748b; margin-top: 16px; text-align: right; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">⚡ ALPHA QUANT // PRO NEWS TERMINAL</div>
            <div class="live-badge" id="status">● LIVE STREAMING</div>
        </div>
        <div id="feed">
            <div id="empty-msg" style="text-align:center; padding: 60px; color:#64748b; font-size:18px;">
                සජීවී Institutional පුවත් සහ Quant දත්ත බලාපොරොත්තුවෙන් පවතී...
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
                document.getElementById('status').style.color = '#f59e0b';
                setTimeout(connect, 2000);
            };

            ws.onopen = () => {
                document.getElementById('status').innerText = '● LIVE STREAMING';
                document.getElementById('status').style.color = '#4ade80';
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
