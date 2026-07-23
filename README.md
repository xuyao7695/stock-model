# 股票投资模型

> 个人股票投资的"纪律化交易系统"：**实盘选股 + 硬风控 + 交易纪律 + 三端呈现**。
> 数据源 akshare（A股实盘），选股逻辑 = 题材板块资金流 + 技术突破量能，不依赖大V。

## 📊 当前状态

- ✅ 实盘选股扫描器（akshare：涨停池 + 行业热度 + 全市场技术强势）
- ✅ 风控规则 + 交易纪律 → 操作建议生成器
- ✅ 三端呈现：企业微信机器人 / Streamlit 看板 / 独立 Flask 手机 App
- ✅ OCR 历史回测（246 笔交易 + 3 月汇总，见 `reports/行为诊断报告.md`）
- ✅ 行为诊断 + 5 张可视化图表

## 🗂 目录结构

```
stock_model/
├── data/
│   ├── trades.csv / monthly_summary.csv   # 历史 OCR 数据
│   ├── candidates.json                     # 扫描原始候选
│   └── advices.json                        # 带风控建议的结构化候选（看板/App 读这个）
├── screener/
│   ├── scan.py          # 实盘选股扫描器
│   ├── scan_config.json # 选股条件（可调）
│   ├── advise.py        # 风控 + 纪律 → 操作建议
│   ├── rules.py / rules.json  # 风控参数 + Checklist
├── delivery/
│   └── wecom_bot.py     # 企业微信群机器人推送
├── dashboard/
│   ├── app.py           # Streamlit 看板（兼 Web App）
│   └── standalone_app.py# 独立 Flask 手机 App
├── ocr/                 # OCR 历史数据流水线
├── analytics/           # 行为诊断
├── docs/投资模型框架.md
├── reports/             # 诊断报告 + 每日操作建议 + 图表
├── run_daily.py         # 一键流程：扫描 → 建议 → 推送
├── requirements.txt
└── README.md
```

## 🚀 每日使用

```bash
source venv/bin/activate

# 一键：扫描实盘 → 生成建议 → 推送企业微信
python run_daily.py

# 只看不推
python run_daily.py --no-push

# 三端呈现（任选）
streamlit run dashboard/app.py --server.port 8501      # 看板 / Web App
python dashboard/standalone_app.py                      # 手机 App (http://IP:5001)
python delivery/wecom_bot.py "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=XXX"  # 配置并测试机器人
```

## ⚙️ 调参

| 文件 | 调什么 |
|---|---|
| `screener/scan_config.json` | 选股条件：连板数、封单、炸板、行业热度、技术强势阈值 |
| `screener/rules.json` | 风控：单只/总仓上限、熔断、止损、盈亏比、日笔数、最大持仓 |

## 📋 技术栈

| 用途 | 工具 |
|---|---|
| 实盘数据 | akshare 1.18（东方财富） |
| OCR | PaddleOCR 2.7 + PaddlePaddle 2.6 |
| 数据处理 | pandas + numpy |
| 看板 | Streamlit 1.60 |
| 手机 App | Flask |
| 推送 | 企业微信机器人 webhook |
| 可视化 | matplotlib |

## ⚠️ 重要说明

1. **实盘接口限流**：东方财富对多接口高频访问会断连，已加延时重试；全市场 spot 限流时自动跳过（路径 B）。
2. **历史数据缺口**：OCR 仅含 2026-05 至 07 共 246 笔，需补充（见 `docs/投资模型框架.md` 第 8 节）。
3. **免责**：系统按规则生成建议，仅供参考，不构成投资建议。

## 📜 文档

- 投资模型框架：[docs/投资模型框架.md](docs/投资模型框架.md)
- 行为诊断报告：[reports/行为诊断报告.md](reports/行为诊断报告.md)
- 每日操作建议：[reports/每日操作建议.md](reports/每日操作建议.md)
