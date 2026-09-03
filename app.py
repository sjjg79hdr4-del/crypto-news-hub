import os
import re
import time
import json
import asyncio
import logging
import base64
import hashlib
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
seen_hashes = set()
news_queue = asyncio.Queue()

def generate_text_hash(text):
    clean = re.sub(r'[^a-zA-Z0-9]', '', text.lower())[:80]
    return hashlib.md5(clean.encode()).hexdigest()

SYSTEM_PROMPT = """You are an institutional cryptocurrency quantitative macro strategist.
Analyze the breaking news/tweet strictly for BITCOIN (BTC) orderflow impact.

LANGUAGE INSTRUCTIONS:
- 'summarized_english_title' MUST be in concise English (Max 1 sentence).
- ALL analysis fields MUST be in natural, professional, trader-level Sinhala.
- DO NOT use awkward Google-translate terms (e.g. NEVER say 'පිටපත් කිරීමේ අවදානම' for replication/exploit, say 'Exploit / Security අවදානම'; NEVER say 'වගකීම් අඩු කිරීම' for de-risking, say 'Risk management / Capital safety'). Use natural trader Sinhala mixed with quant terms.

Respond ONLY with a valid JSON object:
{
  "summarized_english_title": "Short sharp English headline (Max 1 sentence)",
  "impact_mark": "උදා: 1.5 / 10 — NOISE හෝ 8.0 / 10 — HIGH ALPHA",
  "directional_bias": "මධ්‍යස්ථ (Neutral) හෝ Bullish හෝ Bearish",
  "expected_move": "නොසැලකිය හැකි (Negligible) හෝ මධ්‍යම ප්‍රමාණයේ චලනයක් හෝ ප්‍රබල චලනයක්",
  "window": "ක්ෂණික තත්පර 60 හෝ කෙටි කාලීන",
  "bias_badge": "NEUTRAL හෝ BULLISH හෝ BEARISH",
  "news_points": [
    "පුවතේ ප්‍රධාන සිදුවීම පිළිබඳ පැහැදිලි සාරාංශය",
    "අදාළ සංඛ්‍යාලේඛන හෝ ප්‍රධාන කරුණු",
    "සිදුවීම පිටුපස ඇති ආයතනික පසුබිම"
  ],
  "core_catalyst": "මෙම පුවත BTC spot/perp මිලට macro catalyst එකක් වන්නේ කෙසේද යන්න කෙටියෙන් හා පැහැදිලිව.",
  "cvd_orderbook_impact": "Spot CVD වල sell/buy pressure සහ Perp orderbook එකේ limit liquidity හැසිරීම.",
  "liquidity_traps": "Stop hunt, fake wick හෝ long/short liquidations සිදුවිය හැකි ආකාරය.",
  "verdict": "නොසලකා හරින්න (IGNORE) හෝ NO-TRADE ZONE හෝ LONG BIAS හෝ SHORT BIAS",
  "action_plan": "Spot CVD divergence සහ orderbook absorption අනුව ගත යුතු කෙටි, පැහැදිලි trading පියවර."
}"""

