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
You are a Lead Quantitative Macro Crypto Strategist at a Tier-1 Prop Trading Desk.
Analyze breaking crypto and macro news (CPI, FOMC, Fed Rates, ETF flows, Hacks, Regulatory actions, Exchange listings) specifically for Bitcoin (BTC) price action.

When analyzing Macro data (like CPI, Inflation, Jobs, Interest Rates):
- If CPI is HIGHER than expected: Explain why this is Bearish (Fed keeps rates high -> DXY up -> liquidity drains from BTC).
- If CPI is LOWER than expected: Explain why this is Bullish (Rate cut odds up -> DXY down -> liquidity rushes to BTC).
- Always explain the Fundamental "Why" (ඇයි එහෙම වුණේ කියන ආර්ථික හා මූල්‍යමය හේතුව).

You must start the analysis with EXACTLY this header line:
IMPACT_TIER: [HIGH | MEDIUM | LOW]

Then write the rest strictly in clear, natural, fluent SINHALA (සිංහල භාෂාවෙන්) using this format:

🎯 [Impact Score]: X / 10 | 📈 [දිශාව / Market Bias]: BULLISH (ඉහළට) / BEARISH (පහළට) / NEUTRAL
⚡ [අපේක්ෂිත BTC චලනය]: ±$XXX - $XXX | [ක්‍රියාකාරී කාලය]: ක්ෂණික මිනිත්තු X-XX ඇතුළත

📊 1. ගැඹුරු වෙළඳපල හා Orderbook විශ්ලේෂණය (Deep Microstructure & Macro):
• සෘජු බලපෑම (Direct Impact): (BTC මිලට ක්ෂණිකව සිදුවන දේ සහ දිශාව)
• ඇයි මෙහෙම වුණේ? (The Fundamental "Why"): (මූල්‍යමය හා ආර්ථික හේතුව - උදා: CPI, Fed, DXY, Liquidity පිටතට යාම හෝ පැමිණීම සරල සිංහලෙන්)
• Spot CVD, Liquidity Sweep & Traps: (Fake Wick, Stop Hunt උගුල්, Orderbook එකේ Buyers/Sellers හැසිරීම සහ Liquidation කලාප)

🏛️ 2. ඓතිහාසික පසුබිම හා සංසන්දනය (Historical Precedent):
• අතීත චක්‍ර හැසිරීම: (මීට පෙර මෙවැනි අවස්ථාවලදී BTC හැසිරුණු ආකාරය)
• සත්‍ය ප්‍රතිඵලය: (පළමු ප්‍රතිචාරය Fake wick එකක්ද, නැතහොත් Trend Reversal එකක්ද?)

