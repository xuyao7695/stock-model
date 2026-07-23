"""
最终版解析器。明确 A 行 / B 行结构，每行只取自己的列。
"""
import re, json

with open("ocr/ocr_raw.json", encoding="utf-8") as f:
    raw = json.load(f)

# 1) 聚行
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

# 2) 列分类
def col(x):
    if x < 100: return "L"
    if x < 220: return "M"
    return "R"

# 3) 模式
RE_OP = re.compile(r'^(证券买入|证券卖出|买入|卖出|申购配号|银行转取)(?:[-:：](.+))?$')
RE_PRICE = re.compile(r'^-?\d{1,6}\.\d{3}$')
RE_QTY = re.compile(r'^\d{1,5}$')
RE_AMT_TAIL = re.compile(r'^\d{1,3}\.?\d*$')
RE_AMT_MAIN = re.compile(r'^-?[\d,]+\.?\d*$')
RE_DATE = re.compile(r'(\d{2})[-/](\d{1,2})')
RE_TIME = re.compile(r'(\d{1,2}):(\d{2})')
RE_MONTHLY = re.compile(r'\d{4}[-/]\d{1,2}')

META_KEYS = ["区间盈亏", "上证", "平均仓位", "成功率", "盈利", "亏损", "持股", "税费",
             "交易股票数", "交易笔数", "本月", "近三", "近半", "今年", "全部", "自定义",
             "确定", "对账单", "广发", "详情"]

def is_meta(text):
    return any(k in text for k in META_KEYS)

def clean(s):
    if s is None: return None
    s = s.replace(",", "").strip()
    s = re.sub(r'[^\d.\-]', '', s)
    if s in ("", "-", ".", "-.", ".-"): return None
    return s

def join_amt(a_raw, b_raw):
    """A 行金额 + B 行金额尾 → 完整数字（统一凑 2 位小数）
    例:
      a='47534.'    b='28'  → '47534.28'  (b 补 2 位)
      a='-13909.1'  b='5'   → '-13909.15' (a 已 1 位，b 补 1 位)
      a='-18409.1'  b='5.1' → '-18409.15' (b 的 '.' 是噪点，只取 1 位)
      a='10436.'    b='5.1' → '10436.51'  (b 真值 "51"，补 2 位)
      a='-13909'    b='5'   → '-13909.5'  (b 只有 1 位)
    """
    a = clean(a_raw)
    b = clean(b_raw)
    if a is None and b is None: return None
    if a is None: return b
    if b is None: return a
    a_s = a.rstrip(".")
    b_digits = re.sub(r'[^\d]', '', b) if b else ""
    if "." in a_s:
        a_int, a_dec = a_s.split(".", 1)
        need = max(0, 2 - len(a_dec))
        b_part = b_digits[:need] if need > 0 else ""
        return f"{a_int}.{a_dec}{b_part}" if (a_dec or b_part) else a_int
    else:
        b_part = b_digits[:2]
        return f"{a_s}.{b_part}" if b_part else a_s

records = []
i = 0
N = len(lines)

