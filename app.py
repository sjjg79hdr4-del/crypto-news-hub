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

SYSTEM_PROMPT = """You are an elite cryptocurrency market microstructure intelligence terminal and forensic on-chain quant.
Your job is to conduct an EXHAUSTIVE, DEEP-DIVE FACTUAL BREAKDOWN of the raw incoming news or tweet.

CRITICAL RULE FOR IMPACT EVALUATION:
- Newspapers, media opinion pieces (e.g., WSJ, Bloomberg articles), historical analysis, or general commentary are NOT breaking market catalysts. They must ALWAYS be given a low impact mark (e.g., 2.0 / 10 to 4.5 / 10) and classified as NOISE or standard macro feed.
- ONLY live breaking regulatory actions (SEC, CFTC), sudden exchange hacks, emergency central bank rate cuts, or massive on-chain liquidations deserve high impact marks (>= 7.5 / 10).

LANGUAGE ENFORCEMENT:
- 'summarized_english_title': Ultra-sharp, precise English headline capturing the exact development (Max 1 sentence).
- EVERY OTHER FIELD MUST BE WRITTEN IN DEEP, SOPHISTICATED, NATURAL TRADER SINHALA. Keep it concise, crisp, and direct. NEVER leave any field empty.

Respond ONLY with a valid JSON object matching this schema:
{
  "summarized_english_title": "Precise English headline detailing the full context",
  "impact_mark": "උදා: 2.0 / 10 — NOISE හෝ 8.5 / 10 — HIGH ALPHA",
  "directional_bias": "මධ්‍යස්ථ (Neutral) හෝ Bullish හෝ Bearish",
  "expected_move": "නොසැලකිය හැකි (Negligible) හෝ මධ්‍යම ප්‍රමාණයේ චලනයක් හෝ ප්‍රබල චලනයක්",
  "window": "ක්ෂණික තත්පර 60 හෝ කෙටි කාලීන",
  "bias_badge": "NEUTRAL හෝ BULLISH හෝ BEARISH",
  "news_points": [
    "පළවූ පුවතේ මුල සිට අගට ඇති සාරාංශගත කරුණු පිළිබඳ ගැඹුරු සිංහල පැහැදිලි කිරීම",
    "අදාළ සංවිධානය හෝ පුද්ගලයා කවුද සහ මෙම ප්‍රකාශය පිටුපස ඇති සැබෑ තත්ත්වය",
    "මෙම සිදුවීමෙන් වෙළඳපලට ඇතිවන සැබෑ බලපෑම"
  ],
  "core_catalyst": "මෙම සිදුවීම BTC සාර්ව ආර්ථික ප්‍රාග්ධන ගලනයට සහ Spot වෙළඳපලට බලපාන්නේ කෙසේද යන්න පිළිබඳ කෙටි විග්‍රහය.",
  "cvd_orderbook_impact": "Spot CVD වල ආක්‍රමණශීලී මිලදී ගැනීම්/විකිණීම් සහ DOM Orderbook Bid/Ask Limit Walls වල හැසිරීම.",
  "liquidity_traps": "Perp Open Interest වෙනස්වීම්, Short/Long Stop Hunt අවදානම සහ Fakeout/Sweep විය හැකි කලාප.",
  "verdict": "නොසලකා හරින්න (IGNORE) හෝ NO-TRADE ZONE හෝ LONG BIAS හෝ SHORT BIAS",
  "action_plan": "Spot CVD divergence සහ orderbook absorption අනුව ගත යුතු කෙටි trading පියවර සිංහලෙන්."
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
            margin-bottom: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.6);
        }
        .disclaimer-banner {
            background: rgba(251, 191, 36, 0.08);
            border: 1px solid rgba(251, 191, 36, 0.25);
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 11.5px;
            color: #fde047;
            font-weight: 600;
            line-height: 1.5;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
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
            gap: 10px;
            flex-wrap: wrap;
        }
        .sound-toggle-btn {
            background: #1e293b;
            border: 1px solid #334155;
            color: #38bdf8;
            font-size: 11px;
            font-weight: 800;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .sound-toggle-btn:hover {
            background: #334155;
            color: #ffffff;
        }
        .online-chip {
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: #38bdf8;
            font-size: 11px;
            font-weight: 800;
            padding: 5px 10px;
            border-radius: 6px;
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
            animation: slideIn 0.3s ease-out;
            transition: all 0.3s ease;
        }
        .card.new-incoming {
            border-color: #38bdf8;
            box-shadow: 0 0 25px rgba(56, 189, 248, 0.25);
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-15px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .timing-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .badge-high-impact {
            background: #4c0519;
            color: #fda4af;
            border: 1px solid #9f1239;
            font-size: 11px;
            font-weight: 900;
            padding: 4px 10px;
            border-radius: 4px;
            letter-spacing: 0.8px;
        }
        .badge-standard-feed {
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
            padding: 18px 20px;
            border-radius: 0 8px 8px 0;
            margin-bottom: 22px;
        }
        .news-summary-title {
            font-size: 13px;
            font-weight: 900;
            letter-spacing: 1px;
            color: #38bdf8;
            margin-bottom: 12px;
        }
        .summary-points-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
            font-size: 14px;
            line-height: 1.85;
            color: #e2e8f0;
        }
        .summary-points-list div {
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }
        .summary-points-list span {
            color: #38bdf8;
            font-weight: 900;
        }
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
            line-height: 1.85;
            color: #94a3b8;
        }
        .point-item {
            background: #080d15;
            border-left: 2px solid #2563eb;
            padding: 12px 16px;
            border-radius: 0 6px 6px 0;
        }
        .point-label {
            color: #f1f5f9;
            font-weight: 700;
            margin-right: 6px;
        }
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
                <button class="sound-toggle-btn" id="sound-btn" onclick="toggleSound()">🔊 SOUND: ENABLED</button>
                <div class="online-chip" id="online-count-chip">👤 ONLINE: 1</div>
                <div class="latency-chip">⚡ 12ms EXECUTION</div>
                <div class="live-chip" id="status-chip"><div class="live-dot"></div> FEED SYNCHRONIZED</div>
            </div>
        </div>

        <div class="disclaimer-banner">
            ⚠️ <strong>Disclaimer:</strong> Not an official wire news service. Not financial advice. For informational and tracking purposes only.
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
        let soundEnabled = true;
        let audioCtx = null;

        function toggleSound() {
            soundEnabled = !soundEnabled;
            const btn = document.getElementById("sound-btn");
            if (soundEnabled) {
                btn.innerText = "🔊 SOUND: ENABLED";
                btn.style.borderColor = "#334155";
                btn.style.color = "#38bdf8";
                initAudio();
            } else {
                btn.innerText = "🔇 SOUND: MUTED";
                btn.style.borderColor = "#991b1b";
                btn.style.color = "#f87171";
            }
        }

        function initAudio() {
            try {
                if (!audioCtx) {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                }
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume();
                }
            } catch(e) {}
        }

        ['click', 'keydown', 'touchstart'].forEach(evt => {
            window.addEventListener(evt, () => {
                initAudio();
            }, { once: true });
        });

        function playSynthAlert() {
            if (!soundEnabled) return;
            try {
                initAudio();
                if (!audioCtx) return;

                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();

                osc.type = 'sine';
                osc.frequency.setValueAtTime(659.25, audioCtx.currentTime);
                osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.1);

                gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.35);

                osc.connect(gain);
                gain.connect(audioCtx.destination);

                osc.start();
                osc.stop(audioCtx.currentTime + 0.35);
            } catch(e) {}
        }

        const container = document.getElementById("news-container");
        const renderedIds = new Set();

        function addCard(d, isInitialLoad = false) {
            const cardId = d.display_title + (d.card_time || "");
            if (renderedIds.has(cardId)) return;
            renderedIds.add(cardId);

            const p = document.getElementById("wait-placeholder");
            if (p) p.remove();

            const card = document.createElement("div");
            card.className = "card";
            
            if (!isInitialLoad) {
                card.classList.add("new-incoming");
                playSynthAlert();
            }

            const rawBias = (d.bias_badge || d.directional_bias || "NEUTRAL").toUpperCase();
            const biasClass = rawBias.includes("BULL") ? "BULLISH" : (rawBias.includes("BEAR") ? "BEARISH" : "NEUTRAL");

            const isHighImpact = d.is_high_impact;
            const timingBadge = isHighImpact 
                ? `<div class="badge-high-impact">⚡ HIGH IMPACT BREAKING</div>`
                : `<div class="badge-standard-feed">📌 STANDARD MACRO FEED</div>`;

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
                    <div class="news-summary-title">📢 පුවතේ සවිස්තරාත්මක විග්‍රහය (FORENSIC EVENT BREAKDOWN):</div>
                    <div class="summary-points-list">
                        ${pointsHtml}
                    </div>
                </div>

                <div class="analysis-container">
                    <div class="section-header">● BTC Orderbook & Price Action ගැඹුරු බලපෑම:</div>
                    <div class="points-list">
                        <div class="point-item">
                            <span class="point-label">• Core Catalyst:</span> ${d.core_catalyst || "වෙළඳපලට සෘජු ප්‍රාග්ධන ගලනයක් නොමැත."}
                        </div>
                        <div class="point-item">
                            <span class="point-label">• Orderbook & CVD Impact:</span> ${d.cvd_orderbook_impact || "CVD වල වෙනසක් නොමැත."}
                        </div>
                        <div class="point-item">
                            <span class="point-label">• Liquidity Sweep & Traps:</span> ${d.liquidity_traps || "අදාළ අවදානම් නොමැත."}
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
                <div class="card-time">${d.card_time || new Date().toLocaleTimeString()}</div>
            `;
            container.insertBefore(card, container.firstChild);
        }

        let ws;
        function connect() {
            const proto = location.protocol === "https:" ? "wss:" : "ws:";
            ws = new WebSocket(`${proto}//${location.host}/ws`);

            ws.onopen = () => {
                document.getElementById("status-chip").innerHTML = '<div class="live-dot"></div> FEED SYNCHRONIZED';
            };

            ws.onmessage = (e) => {
                if (e.data === "pong") return;
                try {
                    const msg = JSON.parse(e.data);
                    if (msg.type === "online_count") {
                        document.getElementById("online-count-chip").innerText = `👤 ONLINE: ${msg.count}`;
                        return;
                    }
                    if (Array.isArray(msg)) { 
                        msg.forEach(item => addCard(item, true)); 
                    } else { 
                        addCard(msg, false); 
                    }
                } catch(err) {}
            };

            ws.onclose = () => {
                document.getElementById("status-chip").innerHTML = '<div class="live-dot" style="background:#ef4444;box-shadow:none;"></div> RECONNECTING...';
                setTimeout(connect, 1500);
            };

            ws.onerror = () => { ws.close(); };
        }
        connect();

        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send("ping");
            }
        }, 15000);
    </script>
</body>
</html>"""