💡 3. Institutional Trade Setup & Action Plan:
• ක්‍රියාමාර්ගය: [AGGRESSIVE BUY / SCALP SHORT / FADE THE PUMP/DUMP / WAIT & WATCH]
• Trade Execution Blueprint: (ගත යුතු ක්‍රියාමාර්ගය, Key Levels සහ Invalidation මට්ටම)
"""

async def analyze_news(full_text):
    if not client:
        return "LOW", "⚠️ GROQ_API_KEY සකසා නැත."
    try:
        completion = await client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Full Crypto/Macro Breaking Event:\n{full_text}"}
            ],
            temperature=0.15,
            max_tokens=1000
        )
        content = completion.choices[0].message.content.strip()
        
        tier = "LOW"
        analysis_body = content
        if "IMPACT_TIER:" in content:
            parts = content.split("IMPACT_TIER:", 1)[1].split("\n", 1)
            raw_tier = parts[0].strip().upper()
            if "HIGH" in raw_tier:
                tier = "HIGH"
            elif "MEDIUM" in raw_tier:
                tier = "MEDIUM"
            else:
                tier = "LOW"
            analysis_body = parts[1].strip() if len(parts) > 1 else ""
            
        return tier, analysis_body
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return "LOW", f"විශ්ලේෂණ දෝෂයකි: {str(e)}"

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

async def handle_incoming_news(full_content, source_name, link_url):
    time_display = datetime.now().strftime("%I:%M:%S %p")
    news_id = f"news_{int(asyncio.get_event_loop().time() * 1000)}"
    
    initial_item = {
        "type": "news_pending",
        "id": news_id,
        "content": full_content,
        "source": source_name,
        "link": link_url,
        "tier": "PENDING",
        "analysis": "⚡ ගැඹුරු Macro, Orderbook සහ 'ඇයි එහෙම වුණේ' හේතුව සකස් වෙමින් පවතී...",
        "time": time_display
    }
    await broadcast(initial_item)
    
    tier, analysis = await analyze_news(full_content)
    
    completed_item = {
        "type": "news_update",
        "id": news_id,
        "content": full_content,
        "source": source_name,
        "link": link_url,
        "tier": tier,
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
                                title = (data.get("title") or "").strip()
                                body = (data.get("body") or "").strip()
                                source = data.get("source") or "Tree News Wire"
                                link_url = data.get("link") or data.get("url") or ""
                                
                                # Title සහ Body දෙකම එකතු කර සම්පූර්ණ Text එක ගැනීම
                                full_text = ""
                                if title and body:
                                    full_text = f"{title}\n\n{body}"
                                elif title:
                                    full_text = title
                                elif body:
                                    full_text = body
                                    
                                if full_text:
                                    asyncio.create_task(handle_incoming_news(full_text, source, link_url))
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
    <title>ALPHA QUANT // PRO NEWS TERMINAL</title>
    <style>
        body {
            background-color: #070a0f;
            color: #d8e2ed;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans Sinhala", sans-serif;
            margin: 0;
            padding: 24px;
            display: flex;
            justify-content: center;
            -webkit-font-smoothing: antialiased;
        }
        .container { width: 100%; max-width: 1040px; }
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
            background: #0e1420;
            border: 1px solid #1e293b;
            border-radius: 14px;
            margin-bottom: 28px;
            box-shadow: 0 10px 28px rgba(0,0,0,0.6);
            overflow: hidden;
        }
        .impact-title-bar {
            padding: 14px 24px;
            font-size: 19px;
            font-weight: 900;
            letter-spacing: 1px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .tier-HIGH {
            background: linear-gradient(90deg, rgba(239, 68, 68, 0.25) 0%, rgba(185, 28, 28, 0.1) 100%);
            color: #f87171;
            border-left: 6px solid #ef4444;
            box-shadow: inset 0 0 20px rgba(239, 68, 68, 0.2);
        }
        .tier-MEDIUM {
            background: linear-gradient(90deg, rgba(245, 158, 11, 0.25) 0%, rgba(180, 83, 9, 0.1) 100%);
            color: #fbbf24;
            border-left: 6px solid #f59e0b;
        }
        .tier-LOW {
            background: linear-gradient(90deg, rgba(148, 163, 184, 0.15) 0%, rgba(71, 85, 105, 0.05) 100%);
            color: #94a3b8;
            border-left: 6px solid #64748b;
        }
        .tier-PENDING {
            background: #161f30;
            color: #38bdf8;
            border-left: 6px solid #38bdf8;
        }

        .card-body { padding: 24px; }
        .news-content {
            font-size: 20px;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.65;
            margin-bottom: 22px;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .analysis-box {
            background: #070a0f;
            border: 1px solid #1a2233;
            border-radius: 10px;
            padding: 22px;
            font-size: 18px;
            line-height: 1.95;
            color: #f1f5f9;
            white-space: pre-wrap;
            font-weight: 400;
            letter-spacing: 0.2px;
        }
        .timestamp {
            font-size: 14px;
            color: #64748b;
            margin-top: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .source-link {
            color: #38bdf8;
            text-decoration: none;
            font-weight: 600;
        }
        .source-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">⚡ ALPHA QUANT // PRO MACRO TERMINAL</div>
            <div class="live-badge" id="status">● LIVE STREAMING</div>
        </div>
        <div id="feed">
            <div id="empty-msg" style="text-align:center; padding: 60px; color:#64748b; font-size:18px;">
                සජීවී Institutional පුවත් සහ Macro දත්ත බලාපොරොත්තුවෙන් පවතී...
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

        function getHeaderHtml(tier) {
            if (tier === 'HIGH') return '<span>🔥 🔴 HIGH IMPACT EVENT</span> <span>INSTITUTIONAL ALERT</span>';
            if (tier === 'MEDIUM') return '<span>⚡ 🟡 MEDIUM IMPACT EVENT</span> <span>VOLATILITY EXPECTED</span>';
            if (tier === 'LOW') return '<span>🟢 LOW IMPACT (MARKET NOISE)</span> <span>ROUTINE FLOW</span>';
            return '<span>⏳ ANALYZING IMPACT...</span> <span>QUANT ENGINE</span>';
        }

        function renderCard(data, prepend = false) {
            let existing = document.getElementById(data.id);
            if (existing) return;

            const tier = data.tier || 'PENDING';
            const card = document.createElement('div');
            card.className = 'news-card';
            card.id = data.id || ('temp_' + Math.random());
            
            let sourceHtml = data.link ? `<a href="${data.link}" target="_blank" class="source-link">Source: ${data.source || 'Direct Wire'} ↗</a>` : `<span>Source: ${data.source || 'Direct Wire'}</span>`;

            card.innerHTML = `
                <div class="impact-title-bar tier-${tier}" id="header_${data.id}">
                    ${getHeaderHtml(tier)}
                </div>
                <div class="card-body">
                    <div class="news-content">${data.content}</div>
                    <div class="analysis-box" id="box_${data.id}">${data.analysis}</div>
                    <div class="timestamp">
                        ${sourceHtml}
                        <span>${data.time || ''}</span>
                    </div>
                </div>
            `;
            if (prepend) {
                feed.insertBefore(card, feed.firstChild);
            } else {
                feed.appendChild(card);
            }
        }

        function updateCard(data) {
            const headerBox = document.getElementById(`header_${data.id}`);
            const box = document.getElementById(`box_${data.id}`);
            const tier = data.tier || 'LOW';

            if (headerBox) {
                headerBox.className = `impact-title-bar tier-${tier}`;
                headerBox.innerHTML = getHeaderHtml(tier);
            }
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
