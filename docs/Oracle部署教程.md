# Oracle Cloud 免费部署教程

> **目标**：把股票投资模型 App 部署到 Oracle Cloud 永久免费服务器，手机 4G 随时访问。

---

## 一、方案概览

| 项 | 内容 |
|---|---|
| 云服务 | Oracle Cloud Always Free（永久免费） |
| 实例 | ARM Ampere A1 · 4核 24GB（免费额度内最大） |
| 系统 | Ubuntu 22.04 |
| 费用 | **0 元/月，永久免费** |
| 访问 | 手机浏览器输入 `http://<公网IP>` 直接开 |

---

## 二、注册 Oracle Cloud（约 15 分钟）

### 前置条件
- **外币信用卡**（Visa/MasterCard，用于验证身份，不会扣费）
- 手机号（接收验证码）
- Oracle 账号（用邮箱注册）

### 步骤

1. 打开 https://www.oracle.com/cn/cloud/free/
2. 点击「开始免费试用」
3. 填写：
   - 邮箱 + 密码
   - 手机号 + 验证码
   - **选择区域**：推荐 **日本东京（Japan East - Tokyo）** 或 **韩国春川（South Korea - Seoul）**，国内 4G 访问最快
   - 信用卡验证（扣 $1 验证，随后退回）
4. 等待账号激活（通常几分钟，偶尔需要几小时）

> ⚠️ 信用卡只是为了验证身份，**Always Free 资源不会产生费用**。只要不手动升级到付费套餐，就是永久免费。

---

## 三、创建 ARM 实例（约 10 分钟）

1. 登录 Oracle Cloud 控制台 → 左上角汉堡菜单 → **计算 → 实例**
2. 点击 **创建实例**
3. 配置：
   - **名称**：stock-model
   - **镜像**：Ubuntu 22.04（Canonical Ubuntu 22.04）
   - **配置**：点击「编辑」→ 选择 **VM.Standard.A1.Flex**
     - OCPU：**4**（免费额度 4 核）
     - 内存：**24 GB**（免费额度 24G）
   - **SSH 密钥**：选择「为我生成密钥对」→ 下载私钥 `.key` 和公钥 `.pub`（**务必保存好，丢了进不去服务器**）
   - 点击 **创建**

4. 等待 2-3 分钟，实例状态变绿色「运行中」

5. 记下 **公网 IP**（实例详情页显示，如 `138.3.x.x`）

---

## 四、开放安全组端口（约 2 分钟）

> Oracle Cloud 默认只开 22（SSH），需手动开 80（HTTP）。

1. 控制台 → 实例详情 → **子网**（点击进入）
2. **安全列表** → 默认安全列表
3. **添加入站规则**：
   - 来源 CIDR：`0.0.0.0/0`
   - IP 协议：TCP
   - 目标端口：`80`
   - 点击 **添加**

---

## 五、连接服务器 + 上传代码

### 5.1 SSH 连接

```bash
# Mac/Linux 终端
chmod 400 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<公网IP>

# Windows 用 PuTTY 或 PowerShell
# 需先用 PuTTYgen 把 .key 转成 .ppk
```

### 5.2 上传项目代码

在你**本地电脑**（项目所在机器）执行：

```bash
# 方式A：scp 直接上传（推荐）
scp -i ~/Downloads/ssh-key-*.key -r ./stock_model ubuntu@<公网IP>:~/

# 方式B：先 push 到 GitHub，再在服务器上 clone
# （在服务器上）
git clone <你的GitHub仓库地址> ~/stock_model
```

### 5.3 一键部署

在**服务器上**执行：

```bash
cd ~/stock_model
bash deploy/deploy_oracle.sh
```

脚本会自动完成：
- ✅ 安装 Python + Nginx
- ✅ 创建虚拟环境 + 装依赖
- ✅ 配置开机自启服务（崩溃自动重启）
- ✅ Nginx 反向代理（80 端口，免输端口号）
- ✅ 开放防火墙

---

## 六、手机访问

部署完成后：

```
📱 手机浏览器打开：http://<公网IP>
```

- 4G / WiFi 都能用
- 加到桌面书签 = 像原生 App 一样用
- 全屏，无地址栏

### iPhone 加桌面
1. Safari 打开 `http://<公网IP>`
2. 底部分享按钮 → **添加到主屏幕**
3. 桌面多一个图标，点开全屏

### Android 加桌面
1. Chrome 打开 `http://<公网IP>`
2. 菜单 → **添加到主屏幕**

---

## 七、日常管理

| 操作 | 命令 |
|---|---|
| 查看服务状态 | `sudo systemctl status stock_model` |
| 查看实时日志 | `sudo journalctl -u stock_model -f` |
| 重启服务 | `sudo systemctl restart stock_model` |
| 停止服务 | `sudo systemctl stop stock_model` |
| 更新代码 | 上传新代码后 `sudo systemctl restart stock_model` |

---

## 八、每日自动扫描（可选）

让服务器每天 9:25 自动跑扫描 + 推送企业微信：

```bash
# 在服务器上
crontab -e
# 添加一行（每天 9:25 跑）：
25 9 * * 1-5 cd ~/stock_model && source venv/bin/activate && python run_daily.py >> logs/daily.log 2>&1
```

> 周一到周五 9:25 自动扫描 → 生成建议 → 推送企业微信群 → 存档历史。你开盘前看企业微信即可。

---

## 九、常见问题

### Q1: 手机打不开？
检查三层：
1. Oracle 安全组是否开了 80 端口（第四节）
2. 服务器防火墙：`sudo iptables -L -n` 看 80 是否 ACCEPT
3. 服务是否在跑：`sudo systemctl status stock_model`

### Q2: 访问很慢？
- 换区域：日本东京 / 韩国春川对国内 4G 最快
- 如果还是慢，可用 Cloudflare 免费 CDN 加速（需绑域名）

### Q3: Oracle 账号注册被拒？
- 换浏览器（Chrome 无痕模式）
- 信用卡换一张（部分国内 Visa 被拒，MasterCard 成功率高）
- 区域选新加坡/日本

### Q4: 免费额度会被回收吗？
Oracle 政策：**Always Free 实例只要在用就不会回收**。但如果实例闲置超过 7 天，可能被回收。解决方案：配置 crontab 每天跑一次扫描（第八节），保持活跃。

### Q5: PaddleOCR 在 ARM 上装不了？
ARM 架构下 PaddleOCR 安装较复杂。部署初期先跳过截图 OCR 功能，用 App 内表单手动录入。后期如需 OCR，可换 tesseract 或在线 OCR API。

---

## 十、费用说明

| 项 | 费用 |
|---|---|
| Oracle Cloud ARM 实例（4核24G） | **永久免费** |
| 公网 IP | **免费**（Always Free 含 2 个） |
| 流量 | 每月 10TB 免费（你用不到 1%） |
| 域名（可选） | 不买域名就用 IP 访问，免费 |

> **总费用：0 元/月**