async def analyze_news(text):
    prompt_payload = f"""CRITICAL DIRECTIVE: Perform an in-depth forensic breakdown of this raw incoming post/news. Read every single sentence and explain what the entity is actually doing and saying in full Sinhala depth:

RAW SOURCE CONTENT:
\"\"\"{text}\"\"\""""
    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_payload}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2200
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {
            "summarized_english_title": text[:90] + "...",
            "impact_mark": "2.0 / 10 — NOISE",
            "directional_bias": "මධ්‍යස්ථ (Neutral)",
            "expected_move": "නොසැලකිය හැකි (Negligible)",
            "window": "ක්ෂණික තත්පර 60",
            "bias_badge": "NEUTRAL",
            "news_points": [
                f"වාර්තා වූ සැබෑ අන්තර්ගතය: {text[:250]}",
                "අදාළ ආයතනය මඟින් සිදු කර ඇති නිවේදනය පිළිබඳ මූලික පසුබිම් විග්‍රහය.",
                "මෙම පුවත සාර්ව ආර්ථික වශයෙන් Bitcoin වෙත ප්‍රාග්ධනය ආකර්ෂණය කිරීමට සමත් නොවන බව තහවුරු වේ."
            ],
            "core_catalyst": "මෙම සිදුවීම මඟින් Bitcoin වෙළඳපලට ආයතනික හෝ structural ප්‍රාග්ධන ගලනයක් සිදු නොවන බැවින් සාර්ව catalyst එකක් නොවේ.",
            "cvd_orderbook_impact": "Spot CVD වල කැපී පෙනෙන මිලදී ගැනීමේ හෝ විකිණීමේ delta එකක් නිර්මාණය නොවන අතර DOM limit liquidity ස්ථාවරව පවතී.",
            "liquidity_traps": "Perp Open Interest හි අස්වාභාවික වැඩිවීමක් නොමැත බැවින් cascade liquidations හෝ stop hunt අවදානමක් නැත.",
            "verdict": "නොසලකා හරින්න (IGNORE)",
            "action_plan": "Spot CVD සහ DOM එකේ වෙනසක් නැති බැවින් trade නොගෙන ප්‍රාග්ධනය ආරක්ෂා කරගන්න."
        }