while i < N:
    line = lines[i]
    L = [it for it in line if col(it["x"]) == "L"]
    M = [it for it in line if col(it["x"]) == "M"]
    R = [it for it in line if col(it["x"]) == "R"]
    L_text = "".join(it["txt"] for it in L).strip()
    M_text = "".join(it["txt"] for it in M).strip()
    R_text = "".join(it["txt"] for it in R).strip()
    full_text = L_text + M_text + R_text
    y_a = line[0]["y"]

    # 跳过元数据
    if i < 14 or is_meta(full_text) or not L_text:
        # 但月度汇总例外（包含"上证"是正常的）
        if RE_MONTHLY.search(L_text) and "%" in full_text:
            m = RE_MONTHLY.search(L_text)
            records.append({"type": "monthly", "y": y_a, "year_month": m.group(0), "raw": full_text})
            i += 1
            continue
        i += 1
        continue
    if full_text in ("<", "L", "Y", "∨", "^", "v", ""):
        i += 1
        continue

    # 月度汇总
    if RE_MONTHLY.search(L_text) and "%" in full_text:
        m = RE_MONTHLY.search(L_text)
        records.append({"type": "monthly", "y": y_a, "year_month": m.group(0), "raw": full_text})
        i += 1
        continue

    # 找操作
    action = None
    name = None
    if L and RE_OP.match(L[0]["txt"]):
        m = RE_OP.match(L[0]["txt"])
        action = m.group(1)
        name = (m.group(2) or "").strip()
    else:
        m = RE_OP.match(L_text)
        if m:
            action = m.group(1)
            name = (m.group(2) or "").strip()
        else:
            i += 1
            continue

    # 找 B 行
    if i + 1 >= N:
        i += 1
        continue
    line_b = lines[i + 1]
    Lb = [it for it in line_b if col(it["x"]) == "L"]
    Mb = [it for it in line_b if col(it["x"]) == "M"]
    Rb = [it for it in line_b if col(it["x"]) == "R"]
    Lb_text = "".join(it["txt"] for it in Lb).strip()
    Mb_text = "".join(it["txt"] for it in Mb).strip()
    Rb_text = "".join(it["txt"] for it in Rb).strip()
    y_b = line_b[0]["y"]
    y_gap = y_b - y_a
    if not (10 <= y_gap <= 35):
        i += 1
        continue

    # 解析 B 行：日期/时间/前缀
    b_date = None
    b_time = None
    b_prefix = None
    md = RE_DATE.search(Lb_text)
    if md: b_date = f"{md.group(1)}-{int(md.group(2)):02d}"
    mt = RE_TIME.search(Lb_text)
    if mt: b_time = f"{int(mt.group(1)):02d}:{mt.group(2)}"
    pf = re.match(r'^([买卖申购银])', Lb_text)
    if pf: b_prefix = pf.group(1)

    # B 行 数量（Mb 的整数项）
    b_qty = None
    for it in Mb:
        if RE_QTY.match(it["txt"]):
            b_qty = it["txt"]
            break

    # A 行 价格（3 位小数）
    a_price = None
    for it in M:
        if RE_PRICE.match(it["txt"]):
            a_price = it["txt"]
            break

    # A 行 金额主体（R）
    a_amt = None
    for it in R:
        c = clean(it["txt"])
        if c is not None and RE_AMT_MAIN.match(c.replace(".", "", 1) if "." in c else c):
            # 避免把价格误认为金额
            if not RE_PRICE.match(it["txt"]):
                a_amt = it["txt"]
                break

    # B 行 金额尾（R_b）
    b_amt_tail = None
    for it in Rb:
        c = clean(it["txt"])
        if c is not None and RE_AMT_TAIL.match(c):
            b_amt_tail = it["txt"]
            break

    # 组装
    if action == "申购配号":
        amount = 0.0
        price = 0.0
        try: qty = int(b_qty) if b_qty else 0
        except: qty = 0
    elif action == "银行转取":
        amount_str = clean(a_amt) or clean(R_text) or clean(Rb_text) or "0"
        try: amount = float(amount_str)
        except: amount = 0.0
        price = None
        qty = None
    else:
        # 合并金额
        amount_str = join_amt(a_amt, b_amt_tail)
        try: amount = float(amount_str) if amount_str else 0.0
        except: amount = 0.0
        try: price = float(a_price) if a_price else None
        except: price = None
        try: qty = int(b_qty) if b_qty else None
        except: qty = None

    # 年份推断：图片覆盖 2026
    year = "2026"
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
    i += 2

# 输出
trades = [r for r in records if r["type"] == "trade"]
monthly = [r for r in records if r["type"] == "monthly"]
print(f"交易 {len(trades)} 条, 月度汇总 {len(monthly)} 条")
print(f"  买入: {sum(1 for r in trades if '买入' in r['action'])}")
print(f"  卖出: {sum(1 for r in trades if '卖出' in r['action'])}")
print(f"  申购: {sum(1 for r in trades if r['action'] == '申购配号')}")
print(f"  银行: {sum(1 for r in trades if r['action'] == '银行转取')}")

# 数量检查
qty_ok = sum(1 for r in trades if r["qty"] is not None)
print(f"\n有数量的: {qty_ok}/{len(trades)}")
amt_ok = sum(1 for r in trades if r["amount"] not in (0, None))
print(f"有金额的: {amt_ok}/{len(trades)}")

# 看无效样本
none_amt = [r for r in trades if r["amount"] in (0, None)]
print(f"\n无金额样本（前5）:")
for r in none_amt[:5]:
    print(f"  {r['date']} {r['time']} {r['action']} {r['name']} 价={r['price']} 数量={r['qty']} 额={r['amount']}")

# 输出末尾
print("\n--- 末尾 10 条 ---")
for r in trades[-10:]:
    print(f"  {r['date']} {r['time']} {r['action']:6s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")

# 月度
if monthly:
    print("\n--- 月度汇总 ---")
    for m in monthly:
        print(f"  {m['year_month']}  {m['raw']}")

# 累计
total_pnl = sum(r["amount"] for r in trades if r["action"] in ("卖出", "证券卖出", "买入", "证券买入", "银行转取"))
print(f"\n累计交易盈亏（粗算，忽略申购）: {total_pnl:.2f}")

with open("ocr/records_v3.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
print("\n已保存 ocr/records_v3.json")
