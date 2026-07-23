# 股票投资模型系统 — 项目备忘

> **最后更新**：2026-07-23 21:00
> **仓库地址**：https://github.com/xuyao7695/stock-model.git
> **线上APP**：https://xuyao7695.github.io/stock-model/
> **企业微信群机器人**：webhook key已配置在GitHub Secrets和本地`delivery/wecom_config.json`中
> **GitHub Token**：`ghp_***`（存储在本地安全位置，过期需重新生成）

---

## 一、系统总览

```
┌──────────────────────────────────────────────────────────┐
│                    每日自动流程                            │
│                                                          │
│  GitHub Actions (周一至五 9:25 北京时间)                   │
│    ├─ scan.py         涨停池选股（路径A/B）                │
│    ├─ advise.py       风控建议生成                         │
│    ├─ history.py      存档当日数据                         │
│    ├─ recommendation_stats.py  推荐涨跌追踪               │
│    ├─ portfolio_stats.py      盈亏汇总                    │
│    ├─ generate_web_data.py    生成bundle.json             │
│    ├─ wecom_image.py   推送Top6图片到企业微信              │
│    └─ git commit & push   数据回写仓库                    │
│                                                          │
│  GitHub Pages 自动部署 → 手机浏览器访问                    │
└──────────────────────────────────────────────────────────┘
```

---

## 二、APP页面结构（5页，左右滑动切换）

| 页面 | 功能 | 当前状态 |
|------|------|---------|
| 🏠 首页 | 今日候选Top6 + 一键复制代码 + 风控参数条 | ✅ |
| 📝 录入 | 买卖/名称/单价/数量/持股金额/理由 → 保存到localStorage | ✅ |
| 📊 统计 | 盈亏汇总 + 月度统计 + 当前持仓 + 推荐涨跌统计 | ✅（持仓已清空） |
| 📜 历史 | 近10天推荐，6列方格布局，板块名完整显示，红涨绿跌 | ✅ |
| ⚙️ 规则 | 风控规则7项参数展示 | ✅ |

### 页面切换技术细节
- 滑动阈值30px，X/Y比≥1.2才算横向手势
- CSS `overscroll-behavior-x:none; touch-action:pan-y` 禁用浏览器后退手势
- `touchmove` 用 `passive:false` + `preventDefault()` 拦截右滑退出
- 切页有淡出淡入动画（0.12s + 0.2s）

### 录入页面当前布局
```
[买入/卖出 ▼] [股票名称]
[单价] [数量] [持股金额（自动计算）]
[买入理由（必填）]
[💾 保存记录]

📋 最近10笔操作
  股票名称  200股  1,700  买
  📝 买入理由内容
  ─────────────────────
  ...
```

- 记录保存在浏览器localStorage（`stock_model_records_v1`）
- 换手机/清缓存会丢失本地记录
- 已取消：股票代码输入框、盈亏输入框、JSON复制区

---

## 三、两套选股策略

### 策略一：涨停连板战法（路径A/B）

| 路径 | 数据源 | 核心条件 |
|------|--------|---------|
| A-连板 | 涨停池 stock_zt_pool_em | 连板数1-5 + 封单≥3000万 + 未炸板 + 行业热度 |
| B-强势 | 全市场 stock_zh_a_spot_em | 涨幅3-9.4% + 换手≥3% + 量比≥1.5 |

**去重规则**：同板块最多2只，取评分Top6

### 策略二：K线形态+量能（路径C）

| 信号 | 权重 | 止损 | 目标 | 仓位系数 |
|------|------|------|------|---------|
| 放量突破 | 0.25 | -5% | +15% | 1.00 |
| 缩量回踩 | 0.20 | -6% | +12% | 0.90 |
| 倍量柱 | 0.15 | -7% | +15% | 0.80 |
| 早晨之星 | 0.15 | -5% | +10% | 0.70 |
| 红三兵 | 0.10 | -5% | +12% | 0.85 |
| 锤头线 | 0.10 | -4% | +8% | 0.60 |
| 阳包阴 | 0.15 | -5% | +10% | 0.75 |

