"""
独立 Flask App（手机浏览器优化）v2
==================================
功能：
  - 首页：10 天历史滚动 + 当天候选 + 操作录入入口
  - /day/YYYY-MM-DD：某天详情（建议 + 实际 + 复盘对比）
  - /record：当日实际操作录入表单（手填）
  - /upload：截图上传 + OCR 识别
  - /review/YYYY-MM-DD：建议 vs 实际复盘
  - /history：所有历史日期列表（永久可查）

运行：python dashboard/standalone_app.py
访问：http://<本机IP>:5001  （手机同 WiFi 直接开）
"""
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, jsonify

app = Flask(__name__)
BASE = Path(".")
UPLOAD_DIR = BASE / "data/uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 加载历史模块 ----------
import importlib.util
spec = importlib.util.spec_from_file_location("history", BASE / "screener/history.py")
hist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hist)

# ---------- 页面模板 ----------

PAGE_HEAD = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>投资模型</title>
<style>
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; margin:0; padding:0; }
body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#0d1117; color:#e6edf3; padding:12px; padding-bottom:60px; }
a { color:#58a6ff; text-decoration:none; }
.top { display:flex; justify-content:space-between; align-items:center; padding:4px 0 8px; }
.title { font-size:20px; font-weight:700; }
.meta { font-size:11px; color:#8b949e; }
.card { background:#161b22; border:1px solid #30363d; border-radius:12px; padding:12px; margin-bottom:10px; }
.ch { display:flex; justify-content:space-between; align-items:baseline; }
.nm { font-size:17px; font-weight:700; }
.sc { font-size:13px; color:#d29922; }
.tag { font-size:11px; color:#8b949e; margin:4px 0 8px; }
.row { display:flex; gap:6px; margin:6px 0; }
.pill { flex:1; background:#0d1117; border-radius:8px; padding:6px; text-align:center; font-size:11px; }
.pill b { display:block; font-size:14px; }
.pos { color:#3fb950; } .neg { color:#f85149; } .warn { color:#d29922; }
.disc { font-size:11px; color:#8b949e; margin-top:6px; line-height:1.5; }
.nav { position:fixed; bottom:0; left:0; right:0; background:#161b22; border-top:1px solid #30363d; display:flex; padding:8px 0; z-index:100; }
.nav a { flex:1; text-align:center; font-size:12px; color:#8b949e; padding:4px; }
.nav a.active { color:#58a6ff; }
.nav a:active { background:#21262d; }
.btn { display:block; width:100%; background:#238636; color:#fff; border:none; border-radius:8px; padding:12px; font-size:16px; font-weight:600; text-align:center; margin:8px 0; }
.btn:active { background:#2ea043; }
.btn2 { background:#21262d; color:#58a6ff; border:1px solid #30363d; }
.btn2:active { background:#30363d; }
input,select,textarea { width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:8px; padding:10px; font-size:16px; margin:4px 0 8px; }
textarea { min-height:60px; }
label { font-size:13px; color:#8b949e; display:block; margin:4px 0 2px; }
.riskbar { display:flex; gap:4px; margin:8px 0; }
.rk { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:4px 6px; font-size:10px; text-align:center; flex:1; }
.rk b { display:block; font-size:13px; color:#58a6ff; }
.timeline { margin:8px 0; }
.tl-item { display:flex; gap:8px; padding:8px; background:#161b22; border-radius:8px; margin-bottom:6px; align-items:center; }
.tl-date { font-size:14px; font-weight:700; min-width:50px; }
.tl-info { font-size:11px; color:#8b949e; flex:1; }
.badge { font-size:10px; padding:2px 6px; border-radius:4px; margin-left:4px; }
.b-green { background:#1a3a2a; color:#3fb950; } .b-gray { background:#21262d; color:#8b949e; } .b-red { background:#3a1a1a; color:#f85149; }
.cmp { display:flex; gap:4px; font-size:12px; padding:4px 0; border-bottom:1px solid #21262d; }
.cmp div { flex:1; text-align:center; }
.cmp-h { color:#8b949e; font-size:11px; }
.empty { text-align:center; color:#8b949e; padding:40px 20px; font-size:14px; }
</style>
</head>
<body>
"""

PAGE_FOOT = """
<div class="nav">
  <a href="/" id="nav-home">🏠 首页</a>
  <a href="/record" id="nav-record">📝 录入</a>
  <a href="/upload" id="nav-upload">📷 截图</a>
  <a href="/history" id="nav-history">📜 历史</a>
</div>
</body></html>
"""


def rules():
    rp = BASE / "screener/rules.json"
    if rp.exists():
        with open(rp, encoding="utf-8") as f:
            return json.load(f)
    return {}


def render(title, body, active=""):
    nav_script = f"<script>document.getElementById('nav-{active}')?.classList.add('active');</script>"
    return PAGE_HEAD + f'<div class="top"><div class="title">{title}</div></div>' + body + PAGE_FOOT + nav_script


# ---------- 首页：10天滚动 + 当天候选 ----------
@app.route("/")
def index():
    today = datetime.now().strftime("%Y-%m-%d")
    # 10 天滚动
    history = hist.list_history(10)
    tl_html = ""
    for h in history:
        sc_badge = f'<span class="badge {"b-green" if h["scan_count"] else "b-gray"}">{h["scan_count"]}只</span>' if h["has_scan"] else '<span class="badge b-gray">无</span>'
        tr_badge = f'<span class="badge {"b-green" if h["trade_count"] else "b-gray"}">{h["trade_count"]}笔</span>' if h["has_trades"] else ""
        tl_html += f'<div class="tl-item" onclick="location.href=\'/day/{h["date"]}\'"><div class="tl-date">{h["date"][5:]}</div><div class="tl-info">周{h["weekday"]} {sc_badge} {tr_badge}</div></div>'

    # 当天候选
    r = rules()
    day_data = hist.load_day(today)
    scan = day_data.get("scan") or {}
    advices = sorted(scan.get("advices", []), key=lambda x: x.get("score", 0), reverse=True)
    cards = ""
    if not advices:
        cards = '<div class="empty">今天还没有扫描<br><a href="/scan">👉 点此扫描</a></div>'
    for c in advices[:10]:
        cards += f'''<div class="card">
          <div class="ch"><div class="nm">{c["name"]} <span style="font-size:12px;color:#8b949e">{c["code"]}</span></div><div class="sc">分{c["score"]:.2f}</div></div>
          <div class="tag">{c.get("path","")} ｜ 连板{c.get("zt_count",0)} ｜ {c.get("industry","")}</div>
          <div class="row">
            <div class="pill">仓位<b class="pos">{int(c.get("pos_pct",0)*100)}%</b></div>
            <div class="pill">止损<b class="neg">{int(c.get("stop_pct",-8)*100)}%</b></div>
            <div class="pill">目标<b class="pos">+{int(c.get("target_pct",15)*100)}%</b></div>
            <div class="pill">持仓<b>{c.get("max_hold_days",10)}天</b></div>
          </div>
        </div>'''

    risk_html = f'''<div class="riskbar">
      <div class="rk">单只<b>{int(r.get("max_single_position",0.3)*100)}%</b></div>
      <div class="rk">总仓<b>{int(r.get("max_total_position",0.8)*100)}%</b></div>
      <div class="rk">熔断<b>{int(r.get("daily_loss_circuit_breaker",-0.05)*100)}%</b></div>
      <div class="rk">日笔<b>{r.get("max_daily_trades",3)}</b></div>
    </div>'''

    body = f'''
    <div class="meta">最近10天 · 点任意日期查看详情</div>
    <div class="timeline">{tl_html}</div>
    <div style="margin:12px 0 4px;font-size:15px;font-weight:700">⚡ 今日候选（{len(advices)}只）</div>
    {risk_html}
    {cards}
    <a href="/record" class="btn">📝 录入今日实际操作</a>
    <a href="/scan" class="btn btn2">🔄 重新扫描</a>
    '''
    return render("📈 投资模型", body, "home")


# ---------- 某天详情 ----------
@app.route("/day/<date_str>")
def day_view(date_str):
    data = hist.load_day(date_str)
    scan = data.get("scan") or {}
    advices = sorted(scan.get("advices", []), key=lambda x: x.get("score", 0), reverse=True)
    trades_data = data.get("trades") or {}
    trades = trades_data.get("trades", [])

    cards = ""
    if not advices:
        cards = '<div class="empty">当天无扫描记录</div>'
    for c in advices:
        cards += f'''<div class="card">
          <div class="ch"><div class="nm">{c["name"]}</div><div class="sc">分{c["score"]:.2f}</div></div>
          <div class="tag">{c.get("path","")} ｜ 连板{c.get("zt_count",0)} ｜ {c.get("industry","")}</div>
          <div class="row">
            <div class="pill">仓位<b class="pos">{int(c.get("pos_pct",0)*100)}%</b></div>
            <div class="pill">止损<b class="neg">{int(c.get("stop_pct",-8)*100)}%</b></div>
            <div class="pill">目标<b class="pos">+{int(c.get("target_pct",15)*100)}%</b></div>
          </div>
        </div>'''

    trades_html = ""
    if trades:
        for t in trades:
            pnl = float(t.get("pnl", 0) or 0)
            pnl_cls = "pos" if pnl >= 0 else "neg"
            trades_html += f'''<div class="card">
              <div class="ch"><div class="nm">{t.get("name","")}</div><div class="sc {pnl_cls}">{pnl:+.0f}</div></div>
              <div class="tag">{t.get("action","")} ｜ {t.get("qty","")}股 ｜ {t.get("price","")}元 ｜ {t.get("time","")}</div>
              <div class="disc">{t.get("reason","")}</div>
            </div>'''
    else:
        trades_html = f'<div class="empty">当天无实际操作记录<br><a href="/record?date={date_str}">📝 补录</a></div>'

    body = f'''
    <div class="meta">{date_str} 详情</div>
    <div style="margin:8px 0 4px;font-size:15px;font-weight:700">📋 系统建议（{len(advices)}只）</div>
    {cards}
    <div style="margin:12px 0 4px;font-size:15px;font-weight:700">✋ 实际操作（{len(trades)}笔）</div>
    {trades_html}
    <a href="/review/{date_str}" class="btn btn2">📊 建议 vs 实际 复盘</a>
    <a href="/" class="btn btn2">← 返回首页</a>
    '''
    return render(f"📅 {date_str}", body)


# ---------- 录入表单 ----------
@app.route("/record", methods=["GET", "POST"])
def record():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    if request.method == "POST":
        date_str = request.form.get("date", date_str)
        trade = {
            "action": request.form.get("action", ""),
            "name": request.form.get("name", ""),
            "code": request.form.get("code", ""),
            "price": float(request.form.get("price", 0) or 0),
            "qty": int(request.form.get("qty", 0) or 0),
            "pnl": float(request.form.get("pnl", 0) or 0),
            "time": request.form.get("time", ""),
            "reason": request.form.get("reason", ""),
            "emotion": request.form.get("emotion", ""),
            "followed_plan": request.form.get("followed_plan", "off") == "on",
        }
        # 追加到当天记录
        existing = hist.load_day(date_str)
        trades_list = (existing.get("trades") or {}).get("trades", [])
        trades_list.append(trade)
        hist.archive_day_trades(date_str, trades_list)
        # 自动同步到 GitHub（Render 上防数据丢失）
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("sync", BASE / "screener/sync_github.py")
            sync = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sync)
            sync.sync_to_github()
        except: pass
        return redirect(url_for("day_view", date_str=date_str))

    body = f'''
    <div class="meta">录入实际操作 · {date_str}</div>
    <form method="post">
      <input type="hidden" name="date" value="{date_str}">
      <label>操作</label>
      <select name="action">
        <option value="证券买入">买入</option>
        <option value="证券卖出">卖出</option>
      </select>
      <label>标的名称</label>
      <input name="name" placeholder="如 光库科技" required>
      <label>代码（可选）label>
      <input name="code" placeholder="如 300620">
      <label>价格</label>
      <input name="price" type="number" step="0.01" placeholder="成交价" required>
      <label>数量（股）</label>
      <input name="qty" type="number" placeholder="如 100" required>
      <label>盈亏（卖出时填）</label>
      <input name="pnl" type="number" step="0.01" placeholder="盈利+ 亏损-">
      <label>时间</label>
      <input name="time" type="time" value="{datetime.now().strftime("%H:%M")}">
      <label>买入理由 / 情绪</label>
      <textarea name="reason" placeholder="为什么买？预期赚多少？止损位？"></textarea>
      <label>情绪标记</label>
      <select name="emotion">
        <option value="平静">平静</option>
        <option value="FOMO">FOMO 追涨</option>
        <option value="贪婪">贪婪</option>
        <option value="恐慌">恐慌</option>
        <option value="犹豫">犹豫</option>
      </select>
      <label><input type="checkbox" name="followed_plan"> 是否按系统建议操作？</label>
      <button type="submit" class="btn">💾 保存</button>
    </form>
    <a href="/day/{date_str}" class="btn btn2">← 返回当天</a>
    '''
    return render("📝 录入操作", body, "record")


# ---------- 截图上传 + OCR ----------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        if "file" not in request.files:
            return "未选择文件", 400
        f = request.files["file"]
        if not f.filename:
            return "未选择文件", 400
        # 保存
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = UPLOAD_DIR / f"{ts}_{f.filename}"
        f.save(str(save_path))
        date_str = request.form.get("date", datetime.now().strftime("%Y-%m-%d"))
        # OCR 识别（复用 ocr 模块）
        try:
            result = ocr_screenshot(str(save_path))
            if result:
                # 存档
                existing = hist.load_day(date_str)
                trades_list = (existing.get("trades") or {}).get("trades", [])
                trades_list.extend(result)
                hist.archive_day_trades(date_str, trades_list)
                return redirect(url_for("day_view", date_str=date_str))
            else:
                return render("📷 截图识别", '<div class="empty">未识别到有效交易<br><a href="/upload" class="btn btn2">重试</a></div>', "upload")
        except Exception as e:
            return render("📷 截图识别", f'<div class="empty">识别失败: {e}<br><a href="/upload" class="btn btn2">重试</a></div>', "upload")

    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    body = f'''
    <div class="meta">上传交易截图 · OCR 自动识别 · {date_str}</div>
    <form method="post" enctype="multipart/form-data">
      <input type="hidden" name="date" value="{date_str}">
      <label>选择截图（券商APP成交明细）</label>
      <input type="file" name="file" accept="image/*" capture="environment">
      <button type="submit" class="btn">📷 上传并识别</button>
    </form>
    <div class="card">
      <div class="tag">⚠️ 上传前请打码：账号、姓名、身份证、总资产。只需保留交易明细行。</div>
    </div>
    <a href="/record" class="btn btn2">✋ 改用手动录入</a>
    '''
    return render("📷 截图识别", body, "upload")


def ocr_screenshot(img_path):
    """调用 PaddleOCR 识别截图，返回交易列表"""
    import importlib.util
    # 用 ocr/ocr_full.py 的逻辑简化版
    spec = importlib.util.spec_from_file_location("paddleocr", "ocr/parse_v3.py")
    # 直接调用 PaddleOCR
    from paddleocr import PaddleOCR
    from PIL import Image
    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    result = ocr.ocr(img_path, cls=True)
    # 简单提取：找"买入/卖出"行
    trades = []
    if result and result[0]:
        for line in result[0]:
            txt = line[1][0]
            if "买入" in txt or "卖出" in txt:
                trades.append({
                    "action": "证券买入" if "买入" in txt else "证券卖出",
                    "name": txt.split("-")[-1] if "-" in txt else txt,
                    "price": 0, "qty": 0, "pnl": 0,
                    "time": "", "reason": "OCR识别",
                })
    return trades


# ---------- 触发扫描 ----------
@app.route("/scan")
def scan():
    import subprocess, sys
    subprocess.Popen([sys.executable, "screener/scan.py"], cwd=str(BASE))
    subprocess.Popen([sys.executable, "screener/advise.py"], cwd=str(BASE))
    body = '''
    <div class="empty">
      🔄 扫描已启动（约 30-60 秒）<br><br>
      <a href="/" class="btn">← 返回首页刷新查看</a>
    </div>
    '''
    return render("🔄 扫描中", body)


# ---------- 复盘对比 ----------
@app.route("/review/<date_str>")
def review(date_str):
    r = hist.review_day(date_str)
    comps = r["comparisons"]
    stats = r["stats"]
    rows = ""
    if not comps:
        rows = '<div class="empty">当天无建议或操作数据</div>'
    for c in comps:
        pnl_cls = "pos" if c["actual_pnl"] >= 0 else "neg"
        plan_icon = "✅" if c["followed_plan"] else "❌" if c["had_advice"] else "➕"
        rows += f'''<div class="card">
          <div class="ch"><div class="nm">{c["name"]}</div><div class="sc {pnl_cls}">{c["actual_pnl"]:+.0f}</div></div>
          <div class="cmp">
            <div><div class="cmp-h">建议</div>{c["advice_action"]}</div>
            <div><div class="cmp-h">实际</div>{c["actual_action"]}</div>
            <div><div class="cmp-h">数量</div>{c["actual_qty"]}</div>
            <div><div class="cmp-h">跟计划</div>{plan_icon}</div>
          </div>
        </div>'''
    body = f'''
    <div class="meta">{date_str} 建议 vs 实际</div>
    <div class="riskbar">
      <div class="rk">建议数<b>{stats["advice_count"]}</b></div>
      <div class="rk">跟计划<b style="color:#3fb950">{stats["followed"]}</b></div>
      <div class="rk">计划外<b style="color:#f85149">{stats["off_plan"]}</b></div>
      <div class="rk">总盈亏<b style="color:{"#3fb950" if stats["total_pnl"]>=0 else "#f85149"}">{stats["total_pnl"]:+.0f}</b></div>
    </div>
    {rows}
    <a href="/day/{date_str}" class="btn btn2">← 返回当天</a>
    '''
    return render(f"📊 复盘 {date_str}", body)


# ---------- 全部历史 ----------
@app.route("/history")
def history_all():
    dates = hist.list_all_history()
    if not dates:
        body = '<div class="empty">暂无历史记录</div>'
    else:
        items = ""
        for d in dates:
            data = hist.load_day(d)
            sc = data.get("scan") or {}
            tr = data.get("trades") or {}
            sc_n = len(sc.get("advices", [])) if sc else 0
            tr_n = len(tr.get("trades", [])) if tr else 0
            items += f'''<div class="tl-item" onclick="location.href='/day/{d}'">
              <div class="tl-date">{d}</div>
              <div class="tl-info">建议{sc_n}只 ｜ 操作{tr_n}笔</div>
            </div>'''
        body = f'<div class="meta">全部历史（{len(dates)}天）· 永久保留</div><div class="timeline">{items}</div>'
    return render("📜 全部历史", body, "history")


# ---------- 健康检查 / 保活端点 ----------
@app.route("/health")
def health():
    """Render 健康检查 + UptimeRobot 保活 ping"""
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/keepalive")
def keepalive():
    """保活端点，被 UptimeRobot 每 5 分钟 ping"""
    return "ok"


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
