import asyncio
import json
import os
import re
import websockets
from datetime import datetime, timedelta
from aiohttp import web
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TREE_WS_URL = "wss://news.treeofalpha.com/ws"
MODEL_NAME = "qwen/qwen3.8-27b"

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"Groq Init Warning: {e}")

connected_clients = set()
recent_headlines_cache = []

news_history = [
    {
        "headline": "ALPHA QUANT ENGINE ONLINE // FEED SYNCHRONIZED",
        "analysis": "🎯 Impact Mark: [0.0 / 10] — ⚪ SYSTEM READY\n🧭 Directional Bias: 🟡 Neutral\n⚡ BTC Expected Move: ±$0\n\n🔍 BTC Orderbook & Price Action බලපෑම (සිංහලෙන්):\n• Core Catalyst: High-frequency quant pipeline එක සක්‍රීය විය. Breaking headlines ලැබෙනතුරු monitor කරමින් පවතී.\n• Orderbook & CVD Impact: Normal baseline liquidity.\n\n⚠️ BTC Quant Trade Verdict:\nVerdict: 🟢 SYSTEM ARMED\nAction Plan: Breaking macro සහ liquidations shock පුවත් නිරීක්ෂණය කරන්න.",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA TERMINAL // QUANT EXECUTION</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #06080d; color: #cbd5e1; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
        .bullish { border-left: 4px solid #10b981; background: rgba(16, 185, 129, 0.04); }
        .bearish { border-left: 4px solid #ef4444; background: rgba(239, 68, 68, 0.04); }
        .neutral { border-left: 4px solid #f59e0b; background: rgba(245, 158, 11, 0.04); }
        .recycled { border-left: 4px solid #64748b; background: rgba(100, 116, 139, 0.04); opacity: 0.75; }
    </style>
</head>
<body class="p-3 md:p-6 min-h-screen">
    <div class="max-w-4xl mx-auto">
        <header class="flex justify-between items-center pb-4 border-b border-gray-800/90 mb-4">
            <div>
                <h1 class="text-xl md:text-2xl font-black text-white tracking-wide flex items-center gap-2">
                    ⚡ ALPHA QUANT <span class="text-[10px] px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">PRO V2</span>
                </h1>
                <p class="text-xs text-gray-400 mt-0.5 tracking-wider uppercase font-mono">Institutional Liquidity Engine • Sub-Second Execution</p>
            </div>
            <div id="ws-status" class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> LIVE
            </div>
        </header>

        <div class="mb-5 p-3 bg-gradient-to-r from-gray-950 via-gray-900 to-gray-950 border border-amber-500/30 rounded-lg flex flex-col md:flex-row items-center justify-between gap-3 text-center md:text-left shadow-lg">
            <div class="flex items-center gap-2.5">
                <span class="text-[10px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded border border-amber-500/40 font-bold uppercase tracking-wider">EXCLUSIVE</span>
                <p class="text-xs md:text-sm font-semibold text-gray-200">Institutional Zero-Fee Crypto Perpetuals & Sign-up Bonus</p>
            </div>
            <a href="https://www.bybit.com" target="_blank" rel="noopener noreferrer" class="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded transition-all shadow-md shrink-0">
                Claim Perk ↗
            </a>
        </div>

        <main id="news-container" class="space-y-4"></main>

        <footer class="mt-10 pt-4 border-t border-gray-900 text-center text-[10px] text-gray-500 font-mono">
            Automated Quantitative Liquidity Feed • Strictly For Informational Purposes • Zero Financial Advice
        </footer>
    </div>

    <script>
        const container = document.getElementById('news-container');
        const statusEl = document.getElementById('ws-status');

        function renderCard(item, isNew = false) {
            let cardClass = 'neutral';
            let badgeColor = 'text-amber-400 bg-amber-950/60 border-amber-800';
            let badgeText = 'NEUTRAL';

            if (item.analysis.includes('RECYCLED') || item.analysis.includes('PRICED IN')) {
                cardClass = 'recycled';
                badgeColor = 'text-gray-400 bg-gray-900 border-gray-700';
                badgeText = '♻️ PRICED-IN';
            } else if (item.analysis.includes('Bullish') || item.analysis.includes('🟢')) {
                cardClass = 'bullish';
                badgeColor = 'text-emerald-400 bg-emerald-950/60 border-emerald-800';
                badgeText = '🟢 BULLISH';
            } else if (item.analysis.includes('Bearish') || item.analysis.includes('🔴')) {
                cardClass = 'bearish';
                badgeColor = 'text-rose-400 bg-rose-950/60 border-rose-800';
                badgeText = '🔴 BEARISH';
            }

            const card = document.createElement('div');
            card.className = `${cardClass} p-4 rounded-lg border border-gray-800/80 shadow-lg space-y-2.5 transition-all`;
            card.innerHTML = `
                <div class="flex justify-between items-start gap-4">
                    <h2 class="text-base font-bold text-gray-100 leading-snug">${item.headline}</h2>
                    <span class="text-[10px] px-2 py-0.5 rounded border font-semibold tracking-wider shrink-0 ${badgeColor}">${badgeText}</span>
                </div>
                <div class="text-xs text-gray-300 font-mono bg-black/70 p-3 rounded border border-gray-800/70 whitespace-pre-wrap leading-relaxed">${item.analysis}</div>
                <div class="text-[10px] text-gray-500 text-right font-mono">${item.timestamp}</div>
            `;
            if (isNew) {
                container.prepend(card);
            } else {
                container.appendChild(card);
            }
        }

        fetch('/api/history')
            .then(res => res.json())
            .then(data => {
                container.innerHTML = '';
                data.forEach(item => renderCard(item, false));
            });

        function connectWS() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${proto}//${location.host}/ws`);

            ws.onopen = () => {
                statusEl.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> LIVE';
                statusEl.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono';
            };

            ws.onmessage = (event) => {
                const item = JSON.parse(event.data);
                renderCard(item, true);
            };

            ws.onclose = () => {
                statusEl.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-500"></span> RECONNECTING';
                statusEl.className = 'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-800 font-mono';
                setTimeout(connectWS, 3000);
            };
        }
        connectWS();
    </script>
</body>
</html>
"""

def extract_significant_words(text):
    words = re.findall(r'\b[a-zA-Z0-9]{3,}\b', text.lower())
    ignore_words = {"the", "and", "for", "with", "this", "that", "from", "crypto", "bitcoin", "sec"}
    return set(w for w in words if w not in ignore_words)

def is_duplicate_news(headline):
    global recent_headlines_cache
    now = datetime.now()
    recent_headlines_cache = [(w, t) for w, t in recent_headlines_cache if now - t < timedelta(minutes=45)]
    
    current_words = extract_significant_words(headline)
    if len(current_words) < 3:
        return False

    for cached_words, _ in recent_headlines_cache:
        intersection = current_words.intersection(cached_words)
        similarity = len(intersection) / max(len(current_words), len(cached_words))
        if similarity >= 0.60:
            return True

    recent_headlines_cache.append((current_words, now))
    return False

def analyze_news(headline, is_recycled=False):
    global client
    if not client:
        key = os.environ.get("GROQ_API_KEY")
        if key:
            client = Groq(api_key=key)
        else:
            return "🎯 Impact Mark: [0.0 / 10]\nAPI Key not configured."

    if is_recycled:
        return (
            "🎯 Impact Mark: [0.5 / 10] — ⚪ RECYCLED / PRICED IN\n"
            "🧭 Directional Bias: 🟡 Neutral\n"
            "⚡ BTC Expected Move: ±$0 (Zero Edge)\n\n"
            "🔍 BTC Orderbook & Price Action බලපෑම (සිංහලෙන්):\n"
            "• Market Context: මෙම පුවත මීට පෙර මාධ්‍යවල පළවූවක් බැවින් වෙළඳපොළ දැනටමත් මිල adjust කර අවසන්.\n"
            "• Liquidity Reaction: Spot හෝ Derivatives orderbooks වල අලුත් buy/sell orders නොපැමිණේ. Bids/Asks සාමාන්‍ය පරිදි පවතී.\n\n"
            "⚠️ Trade Verdict:\n"
            "Verdict: 🛑 IGNORE / DO NOT CHASE\n"
            "Action Plan: කිසිදු trade එකක් නොගන්න. Fake-out wick වලට හසුවීමෙන් වළකින්න."
        )

    clean_headline = str(headline)[:400]
    
    prompt = f'''You are an elite Crypto Derivatives Quant Trader specializing in Bitcoin (BTC) orderflow and liquidity engineering.
Task: Provide a high-precision, technical breakdown of exactly how this headline impacts BITCOIN (BTC).

Strict Rules:
1. Focus strictly on Bitcoin (BTC): Spot CVD, Perp funding rates, DXY correlation, and Orderbook dynamics.
2. Macro Releases (CPI, PPI, Jobs): Higher than expected -> DXY pumps -> BTC sell pressure. Lower -> DXY drops -> BTC liquidity expansion pump.
3. Speculation/Blogs = <= 2.0. True systemic news/Macro = >= 7.5.
4. Sinhala explanation must be deeply technical yet clear about BTC orderbook reaction.

Strict Output Format:
🎯 Impact Mark: [X.X / 10] — [⚪ NOISE / 🟡 MINOR / 🔴 HIGH VOL / 🚨 MACRO SHOCK]
🧭 Directional Bias: [🟢 Bullish / 🔴 Bearish / 🟡 Neutral / 🪤 Fake-out Trap Risk]
⚡ BTC Expected Move: [±$0-$50 / ±$200-$500 / ±$1,000-$2,500+] | Window: [Immediate 60s / 5m-15m / Macro]

🔍 BTC Orderbook & Price Action බලපෑම (සිංහලෙන්):
• Core Catalyst: [පුවතේ සාරාංශය සහ Bitcoin වලට සෘජුව බලපාන හේතුව]
• Orderbook & CVD Impact: [Bids pull වෙයිද? Aggressive Market Sells/Buys එයිද? Spot buyer support තියෙයිද?]
• Liquidity Sweep & Traps: [Short Squeeze එකක්ද, Long Liquidation Cascade එකක්ද, නැතහොත් Fake Wick එකක්ද?]

⚠️ BTC Quant Trade Verdict:
Verdict: [IGNORE / SCALP LONG / SCALP SHORT / WAIT FOR SWEEP]
Action Plan: [Bitcoin traders ලා 1m/5m timeframe එකේ ක්ෂණිකව කළ යුතු දේ සහ invalidation මට්ටම]

Headline: "{clean_headline}"'''

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_NAME,
            max_tokens=480,
            temperature=0.05,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Quant Engine Latency/Error: {e}"

def extract_headline(data):
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        title = data.get("title") or ""
        body = data.get("body") or data.get("text") or data.get("en") or ""
        if title and body and title != body:
            return f"{title}: {body}".strip()
        elif body:
            return str(body).strip()
        elif title:
            return str(title).strip()
    return ""

async def handle_index(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def handle_history(request):
    return web.json_response(news_history)

async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)
    try:
        async for msg in ws:
            pass
    finally:
        connected_clients.discard(ws)
    return ws

async def broadcast_news(payload):
    news_history.insert(0, payload)
    if len(news_history) > 40:
        news_history.pop()
    for ws in list(connected_clients):
        try:
            await ws.send_str(json.dumps(payload))
        except Exception:
            pass

async def tree_listener():
    while True:
        try:
            async with websockets.connect(TREE_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                while True:
                    raw = await ws.recv()
                    if raw in ["ping", "pong"]:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = raw
                    headline = extract_headline(data)
                    if not headline or len(headline) < 4:
                        continue
                    
                    recycled = is_duplicate_news(headline)
                    analysis = analyze_news(headline, is_recycled=recycled)
                    
                    payload = {
                        "headline": headline,
                        "analysis": analysis,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                    await broadcast_news(payload)
        except Exception:
            await asyncio.sleep(3)

def main():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/ws', handle_ws)
    app.router.add_get('/api/history', handle_history)

    async def start_bg(app):
        app['tree_task'] = asyncio.create_task(tree_listener())

    async def stop_bg(app):
        app['tree_task'].cancel()
        await app['tree_task']

    app.on_startup.append(start_bg)
    app.on_cleanup.append(stop_bg)
    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()