- 文档：`docs/kline_strategy.md`
- 配置：`screener/kline_config.json`
- 扫描：`screener/kline_scan.py`
- 建议：`screener/kline_advise.py`
- **注意**：K线策略尚未接入GitHub Actions自动流程，需手动运行或后续集成

---

## 四、风控规则（screener/rules.json）

| 参数 | 值 | 说明 |
|------|-----|------|
| 单只仓位上限 | 30% | 单只股票最多占总资金30% |
| 总仓位上限 | 80% | 永远留20%现金 |
| 日亏熔断 | -5% | 当日亏5%强制停手 |
| 单笔硬止损 | -8% | 单笔最大亏损8% |
| 最小盈亏比 | 2.0 | 目标/止损 ≥ 2 |
| 日最大交易 | 3笔 | 每天最多交易3次 |
| 最大持仓天数 | 10天 | 到期强制复盘 |

---

## 五、文件结构

```
stock-model/
├── .github/workflows/daily_scan.yml   # GitHub Actions 每日9:25自动扫描
├── .gitignore                         # 敏感数据排除规则
├── docs/
│   ├── index.html                     # ★ 手机APP主页面（601行）
│   ├── data/
│   │   ├── bundle.json                # 前端数据包（候选+历史+规则）
│   │   ├── portfolio.json             # 盈亏汇总（当前空）
│   │   └── recommendation_stats.json  # 推荐涨跌统计
│   ├── kline_strategy.md              # K线策略文档
│   ├── 投资模型框架.md
│   ├── Oracle部署教程.md               # （已弃用）
│   └── Render部署教程.md               # （已弃用）
├── screener/
│   ├── scan.py                        # 涨停池选股扫描器
│   ├── scan_config.json               # 扫描条件配置
│   ├── advise.py                      # 风控建议生成器
│   ├── kline_scan.py                  # K线形态扫描器（7种信号）
│   ├── kline_advise.py                # K线策略建议生成器
│   ├── kline_config.json              # K线策略配置
│   ├── rules.json                     # 风控规则参数
│   ├── rules.py                       # 规则加载模块
│   ├── history.py                     # 历史存档
│   ├── generate_web_data.py           # 生成bundle.json
│   ├── portfolio_stats.py             # FIFO盈亏计算
│   ├── recommendation_stats.py        # 推荐1/3/5/10日涨跌追踪
│   └── sync_github.py                 # GitHub同步
├── delivery/
│   ├── wecom_image.py                 # 企业微信图片推送
│   ├── wecom_bot.py                   # 企业微信文本推送
│   └── wecom_config.json              # webhook配置（gitignore）
├── data/
│   ├── candidates.json                # 候选池
│   ├── advices.json                   # 操作建议
│   ├── portfolio.json                 # 盈亏数据
│   ├── recommendation_stats.json      # 推荐统计
│   ├── trades.csv                     # 交易记录（gitignore，本地保留）
│   ├── monthly_summary.csv            # 月度汇总（gitignore）
│   └── history/                       # 每日存档（*_trades.json gitignore）
├── ocr/                               # OCR交易记录解析（历史用）
├── analytics/diagnosis.py             # 交易行为诊断
├── dashboard/                         # Streamlit仪表盘（本地用）
├── reports/                           # 报告输出
├── requirements.txt                   # Python依赖
└── requirements-render.txt            # Render部署依赖
```

### .gitignore 排除的敏感文件
```
data/trades.csv              # 交易记录
data/history/*_trades.json   # 每日交易存档
data/monthly_summary.csv     # 月度汇总
delivery/wecom_config.json   # 微信webhook
ocr/*.json                   # OCR原始数据
```

---

## 六、数据文件说明

### bundle.json（前端核心数据包）
- 路径：`docs/data/bundle.json`
- 内容：`generated_at` + `today` + `rules` + `history_10days` + `days_detail`
- `days_detail` 中每天的 `advices` 来自 `advices.json` 的去重Top6
- 由 `generate_web_data.py` 生成