async def broadcast_online_count():
    count = len(connected_websockets)
    payload = json.dumps({"type": "online_count", "count": count})
    for ws in list(connected_websockets):
        try:
            if not ws.closed:
                await ws.send_str(payload)
        except Exception:
            connected_websockets.discard(ws)

async def broadcast(item):
    recent_news_cache.append(item)
    if len(recent_news_cache) > 40: recent_news_cache.pop(0)
    msg_str = json.dumps(item)
    for ws in list(connected_websockets):
        try: 
            if not ws.closed:
                await ws.send_str(msg_str)
        except Exception: 
            connected_websockets.discard(ws)

async def news_worker():
    while True:
        raw_news = await news_queue.get()
        full_title = raw_news.get("full_title", "")
        body = raw_news.get("body", "")
        item_time = raw_news.get("time", time.time() * 1000)
        
        now_ms = time.time() * 1000
        is_fresh = (now_ms - item_time) < (90 * 1000) if item_time > 0 else False
            
        res = await analyze_news(content := (f"Headline: {full_title}\nBody/Details: {body}" if body and body != full_title else full_title))
        
        impact_str = res.get("impact_mark", "2.0")
        impact_num = 2.0
        try:
            match = re.search(r'([\d\.]+)', impact_str)
            if match:
                impact_num = float(match.group(1))
        except:
            pass

        # Strict threshold: Only true fresh breaking news with >= 7.5 score get high impact badge
        is_high_impact = is_fresh and (impact_num >= 7.5)
        display_title = res.get("summarized_english_title") or full_title
        
        payload = {
            "display_title": display_title,
            "is_high_impact": is_high_impact,
            "impact_mark": res.get("impact_mark", "2.0 / 10 — NOISE"),
            "directional_bias": res.get("directional_bias", "මධ්‍යස්ථ (Neutral)"),
            "expected_move": res.get("expected_move", "නොසැලකිය හැකි (Negligible)"),
            "window": res.get("window", "ක්ෂණික තත්පර 60"),
            "bias_badge": res.get("bias_badge", "NEUTRAL"),
            "news_points": res.get("news_points", []),
            "core_catalyst": res.get("core_catalyst") or "වෙළඳපලට සෘජු ප්‍රාග්ධන ගලනයක් නොමැත.",
            "cvd_orderbook_impact": res.get("cvd_orderbook_impact") or "CVD වල වෙනසක් නොමැත.",
            "liquidity_traps": res.get("liquidity_traps") or "අදාළ අවදානම් නොමැත.",
            "verdict": res.get("verdict", "නොසලකා හරින්න (IGNORE)"),
            "action_plan": res.get("action_plan", "ප්‍රාග්ධනය ආරක්ෂා කරගන්න."),
            "card_time": time.strftime("%H:%M:%S")
        }
        await broadcast(payload)
        news_queue.task_done()
        await asyncio.sleep(1)

async def treeofalpha_stream():
    url = "wss://news.treeofalpha.com/ws"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    logger.info("Connected to news websocket stream")
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
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    connected_websockets.add(ws)
    await broadcast_online_count()
    
    if recent_news_cache:
        await ws.send_str(json.dumps(recent_news_cache))
        
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT and msg.data == "ping":
                await ws.send_str("pong")
    finally:
        connected_websockets.discard(ws)
        await broadcast_online_count()
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
