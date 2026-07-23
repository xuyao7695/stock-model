"""
列位感知的解析器：每行按 x 分为 3 列
- LEFT  (x<100):  A=操作+标的   B=日期+时间
- MID   (x 150-220): A=价格   B=数量
- RIGHT (x>240):  金额（可能 A+B 拼接）

A+B 配对规则：A 行后紧跟 y_gap 18-30px 的 B 行
"""
import re, json

with open("ocr/ocr_raw.json", encoding="utf-8") as f:
    raw = json.load(f)

# 行聚
raw_sorted = sorted(raw, key=lambda d: d["y"])
lines = []
cur = [raw_sorted[0]]
for it in raw_sorted[1:]:
    if abs(it["y"] - cur[-1]["y"]) <= 5:
        cur.append(it)
    else:
        lines.append(sorted(cur, key=lambda d: d["x"]))
        cur = [it]
lines.append(sorted(cur, key=lambda d: d["x"]))

# 列分类
def col(x):
    if x < 100: return "L"
    if x < 220: return "M"
    return "R"

# 把每行分成列
def split_cols(line):
    cols = {"L": [], "M": [], "R": []}
    for it in line:
        cols[col(it["x"])].append(it)
    return cols

# 清理金额字符串：去非数字符号、合并 A+B
def clean_amt(s):
    if s is None: return None
    s = s.replace(",", "").strip()
    s = re.sub(r'[^\d.\-]', '', s)
    if s in ("", "-", ".", "-.", ".-"): return None
    return s

def join_amt(a, b):
    """A.金额 + B.金额尾 → 完整数字"""
    a = clean_amt(a) if a else None
    b = clean_amt(b) if b else None
    if a is None and b is None: return None
    if a is None: return b
    if b is None: return a
    if a.endswith("."):
        a = a[:-1]
    if b.endswith("."):
        b = b[:-1]
    if not b:
        return a
    if "." in b:
        return f"{a}.{b.split('.')[1]}"
    return f"{a}.{b}"

# 正则
RE_OP = re.compile(r'^(证券买入|证券卖出|买入|卖出|申购配号|银行转取)(?:[-:：](.+))?$')
RE_BUY = re.compile(r'^[买卖申购银]')
RE_DATE = re.compile(r'(\d{2})[-/](\d{1,2})')
RE_TIME = re.compile(r'(\d{1,2}):(\d{2})')
RE_PRICE = re.compile(r'^-?\d{1,6}\.\d{3}$')
RE_QTY = re.compile(r'^\d{1,5}$')
RE_MONTHLY = re.compile(r'^\d{4}[-/]\d{1,2}$')

# 标题/汇总关键词
META_KEYS = ["区间盈亏", "上证", "平均仓位", "成功率", "盈利", "亏损", "持股", "税费",
             "交易股票数", "交易笔数", "本月", "近三", "近半", "今年", "全部", "自定义",
             "确定", "对账单", "广发", "详情", "操作", "价格", "数量"]

# 识别是否为汇总/标题行
def is_meta_line(text):
    return any(k in text for k in META_KEYS)

# 识别是否为月份行
def is_monthly_line(text):
    return bool(RE_MONTHLY.search(text))

records = []
i = 0
N = len(lines)