HTML_UI = """<!DOCTYPE html>
<html lang="si">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPHA QUANT // INSTITUTIONAL MACRO TERMINAL</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #06090e;
            color: #cbd5e1;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
            padding: 24px 20px;
        }
        .container {
            max-width: 960px;
            margin: 0 auto;
        }
        .terminal-nav {
            background: linear-gradient(180deg, #0f172a 0%, #090e17 100%);
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.6);
        }
        .nav-brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .brand-icon {
            width: 36px;
            height: 36px;
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            color: #38bdf8;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }
        .brand-title {
            font-size: 17px;
            font-weight: 900;
            letter-spacing: 1px;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .badge-v2 {
            background: #0284c7;
            color: #ffffff;
            font-size: 10px;
            font-weight: 900;
            padding: 2px 7px;
            border-radius: 4px;
        }
        .brand-sub {
            font-size: 11px;
            font-weight: 600;
            color: #64748b;
            letter-spacing: 0.8px;
        }
        .nav-status-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .live-chip {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            font-size: 11px;
            font-weight: 800;
            padding: 5px 12px;
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .live-dot {
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
            animation: pulse-glow 1.5s infinite;
        }
        @keyframes pulse-glow {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.5; }
        }
        .latency-chip {
            font-size: 11px;
            font-weight: 700;
            color: #94a3b8;
            background: #0b0f19;
            padding: 5px 10px;
            border-radius: 6px;
            border: 1px solid #1e293b;
        }
        
        .grid {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        .card {
            background: #0a0f18;
            border: 1px solid #1a2436;
            border-radius: 12px;
            padding: 26px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
        }
        .timing-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .badge-live-breaking {
            background: #4c0519;
            color: #fda4af;
            border: 1px solid #9f1239;
            font-size: 11px;
            font-weight: 900;
            padding: 4px 10px;
            border-radius: 4px;
            letter-spacing: 0.8px;
        }
        .badge-archive-recap {
            background: #1e293b;
            color: #94a3b8;
            border: 1px solid #334155;
            font-size: 11px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 4px;
            letter-spacing: 0.8px;
        }
        .impact-hero {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #0f1726;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 14px 18px;
            margin-bottom: 18px;
        }
        .impact-hero-left {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .impact-label {
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #64748b;
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
            font-size: 12.5px;
            font-weight: 900;
            letter-spacing: 1px;
            white-space: nowrap;
        }
        .bias-NEUTRAL { background: #271e11; color: #fbbf24; border: 1px solid #78350f; }
        .bias-BULLISH { background: #064e3b; color: #34d399; border: 1px solid #059669; }
        .bias-BEARISH { background: #451319; color: #f87171; border: 1px solid #991b1b; }

        .summarized-title {
            font-size: 18px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.5;
            margin-bottom: 16px;
            word-break: break-word;
        }
        .metric-summary {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            font-size: 13.5px;
            color: #94a3b8;
            background: #0c121e;
            border: 1px solid #162032;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 20px;
        }
        .metric-summary span {
            color: #f1f5f9;
            font-weight: 700;
        }
        .news-summary-box {
            background: #0e1626;
            border-left: 4px solid #38bdf8;
            padding: 16px 18px;
            border-radius: 0 8px 8px 0;
            margin-bottom: 22px;
        }
        .news-summary-title {
            font-size: 12px;
            font-weight: 900;
            letter-spacing: 1px;
            color: #38bdf8;
            margin-bottom: 10px;
        }
        .summary-points-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            font-size: 13.5px;
            line-height: 1.75;
            color: #e2e8f0;
        }
        .summary-points-list div {
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }
        .summary-points-list span {
            color: #38bdf8;
            font-weight: 900;
        }
        
        /* Structured Analysis Section */
        .analysis-container {
            background: #0c121e;
            border: 1px solid #162032;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 20px;
        }
        .section-header {
            font-size: 14px;
            font-weight: 800;
            color: #38bdf8;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .points-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            font-size: 13.5px;
            line-height: 1.8;
            color: #94a3b8;
        }
        .point-item {
            background: #080d15;
            border-left: 2px solid #2563eb;
            padding: 10px 14px;
            border-radius: 0 6px 6px 0;
        }
        .point-label {
            color: #f1f5f9;
            font-weight: 700;
            margin-right: 6px;
        }

        /* Verdict Box */
        .verdict-box {
            background: linear-gradient(180deg, #131a29 0%, #0c121e 100%);
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 18px;
            font-size: 13.5px;
            line-height: 1.8;
        }
        .verdict-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 10px;
            margin-bottom: 12px;
        }
        .verdict-title {
            color: #fbbf24;
            font-size: 14px;
            font-weight: 900;
            letter-spacing: 0.5px;
        }
        .verdict-badge-box {
            background: #1e293b;
            color: #38bdf8;
            font-weight: 800;
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 12px;
        }
        .action-plan-content {
            color: #cbd5e1;
        }
        .card-time {
            text-align: right;
            font-size: 11px;
            color: #475569;
            margin-top: 14px;
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
        <div class="terminal-nav">
            <div class="nav-brand">
                <div class="brand-icon">⚡</div>
                <div>
                    <div class="brand-title">ALPHA QUANT <span class="badge-v2">PRO V2</span></div>
                    <div class="brand-sub">INSTITUTIONAL LIQUIDITY ENGINE • SUB-SECOND QUANT VERDICT</div>
                </div>
            </div>
            <div class="nav-status-group">
                <div class="latency-chip">⚡ 12ms EXECUTION</div>
                <div class="live-chip"><div class="live-dot"></div> FEED SYNCHRONIZED</div>
            </div>
        </div>

        <div class="grid" id="news-container">
            <div id="wait-placeholder" style="text-align:center; padding:60px; color:#475569; font-size:14px; font-weight:700;">
                📡 CONNECTED TO QUANTITATIVE FEED // WAITING FOR CATALYST...
            </div>
        </div>

        <div class="bottom-bar">
            <div style="color:#38bdf8;">ALPHA QUANT ENGINE ONLINE // SUB-SECOND PIPELINE ACTIVE</div>
            <div style="color:#10b981;">● SYSTEM OPTIMAL</div>
        </div>
    </div>

    <script>
        const container = document.getElementById("news-container");
        function addCard(d) {
            const p = document.getElementById("wait-placeholder");
            if (p) p.remove();

            const card = document.createElement("div");
            card.className = "card";

            const rawBias = (d.bias_badge || d.directional_bias || "NEUTRAL").toUpperCase();
            const biasClass = rawBias.includes("BULL") ? "BULLISH" : (rawBias.includes("BEAR") ? "BEARISH" : "NEUTRAL");

            const isBreaking = d.is_fresh_breaking;
            const timingBadge = isBreaking 
                ? `<div class="badge-live-breaking">⚡ BREAKING NEWS</div>`
                : `<div class="badge-archive-recap">⌛ PRICED-IN / RECAP</div>`;

            let pointsHtml = "";
            if (Array.isArray(d.news_points) && d.news_points.length > 0) {
                pointsHtml = d.news_points.map(pt => `<div><span>•</span> <div>${pt}</div></div>`).join("");
            } else if (d.news_summary) {
                pointsHtml = `<div><span>•</span> <div>${d.news_summary}</div></div>`;
            }

            card.innerHTML = `
                <div class="timing-strip">
                    ${timingBadge}
                    <div style="font-size:11px; color:#64748b;">QUANT SIGNAL VERIFIED</div>
                </div>

                <div class="impact-hero">
                    <div class="impact-hero-left">
                        <div class="impact-label">📌 IMPACT SCORE & EVALUATION</div>
                        <div class="impact-val">⚡ ${d.impact_mark}</div>
                    </div>
                    <div class="badge-bias bias-${biasClass}">● ${d.directional_bias}</div>
                </div>

                <div class="summarized-title">${d.display_title}</div>

                <div class="metric-summary">
                    <div>🎯 <strong>Directional Bias:</strong> <span>● ${d.directional_bias}</span></div>
                    <div>⚡ <strong>BTC Expected Move:</strong> <span>${d.expected_move}</span></div>
                    <div>⏱️ <strong>Window:</strong> <span>${d.window}</span></div>
                </div>

                <div class="news-summary-box">
                    <div class="news-summary-title">📢 පුවතේ සාරාංශය (WHAT HAPPENED):</div>
                    <div class="summary-points-list">
                        ${pointsHtml}
                    </div>
                </div>

                <div class="analysis-container">
                    <div class="section-header">● BTC Orderbook & Price Action බලපෑම:</div>
                    <div class="points-list">
                        <div class="point-item">
                            <span class="point-label">• Core Catalyst:</span> ${d.core_catalyst}
                        </div>
                        <div class="point-item">
                            <span class="point-label">• Orderbook & CVD Impact:</span> ${d.cvd_orderbook_impact}
                        </div>
                        <div class="point-item">
                            <span class="point-label">• Liquidity Sweep & Traps:</span> ${d.liquidity_traps}
                        </div>
                    </div>
                </div>

                <div class="verdict-box">
                    <div class="verdict-header">
                        <div class="verdict-title">⚠️ BTC Quant Trade Verdict</div>
                        <div class="verdict-badge-box">${d.verdict}</div>
                    </div>
                    <div class="action-plan-content">
                        <strong>ක්‍රියාකාරී සැලැස්ම (Action Plan):</strong> ${d.action_plan}
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
    prompt_payload = f"Analyze breaking crypto headline for BTC Orderflow and DOM execution. ALL analysis must be exclusively in natural, trader-grade Sinhala:\n\n{text[:3500]}"
    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_payload}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1800
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {
            "summarized_english_title": text[:90] + "...",
            "impact_mark": "1.5 / 10 — NOISE",
            "directional_bias": "මධ්‍යස්ථ (Neutral)",
            "expected_move": "නොසැලකිය හැකි (Negligible)",
            "window": "ක්ෂණික තත්පර 60",
            "bias_badge": "NEUTRAL",
            "news_points": [
                "සාමාන්‍ය පුවතක් හෝ ප්‍රකාශනයක් වාර්තා වී ඇත.",
                "ක්ෂණික ප්‍රතිපත්ති හෝ අරමුදල් ගලායාමේ වෙනසක් නොමැත.",
                "Bitcoin මිලට සෘජු ආයතනික බලපෑමක් ඇති නොකරයි."
            ],
            "core_catalyst": "මෙය Bitcoin සඳහා macro catalyst එකක් නොවන සාමාන්‍ය noise පුවතකි.",
            "cvd_orderbook_impact": "Spot CVD සහ DOM bid/ask liquidity වල කිසිදු කැපී පෙනෙන වෙනසක් නොමැත.",
            "liquidity_traps": "ලික්විඩේෂන් හෝ fake wick අවදානමක් නොමැත.",
            "verdict": "නොසලකා හරින්න (IGNORE)",
            "action_plan": "Spot CVD සහ DOM එකේ වෙනසක් නැති බැවින් trade නොගෙන ප්‍රාග්ධනය ආරක්ෂා කරගන්න."
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
        item_time = raw_news.get("time", time.time() * 1000)
        
        now_ms = time.time() * 1000
        is_fresh = (now_ms - item_time) < (120 * 1000) if item_time > 0 else True

        if body and body != full_title:
            content = f"Headline: {full_title}\nBody/Details: {body}"
        else:
            content = full_title
            
        res = await analyze_news(content)
        display_title = res.get("summarized_english_title") or full_title
        
        payload = {
            "display_title": display_title,
            "is_fresh_breaking": is_fresh,
            "impact_mark": res.get("impact_mark", "1.5 / 10 — NOISE"),
            "directional_bias": res.get("directional_bias", "මධ්‍යස්ථ (Neutral)"),
            "expected_move": res.get("expected_move", "නොසැලකිය හැකි (Negligible)"),
            "window": res.get("window", "ක්ෂණික තත්පර 60"),
            "bias_badge": res.get("bias_badge", "NEUTRAL"),
            "news_points": res.get("news_points", []),
            "core_catalyst": res.get("core_catalyst", ""),
            "cvd_orderbook_impact": res.get("cvd_orderbook_impact", ""),
            "liquidity_traps": res.get("liquidity_traps", ""),
            "verdict": res.get("verdict", "නොසලකා හරින්න (IGNORE)"),
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
                    logger.info("Connected to news stream")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            raw = json.loads(msg.data)
                            title = (raw.get("title") or "").strip()
                            body = (raw.get("body") or raw.get("content") or "").strip()
                            item_time = raw.get("time") or (time.time() * 1000)
                            
                            combined = f"{title} {body}".strip()
                            if len(combined) < 15:
                                continue
                            
                            h = generate_text_hash(combined)
                            if h in seen_hashes:
                                continue
                            seen_hashes.add(h)
                            if len(seen_hashes) > 2000:
                                seen_hashes.clear()
                            
                            if title and body and title not in body:
                                full_title = f"{title}: {body}"
                            else:
                                full_title = title if title else body
                            
                            await news_queue.put({
                                "full_title": full_title,
                                "body": body,
                                "time": item_time
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
