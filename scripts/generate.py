import yfinance as yf
import pandas as pd
import json
import os
import time

# ── 读取配置 ──────────────────────────────────────
with open("config.json") as f:
    cfg = json.load(f)

TOTAL_CAPITAL    = cfg["total_capital"]
CURRENT_INVESTED = cfg["current_invested"]
CURRENT_POSITION_PCT = CURRENT_INVESTED / TOTAL_CAPITAL if TOTAL_CAPITAL else 0
MAX_SINGLE_BUY   = cfg.get("max_single_buy", 500)   # 单次加仓上限，默认500
LAST_OP          = cfg.get("last_operation", {})    # 上次操作记录

TICKER     = "^NDX"
RSI_PERIOD = 14
MA_PERIOD  = 200
# ──────────────────────────────────────────────────

def get_data():
    df = yf.download(TICKER, period="13mo", interval="1d",
                     progress=False, auto_adjust=True)
    df = df[["Close"]].dropna()
    df.columns = ["Close"]
    return df

def compute_indicators(df):
    delta    = df["Close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
    rs       = avg_gain / avg_loss.replace(0, float("inf"))
    df["RSI"] = 100 - (100 / (1 + rs))
    rolling_peak  = df["Close"].rolling(window=252, min_periods=1).max()
    df["Drawdown"] = (df["Close"] - rolling_peak) / rolling_peak
    df["MA200"]    = df["Close"].rolling(window=MA_PERIOD, min_periods=1).mean()
    df["Above_MA200"] = df["Close"] > df["MA200"]
    return df

def get_vix():
    """重试两次获取 VIX，失败时打印原因并返回 None"""
    for attempt in range(2):
        try:
            df = yf.download("^VIX", period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            val = df["Close"].dropna()
            if len(val) > 0:
                return round(float(val.iloc[-1]), 2)
            print(f"⚠️  VIX 第{attempt+1}次：返回数据为空")
        except Exception as e:
            print(f"⚠️  VIX 第{attempt+1}次失败：{e}")
        time.sleep(2)
    print("❌ VIX 获取失败，建议金额将保守打七折")
    return None

def determine_market_state(rsi, drawdown, vix, above_ma200):
    score = 0
    if rsi < 25:         score += 4
    elif rsi < 30:       score += 3
    elif rsi < 35:       score += 2
    elif rsi < 40:       score += 1
    if drawdown < -0.20:   score += 4
    elif drawdown < -0.15: score += 3
    elif drawdown < -0.10: score += 2
    elif drawdown < -0.05: score += 1
    if vix is not None:       # VIX 有数据才计分
        if vix > 35:    score += 3
        elif vix > 25:  score += 2
        elif vix > 20:  score += 1
    if not above_ma200:
        score -= 1
    if score <= 0:   return "市场正常",  "normal",   0.40
    elif score <= 2: return "轻度回调",  "mild",     0.55
    elif score <= 4: return "中度下跌",  "moderate", 0.70
    elif score <= 6: return "重度下跌",  "severe",   0.85
    else:            return "极端恐慌",  "panic",    0.95

def calculate_suggestion(target_pct, current_pct, total_capital, max_buy, vix_missing):
    gap = target_pct - current_pct
    if gap <= 0.02:
        return 0, "仓位已达目标，继续观望"
    raw = total_capital * gap / 2
    if vix_missing:
        raw = raw * 0.7   # VIX 缺失时保守打七折
    amount = min(round(raw), max_buy)
    if amount < 100:
        return 0, "差距过小，无需操作"
    return amount, None

def build_html(d):
    state_colors = {
        "normal":   "#22c55e",
        "mild":     "#eab308",
        "moderate": "#f97316",
        "severe":   "#ef4444",
        "panic":    "#dc2626",
    }
    sc = state_colors.get(d["state_key"], "#3b82f6")

    # 操作建议区块
    if d["suggest_amount"] > 0:
        vix_warn = ""
        if d["vix_missing"]:
            vix_warn = '<div class="vix-warn">⚠️ VIX 数据缺失，建议金额已保守打折</div>'
        suggest_html = f"""
        <div class="sug-amt">¥{d['suggest_amount']:,}</div>
        <div class="sug-sub">本次建议买入上限（每次最多 ¥{d['max_single_buy']:,}）</div>
        {vix_warn}"""
    else:
        suggest_html = f'<div class="sug-none">{d["no_action_reason"]}</div>'

    # VIX 显示
    vix_display = str(d["vix"]) if d["vix"] is not None else "N/A"
    vix_color   = 'style="color:#f97316"' if d["vix"] is None else ""

    ma_badge = (
        '<span class="badge-up">✓ 价格在均线上方</span>'
        if d["above_ma200"] else
        '<span class="badge-dn">↓ 价格低于均线</span>'
    )

    repo     = os.environ.get("GITHUB_REPOSITORY", "your-username/nasdaq-signal")
    edit_url = f"https://github.com/{repo}/edit/main/config.json"
    rsi_cls  = "pos" if d["rsi"] < 35 else ("neg" if d["rsi"] > 65 else "")
    dd_cls   = "pos" if d["drawdown_pct"] < -10 else ("ora" if d["drawdown_pct"] < -5 else "")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="纳指信号">
<meta name="theme-color" content="#0a0e1a">
<title>纳指定投信号</title>
<style>
:root {{
  --bg:#0a0e1a; --surface:#111827; --border:#1f2d45;
  --text:#e8edf5; --muted:#5a6a82; --accent:#3b82f6;
  --normal:#22c55e; --severe:#ef4444; --warn:#f97316;
  --state:{sc};
  --fm:'SF Mono','Fira Code','Consolas',monospace;
  --fs:-apple-system,'PingFang SC','Helvetica Neue',sans-serif;
  --st:env(safe-area-inset-top,0px); --sb:env(safe-area-inset-bottom,0px);
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{height:100%;background:var(--bg);color:var(--text);
  font-family:var(--fs);-webkit-font-smoothing:antialiased;}}
body{{padding:calc(var(--st) + 16px) 16px calc(var(--sb) + 16px);
  min-height:100dvh;display:flex;flex-direction:column;
  gap:10px;max-width:480px;margin:0 auto;}}
.hdr{{display:flex;justify-content:space-between;align-items:center;}}
.hdr-t{{font:600 11px/1 var(--fs);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}}
.hdr-d{{font:11px/1 var(--fm);color:var(--muted);}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;}}
.lbl{{font:600 10px/1 var(--fs);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px;}}
.state-card{{position:relative;overflow:hidden;}}
.state-card::before{{content:'';position:absolute;top:0;left:0;right:0;
  height:3px;background:var(--state);border-radius:14px 14px 0 0;}}
.state-val{{font:700 24px/1 var(--fs);color:var(--state);display:flex;align-items:center;gap:8px;}}
.state-dot{{width:9px;height:9px;border-radius:50%;background:var(--state);
  box-shadow:0 0 7px var(--state);flex-shrink:0;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.metric{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 15px;}}
.mv{{font:600 20px/1 var(--fm);color:var(--text);}}
.mv.pos{{color:var(--normal);}} .mv.neg{{color:var(--severe);}} .mv.ora{{color:var(--warn);}}
.msub{{font:10px/1 var(--fs);color:var(--muted);margin-top:4px;}}
.badge-up{{display:inline-block;font:10px/1 var(--fs);padding:3px 7px;
  border-radius:5px;background:#14291a;color:var(--normal);margin-top:5px;}}
.badge-dn{{display:inline-block;font:10px/1 var(--fs);padding:3px 7px;
  border-radius:5px;background:#2d1a1a;color:var(--severe);margin-top:5px;}}
.bar-track{{height:5px;background:var(--border);border-radius:99px;position:relative;margin:10px 0 6px;}}
.bar-fill{{height:100%;border-radius:99px;background:var(--accent);width:{min(d['current_position_pct'],100):.1f}%;}}
.bar-marker{{position:absolute;top:-4px;left:{min(d['target_position_pct'],100):.0f}%;
  width:2px;height:13px;background:var(--state);transform:translateX(-50%);border-radius:1px;}}
.bar-labels{{display:flex;justify-content:space-between;font:10px/1 var(--fs);color:var(--muted);}}
.bar-tgt{{color:var(--state);font-weight:600;}}
.sug-amt{{font:700 30px/1 var(--fm);color:var(--normal);}}
.sug-sub{{font:11px/1 var(--fs);color:var(--muted);margin-top:4px;}}
.sug-none{{font:14px/1.4 var(--fs);color:var(--muted);}}
.vix-warn{{margin-top:8px;padding:7px 10px;background:#2a1f0a;border:1px solid #5a3e0a;
  border-radius:8px;font:11px/1.4 var(--fs);color:#f59e0b;}}
.upd-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;}}
.upd-desc{{font:12px/1.5 var(--fs);color:var(--muted);margin-bottom:12px;}}
.upd-link{{display:block;text-align:center;background:var(--accent);color:#fff;
  text-decoration:none;border-radius:10px;padding:13px;font:600 14px/1 var(--fs);}}
.upd-link:active{{opacity:.7;}}
.footer{{font:10px/1.6 var(--fs);color:var(--muted);text-align:center;padding-bottom:4px;}}
</style>
</head>
<body>
<div class="hdr">
  <span class="hdr-t">纳指定投</span>
  <span class="hdr-d">{d['date']} 更新</span>
</div>
<div class="card state-card">
  <div class="lbl">市场状态</div>
  <div class="state-val"><div class="state-dot"></div>{d['state_label']}</div>
</div>
<div class="grid">
  <div class="metric">
    <div class="lbl">RSI · 14日</div>
    <div class="mv {rsi_cls}">{d['rsi']}</div>
    <div class="msub">{d['rsi_hint']}</div>
  </div>
  <div class="metric">
    <div class="lbl">近1年回撤</div>
    <div class="mv {dd_cls}">{d['drawdown_pct']}%</div>
    <div class="msub">{d['drawdown_hint']}</div>
  </div>
  <div class="metric">
    <div class="lbl">VIX 恐慌</div>
    <div class="mv" {vix_color}>{vix_display}</div>
    <div class="msub">{d['vix_hint']}</div>
  </div>
  <div class="metric">
    <div class="lbl">200日均线</div>
    <div class="mv" style="font-size:16px">{d['ma200']:,.0f}</div>
    {ma_badge}
  </div>
</div>
<div class="card">
  <div class="lbl">仓位 &nbsp; 当前 {d['current_position_pct']:.1f}% → 目标 {d['target_position_pct']:.0f}%</div>
  <div class="bar-track">
    <div class="bar-fill"></div>
    <div class="bar-marker"></div>
  </div>
  <div class="bar-labels">
    <span>0%</span>
    <span class="bar-tgt">目标 {d['target_position_pct']:.0f}%</span>
    <span>100%</span>
  </div>
</div>
<div class="card">
  <div class="lbl">操作建议</div>
  {suggest_html}
</div>
<div class="upd-card">
  <div class="lbl">更新仓位</div>
  <div class="upd-desc">
    加仓或减仓后点下方按钮，在 GitHub 同步更新两个字段：<br>
    · <code style="color:var(--accent)">current_invested</code> → 操作后的持仓总金额<br>
    · <code style="color:var(--accent)">last_operation</code> → 本次操作记录（type 填 buy 或 sell）
  </div>
  {last_op_html}
  <a class="upd-link" href="{edit_url}" target="_blank">✏️ 去 GitHub 更新</a>
</div>
<div class="footer">每天北京时间 9:00 自动更新 · 仅供参考，不构成投资建议</div>
</body>
</html>"""

def _build_last_op_html(op):
    """生成上次操作记录的 HTML 小卡片"""
    if not op or not op.get("type"):
        return ""
    op_type  = op.get("type", "buy")
    amount   = op.get("amount", 0)
    date     = op.get("date", "")
    note     = op.get("note", "")
    color    = "#22c55e" if op_type == "buy" else "#f97316"
    label    = "买入" if op_type == "buy" else "卖出"
    sign     = "+" if op_type == "buy" else "-"
    note_str = f" · {note}" if note else ""
    return (
        f'<div style="margin-top:10px;padding:8px 11px;background:var(--bg);'
        f'border:1px solid var(--border);border-radius:9px;'
        f'font:11px/1.5 var(--fs);color:var(--muted);">'
        f'上次操作：<span style="color:{color};font-weight:600;">{label} ¥{amount:,}</span>'
        f' &nbsp;{date}{note_str}</div>'
    )


def main():
    print("拉取数据中...")
    df  = get_data()
    df  = compute_indicators(df)
    vix = get_vix()
    vix_missing = vix is None

    latest   = df.iloc[-1]
    rsi      = round(float(latest["RSI"]), 1)
    drawdown = round(float(latest["Drawdown"]) * 100, 2)
    above_ma = bool(latest["Above_MA200"])
    ma200    = float(latest["MA200"])
    date_str = df.index[-1].strftime("%Y-%m-%d")

    def rsi_hint(v):
        if v < 25: return "严重超卖 🔥"
        if v < 35: return "超卖区间"
        if v < 45: return "偏低"
        if v < 55: return "中性"
        if v < 65: return "偏高"
        return "超买区间"

    def vix_hint(v):
        if v is None: return "获取失败，建议已打折"
        if v > 35: return "极度恐慌"
        if v > 25: return "市场恐慌"
        if v > 20: return "轻度紧张"
        return "市场平稳"

    def drawdown_hint(v):
        if v < -20: return "距高点超20%"
        if v < -15: return "距高点超15%"
        if v < -10: return "距高点超10%"
        if v < -5:  return "轻度回撤"
        return "接近高位"

    state_label, state_key, target_pct = determine_market_state(
        rsi, drawdown / 100, vix, above_ma)
    suggest_amount, no_action_reason = calculate_suggestion(
        target_pct, CURRENT_POSITION_PCT, TOTAL_CAPITAL, MAX_SINGLE_BUY, vix_missing)

    d = {
        "date":                 date_str,
        "rsi":                  rsi,
        "rsi_hint":             rsi_hint(rsi),
        "drawdown_pct":         drawdown,
        "drawdown_hint":        drawdown_hint(drawdown),
        "vix":                  round(vix, 1) if vix else None,
        "vix_hint":             vix_hint(vix),
        "vix_missing":          vix_missing,
        "above_ma200":          above_ma,
        "ma200":                ma200,
        "state_label":          state_label,
        "state_key":            state_key,
        "current_position_pct": round(CURRENT_POSITION_PCT * 100, 1),
        "target_position_pct":  round(target_pct * 100),
        "suggest_amount":       suggest_amount,
        "no_action_reason":     no_action_reason,
        "max_single_buy":       MAX_SINGLE_BUY,
        "last_op_html":         _build_last_op_html(LAST_OP),
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_html(d))

    vix_str = f"{vix}" if vix else "获取失败"
    print(f"✓ {date_str} | {state_label} | RSI {rsi} | 回撤 {drawdown}% | VIX {vix_str}")

if __name__ == "__main__":
    main()
