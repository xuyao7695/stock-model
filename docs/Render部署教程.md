# Render 部署方案（免费）

> **方案**：Render 免费版 Web Service + GitHub 自动部署 + 保活防休眠
> **费用**：0 元/月
> **4G 访问**：✅ 手机浏览器开 `https://你的应用名.onrender.com`

---

## 方案概览

| 项 | 内容 |
|---|---|
| 平台 | Render.com（美国 PaaS，类似 Heroku） |
| 费用 | **永久免费**（Web Service Free 套餐） |
| 访问地址 | `https://stock-model.onrender.com`（自带 HTTPS） |
| 4G 可用 | ✅ 全球 CDN，国内 4G 可访问 |
| 限制 | 512MB 内存；**15 分钟无访问会休眠**，下次访问冷启动约 30-50 秒 |
| 保活方案 | 用 UptimeRobot 每 10 分钟 ping 一次，永不休眠 |

---

## 与 Oracle 对比

| 项 | Render 免费 | Oracle 免费 |
|---|---|---|
| 注册难度 | ⭐ 极简（GitHub 登录） | ⭐⭐⭐⭐ 难（信用卡风控） |
| 费用 | 0 元 | 0 元 |
| 内存 | 512MB（够跑 Flask，不够跑 PaddleOCR） | 24GB |
| 休眠 | 15 分钟无访问休眠 | 永不休眠 |
| 冷启动 | 30-50 秒 | 无 |
| 国内 4G 速度 | 中等（美国节点） | 快（日本节点 50ms） |
| HTTPS | ✅ 自带 | 需自己配 |
| 定时任务 | ❌ 免费版不支持 cron | ✅ 支持 crontab |

---

## 部署步骤（约 15 分钟）

### 第 1 步：代码推到 GitHub（5 分钟）

在本地：
```bash
cd /workspace/stock_model

# 初始化 git（如果还没有）
git init
git add .
git commit -m "股票投资模型 v0.3"

# 在 GitHub 上新建仓库 stock_model（Private 即可）
git remote add origin https://github.com/你的用户名/stock_model.git
git branch -M main
git push -u origin main
```

### 第 2 步：注册 Render（1 分钟）

1. 打开 https://render.com
2. 右上角 **Sign Up** → **用 GitHub 登录**
3. 授权 Render 访问你的 GitHub

### 第 3 步：创建 Web Service（5 分钟）

1. Render 控制台 → **New +** → **Web Service**
2. 连接你的 GitHub 仓库 `stock_model`
3. 配置：

| 项 | 填什么 |
|---|---|
| Name | `stock-model`（决定访问域名） |
| Region | Singapore（离中国最近）或 Oregon |
| Branch | `main` |
| Runtime | **Python 3** |
| Build Command | `pip install -r requirements-render.txt` |
| Start Command | `gunicorn dashboard.standalone_app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120` |
| Instance Type | **Free** |

4. 点击 **Create Web Service**
5. 等待 3-5 分钟（自动装依赖 + 启动）
6. 部署成功后，顶部显示 `https://stock-model.onrender.com`

### 第 4 步：配保活（2 分钟，关键！）

Render 免费版 15 分���无访问会休眠。用 UptimeRobot 免费保活：

1. 打开 https://uptimerobot.com → 注册
2. **Add New Monitor**
   - Monitor Type: HTTP(s)
   - Friendly Name: stock-model
   - URL: `https://stock-model.onrender.com`
   - Monitoring Interval: **5 minutes**
3. 保存

> 效果：每 5 分钟 ping 一次你的 App → Render 认为有人在访问 → 永不休眠。

### 第 5 步：手机访问

```
📱 手机浏览器打开：https://stock-model.onrender.com
```

- 4G / WiFi 都能用
- 自带 HTTPS（锁标）
- 加桌面书签当 App 用

---

## 注意事项

### 1. 内存限制（512MB）
- Flask + pandas + akshare：约 200-300MB，**够用**
- PaddleOCR：约 500MB+，**跑不了** → 截图 OCR 功能在 Render 上不可用，用 App 内表单录入
- 如果内存超了 Render 会重启服务（不影响数据，数据存在文件里）

### 2. 冷启动
即使有 UptimeRobot 保活，偶尔 Render 会维护重启。冷启动约 30-50 秒，表现为页面转圈。等一下就好。

### 3. 定时扫描
Render 免费版**不支持 cron**。两个替代方案：

| 方案 | 说明 |
|---|---|
| **GitHub Actions 定时** | 免费，每个交易日 9:25 自动跑扫描脚本，结果推企业微信 |
| **手动触发** | App 首页有「🔄 重新扫描」按钮，点一下就行 |

### 4. 数据持久性
Render 免费版的文件系统是**临时的**——每次部署/重启，非 Git 跟踪的文件会丢失。

**解决方案**：历史数据需要持久化到外部存储：

| 数据 | 持久化方式 |
|---|---|
| 交易日志（trades.csv） | ✅ 在 Git 仓库里，部署时自带 |
| 每日扫描结果（history/） | ⚠️ 需要额外存 GitHub 或云存储 |
| 操作录入记录 | ⚠️ 需要额外存 GitHub 或云存储 |

> 最简方案：每天的数据自动 commit 回 GitHub 仓库（我可以在代码里加这个逻辑）。

---

## 下一步

部署完成后告诉我你的 Render 域名，我帮你：
1. 配 GitHub Actions 定时扫描
2. 加数据自动备份到 GitHub 的逻辑
3. 优化冷启动速度