### portfolio.json（盈亏数据）
- 路径：`docs/data/portfolio.json`
- 当前状态：**空**（已删除中国西电案例持仓）
- 字段：`total_trades`, `realized_count`, `cumulative_pnl`, `monthly`, `current_holdings`, `recent_realized`
- 由 `portfolio_stats.py` 从 `data/history/*_trades.json` 生成

### recommendation_stats.json（推荐统计）
- 路径：`docs/data/recommendation_stats.json`
- 追踪推荐股票的1/3/5/10日收益

---

## 七、GitHub Actions 自动流程

**触发时间**：周一至周五北京时间9:25（UTC 1:25）

**执行步骤**：
1. `scan.py` — 涨停池选股
2. `advise.py` — 生成风控建议
3. `history.py` — 存档
4. `recommendation_stats.py` — 推荐统计
5. `portfolio_stats.py` — 盈亏汇总
6. `generate_web_data.py` — 生成前端数据包
7. `wecom_image.py` — 推送Top6图片到企业微信
8. `git commit & push` — 数据回写仓库

**注意**：K线策略（kline_scan.py / kline_advise.py）尚未加入workflow

---

## 八、部署信息

| 项目 | 地址/状态 |
|------|----------|
| GitHub仓库 | https://github.com/xuyao7695/stock-model.git |
| 仓库可见性 | public（GitHub Pages需要公开仓库） |
| GitHub Pages | https://xuyao7695.github.io/stock-model/ |
| Pages来源 | Deploy from branch / main / docs |
| 企业微信机器人 | key=a4526d71-9f5a-4ab3-9f07-b75dcdf7ef37 |
| WECOM_WEBHOOK secret | 已配置在GitHub Secrets中 |
| 数据源 | akshare（东方财富） |
| Python版本 | 3.11 |

### 推送命令（token过期时更新）
```bash
git -C /workspace/stock_model remote set-url origin https://xuyao7695:<TOKEN>@github.com/xuyao7695/stock-model.git
git -C /workspace/stock_model push origin main
git -C /workspace/stock_model remote set-url origin https://github.com/xuyao7695/stock-model.git
```

---

## 九、交易行为诊断结论（基于OCR解析的246笔历史交易）

- **胜率**：57.3%
- **盈亏比**：0.49（赚小亏大）
- **日均交易**：3.3笔（过于频繁）
- **核心问题**：赚就跑、亏就扛，没有纪律性止盈止损
- **诊断报告**：`reports/行为诊断报告.md`（gitignore，本地保留）

---

## 十、待办/后续可调整项

- [ ] K线策略接入GitHub Actions自动流程
- [ ] 录入页localStorage记录导出/备份功能
- [ ] 推荐统计积累30个样本后评估各信号有效性
- [ ] token过期后需重新生成（当前token有有效期）
- [ ] 录入页记录如需同步到服务端，需开发API接口

---

## 十一、关键代码位置速查

| 功能 | 文件 | 关键行 |
|------|------|--------|
| 页面滑动切换 | docs/index.html | touchstart/touchmove/touchend 监听 |
| 首页候选展示 | docs/index.html | renderHome() |
| 录入表单 | docs/index.html | renderRecord() |
| 本地记录保存 | docs/index.html | saveRecord() / loadLocalRecords() |
| 历史页6列方格 | docs/index.html | renderHistory() grid-template-columns:repeat(6,1fr) |
| 统计页 | docs/index.html | renderStats() |
| 风控规则展示 | docs/index.html | renderRules() |
| 数据加载 | docs/index.html | loadData() |
| 涨停选股 | screener/scan.py | scan_limit_up() / scan_strong() |
| K线选股 | screener/kline_scan.py | 7个signal_c*()函数 |
| 风控闸门 | screener/advise.py | risk_gate() |
| FIFO盈亏 | screener/portfolio_stats.py | calc_pnl_fifo() |
| 前端数据包 | screener/generate_web_data.py | main() |
| 微信推送 | delivery/wecom_image.py | matplotlib渲染PNG |

---

> ⚠️ **安全提醒**：本文档包含GitHub token和企业微信webhook密钥，请妥善保管，不要分享到公开渠道。
