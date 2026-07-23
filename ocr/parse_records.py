"""
把 OCR 行解析成结构化交易记录。

每条交易占 2 行（A+B）：
- A:  "操作-标的" | "价格" | "金额."
- B:  "动作前缀" + "日期 时间" | "数量" | "金额尾数"

另外要识别：
- 月度汇总行（如  "2026-07  -22,429.51  -23.23%  上证-5.74%"）
- 申购配号（价格=0, 数量=0, 金额=0）
- 银行转取（无标的）
- 标题/汇总行（跳过）
"""
import re, json
from collections import OrderedDict

with open("ocr/ocr_raw.json", encoding="utf-8") as f:
    raw = json.load(f)

# 按 y 聚行（更紧的 tol 避免把多行压一行）
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
print(f"重聚: {len(lines)} 行")

# 正则
RE_OP_STOCK = re.compile(r'^(证券买入|证券卖出|买入|卖出|申购配号|银行转取)(?:[-:：](.+))?$')
RE_DATE = re.compile(r'^(\d{2})[-/](\d{1,2})(?:[ ]?(\d{1,2}):(\d{2}))?$')
RE_PRICE = re.compile(r'^-?\d{1,6}\.\d{2,3}$')
RE_QTY = re.compile(r'^-?\d{1,5}(?:\.\d+)?$')
RE_AMT = re.compile(r'^-?[\d,]*\.\d+$|^-?[\d,]+$')
RE_MONTHLY = re.compile(r'^\d{4}[-/](0?[1-9]|1[0-2])$')

def join_txt(line):
    return "".join(it["txt"] for it in line).strip()

def split_action_stock(action_text):
    """'证券买入-光库科技' 或 '卖出-光库科技' → ('证券买入','光库科技')"""
    m = re.match(r'^(证券买入|证券卖出|买入|卖出|申购配号|银行转取)(?:[-:：](.+))?$', action_text)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    return None, action_text

def parse_amount_tail(parts):
    """A.金额 + B.金额尾 → 完整金额"""
    # A 行: 金额.X（如 -25,004.5）
    # B 行: 金额尾（如 5.1）
    a, b = parts
    if a.endswith("."):
        a = a[:-1]
    if b.endswith("."):
        b = b[:-1]
    if not a and not b:
        return None
    if not b:
        return a
    return f"{a}.{b}"

records = []
skipped = []