while i < N:
    line = lines[i]
    cols = split_cols(line)
    text_full = "".join(it["txt"] for it in line)
    y_a = line[0]["y"]
    L_text = "".join(it["txt"] for it in cols["L"]).strip()
    M_text = "".join(it["txt"] for it in cols["M"]).strip()
    R_text = "".join(it["txt"] for it in cols["R"]).strip()
    R_items = cols["R"]
    L_items = cols["L"]
    M_items = cols["M"]

    # 跳过元数据
    if i < 14 or is_meta_line(text_full) or len(line) <= 1 and not L_text:
        i += 1
        continue
    # 标题小标签如 "<" "L" "Y"
    if text_full in ("<", "L", "Y", "∧", "∨", "^", "v", ""):
        i += 1
        continue

    # 月度汇总行: "2026-07  -22,429.51  -23.23%  上证-5.74%"
    if is_monthly_line(L_text) or is_monthly_line(text_full[:10]):
        records.append({
            "type": "monthly",
            "y": y_a,
            "year_month": L_text,
            "summary_text": text_full,
        })
        i += 1
        continue

    # 判断是否为交易 A 行
    action = None
    name = None
    # 尝试 LEFT 第一个项匹配操作
    if L_items and RE_OP.match(L_items[0]["txt"]):
        action, name = RE_OP.match(L_items[0]["txt"]).groups()
        name = (name or "").strip()
    else:
        # 可能整行合并在 L_text
        m = RE_OP.match(L_text)
        if m:
            action, name = m.groups()
            name = (name or "").strip()
        else:
            # 跳过无法识别的
            i += 1
            continue

    # 找 B 行
    if i + 1 >= N:
        i += 1
        continue
    line_b = lines[i + 1]
    cols_b = split_cols(line_b)
    L_b = "".join(it["txt"] for it in cols_b["L"]).strip()
    M_b = "".join(it["txt"] for it in cols_b["M"]).strip()
    R_b_items = cols_b["R"]
    y_b = line_b[0]["y"]
    y_gap = y_b - y_a
    if not (10 <= y_gap <= 35):
        # 间距不对，跳过这一行
        i += 1
        continue

    # 解析 B 行日期+时间
    b_date = None
    b_time = None
    b_prefix = None  # 买/卖/申/银
    m_d = RE_DATE.search(L_b)
    if m_d:
        b_date = f"{m_d.group(1)}-{int(m_d.group(2)):02d}"
    m_t = RE_TIME.search(L_b)
    if m_t:
        b_time = f"{int(m_t.group(1)):02d}:{m_t.group(2)}"
    # 前缀字符
    pfx = re.match(r'^([买卖申购银])', L_b)
    if pfx:
        b_prefix = pfx.group(1)

    # 解析 B 行 数量
    b_qty = None
    if M_items and len(M_items) == 1 and RE_QTY.match(M_items[0]["txt"]):
        b_qty = M_items[0]["txt"]

    # 解析 A 行 价格 + 金额
    a_price = None
    a_amt = None
    for it in M_items:
        if RE_PRICE.match(it["txt"]):
            a_price = it["txt"]
            break
    for it in R_items:
        clean = it["txt"].replace(",", "")
        if re.match(r'^-?\d+\.?\d*$', clean):
            a_amt = it["txt"]
            break

    # 解析 B 行 金额尾
    b_amt_tail = None
    for it in R_b_items:
        clean = it["txt"].replace(",", "")
        if re.match(r'^-?\d+\.?\d*$', clean):
            b_amt_tail = it["txt"]
            break

    # 合成
    if action == "申购配号":
        amount = 0
        price = 0
        qty = int(b_qty) if b_qty else 0
    elif action == "银行转取":
        # A 行 R 列就是金额
        amount = clean_amt(a_amt) or clean_amt(R_text)
        try: amount = float(amount) if amount is not None else 0
        except: amount = 0
        price = None
        qty = None
    else:
        amount_str = join_amt(a_amt, b_amt_tail)
        try: amount = float(amount_str) if amount_str else 0
        except: amount = 0
        try: price = float(a_price) if a_price else None
        except: price = None
        try: qty = int(b_qty) if b_qty else None
        except: qty = None

    # 年份：图片内最近月份推断
    year = "2026"  # 大概率 2026
    full_date = f"{year}-{b_date}" if b_date else None

    records.append({
        "type": "trade",
        "y": y_a,
        "date": full_date,
        "time": b_time,
        "action": action,
        "name": name,
        "price": price,
        "qty": qty,
        "amount": amount,
    })
    i += 2  # 跳过 A+B

# 输出
trades = [r for r in records if r["type"] == "trade"]
monthly = [r for r in records if r["type"] == "monthly"]
print(f"交易 {len(trades)} 条, 月度汇总 {len(monthly)} 条")
print(f"其中 买入: {sum(1 for r in trades if '买入' in (r['action'] or ''))}")
print(f"     卖出: {sum(1 for r in trades if '卖出' in (r['action'] or ''))}")
print(f"     申购: {sum(1 for r in trades if r['action'] == '申购配号')}")
print(f"     银行: {sum(1 for r in trades if r['action'] == '银行转取')}")

print("\n--- 样例 1: 卖出 ---")
for r in trades[:3]:
    print(f"  y={r['y']:.0f} {r['date']} {r['time']} {r['action']:6s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")
print("--- 样例 2: 买入 ---")
for r in trades[3:7]:
    print(f"  y={r['y']:.0f} {r['date']} {r['time']} {r['action']:6s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")
print("--- 样例 3: 银行转取 ---")
for r in trades:
    if r['action'] == '银行转取':
        print(f"  y={r['y']:.0f} {r['date']} {r['action']:6s} 额={r['amount']}")
print("--- 样例 4: 末尾 ---")
for r in trades[-5:]:
    print(f"  y={r['y']:.0f} {r['date']} {r['time']} {r['action']:6s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")

# 校验：总盈亏
total_pnl = sum(r["amount"] for r in trades if r["action"] in ("卖出", "证券卖出", "买入", "证券买入", "银行转取"))
print(f"\n累计交易盈亏（粗算）: {total_pnl:.2f}")

# 月度
print("\n--- 月度汇总行 ---")
for m in monthly:
    print(f"  y={m['y']:.0f} {m['year_month']}  text={m['summary_text']}")

with open("ocr/records_v2.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
print("\n已保存 ocr/records_v2.json")