i = 0
while i < len(lines):
    line_a = lines[i]
    txt_a = "".join(it["txt"] for it in line_a)
    y_a = line_a[0]["y"]

    # 跳过标题/汇总/月份/单标签
    if i < 14:
        skipped.append(("header", y_a, txt_a))
        i += 1
        continue
    if RE_MONTHLY.match(txt_a):
        # 月度汇总
        # 找右侧的金额和百分比
        m = RE_MONTHLY.match(txt_a)
        records.append({
            "type": "monthly_summary",
            "year_month": txt_a,
            "y": y_a,
            "raw": txt_a,
        })
        i += 1
        continue
    if "区间盈亏" in txt_a or "上证" in txt_a or "平均仓位" in txt_a or "成功率" in txt_a \
       or "盈利" in txt_a or "亏损" in txt_a or "持股" in txt_a or "税费" in txt_a \
       or "交易" in txt_a or "本月" in txt_a or "近三" in txt_a or "近半" in txt_a \
       or "今年" in txt_a or "全部" in txt_a or "自定义" in txt_a or "确定" in txt_a \
       or "操作" == txt_a or "价格" in txt_a or "对账单" in txt_a or "广发" in txt_a:
        skipped.append(("meta", y_a, txt_a))
        i += 1
        continue

    # 看是否是交易 A 行（操作-标的 + 价格 + 金额.X）
    if i + 1 >= len(lines):
        skipped.append(("incomplete", y_a, txt_a))
        i += 1
        continue
    line_b = lines[i + 1]
    txt_b = "".join(it["txt"] for it in line_b)
    y_b = line_b[0]["y"]
    y_gap = y_b - y_a

    # A 行第一个项应是操作+标的
    a_first = line_a[0]
    a_first_txt = a_first["txt"]

    # 月份 A 行: "2026-07" (只是数字)
    if RE_MONTHLY.match(a_first_txt.strip()):
        records.append({"type": "monthly_summary", "year_month": a_first_txt, "y": y_a, "raw": txt_a})
        i += 1
        continue

    # 判断是否交易 A 行
    action = None
    name = None
    if RE_OP_STOCK.match(a_first_txt):
        action, name = split_action_stock(a_first_txt)
    elif a_first_txt in ("银行转取",) or a_first_txt.startswith("银行转取"):
        action, name = "银行转取", ""
    else:
        # 可能是跨行操作（如 "证券" + "买入-XXX"），先尝试合并 A 行内
        full_a = "".join(it["txt"] for it in line_a)
        if RE_OP_STOCK.match(full_a):
            action, name = split_action_stock(full_a)
        else:
            skipped.append(("unknown_a", y_a, txt_a))
            i += 1
            continue

    # A 行的右半：价格 + 金额.X
    a_right = line_a[1:]
    a_right_txts = [it["txt"] for it in a_right]

    price = None
    amount_a = None
    if action == "银行转取":
        # 没有价格和标的，金额直接给
        for t in a_right_txts:
            if RE_AMT.match(t.replace(",", "")) or "," in t:
                amount_a = t
                break
    elif action == "申购配号":
        # 数量是 1000 等
        pass
    else:
        # 找价格（带 3 位小数）和金额
        for t in a_right_txts:
            tt = t.replace(",", "")
            if RE_PRICE.match(tt) and price is None:
                price = t
            elif (RE_AMT.match(tt) or ("," in t and re.match(r'^-?[\d,]+\.?\d*$', tt))):
                amount_a = t
        # 若没找到金额，金额可能就在 价格右边
        if amount_a is None and len(a_right_txts) >= 2:
            amount_a = a_right_txts[-1]

    # B 行：日期 + 数量 + 金额尾
    b_items = line_b
    b_txts = [it["txt"] for it in b_items]
    # 把 B 行第一个项也看：可能是 "买07-22 13:32" 这种合并的
    b_date = None
    b_time = None
    b_qty = None
    b_amt_tail = None

    # 日期/时间/数量识别
    for idx, t in enumerate(b_txts):
        tt = t.replace(" ", "")
        m = re.match(r'^([买卖申购银])?(\d{2})[-/](\d{1,2})(?:(\d{1,2}):(\d{2}))?', tt)
        if m:
            b_date = f"{m.group(2)}-{m.group(3)}"
            if m.group(4) and m.group(5):
                b_time = f"{int(m.group(4)):02d}:{m.group(5)}"
            # 第一个 字符
            continue
        # 数量（小整数）
        if RE_QTY.match(t) and b_qty is None and t != "0":
            try:
                v = int(t) if "." not in t else float(t)
                if 1 <= v <= 1000000:
                    b_qty = t
            except: pass
        # 金额尾（"5." "5.1" 等）
        if re.match(r'^\d{1,3}\.?\d*$', t) and b_amt_tail is None:
            b_amt_tail = t

    # 合并金额
    if action == "申购配号":
        amount = "0.00"
        price_val = "0.000"
        qty = b_qty or "0"
    elif action == "银行转取":
        # A 行就是金额
        amount = amount_a or "0"
        price_val = None
        qty = None
    else:
        # 合并 A 金额 + B 尾
        if amount_a is not None and b_amt_tail is not None:
            amount = parse_amount_tail([amount_a, b_amt_tail])
        elif amount_a is not None:
            amount = amount_a
        else:
            amount = b_amt_tail
        price_val = price
        qty = b_qty

    records.append({
        "type": "trade",
        "y": y_a,
        "date": b_date,
        "time": b_time,
        "action": action,
        "name": name,
        "price": price_val,
        "qty": qty,
        "amount": amount,  # 解析后是 P&L 金额
    })
    i += 2  # 跳过 A+B

# 写出来
print(f"\n解析到 {len(records)} 条记录")
print(f"  交易: {sum(1 for r in records if r['type']=='trade')}")
print(f"  月度汇总: {sum(1 for r in records if r['type']=='monthly_summary')}")

# 跳过统计
print(f"\n跳过 {len(skipped)} 条元数据行")
for s in skipped[:10]:
    print(f"  {s}")

# 输出交易样例
print("\n--- 交易样例（前 10 条 + 后 5 条）---")
trades = [r for r in records if r["type"] == "trade"]
for r in trades[:10]:
    print(f"  y={r['y']:.0f} {r['date']} {r['time']} {r['action']:8s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")
print("  ...")
for r in trades[-5:]:
    print(f"  y={r['y']:.0f} {r['date']} {r['time']} {r['action']:8s} {r['name']:8s} 价={r['price']} 数量={r['qty']} 额={r['amount']}")

# 保存
with open("ocr/records.json", "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
print("\n已保存 ocr/records.json")
