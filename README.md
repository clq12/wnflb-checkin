[README.md](https://github.com/user-attachments/files/30833138/README.md)
# 福利吧论坛自动签到

利用 GitHub Actions 在云端定时执行签到，**无需开电脑**，每天自动签到 + 晚间复查，签到失败时微信推送提醒。

## 工作原理

```
GitHub Actions 云服务器
  ├── 每天 09:00 → 自动签到（已签则跳过）
  └── 每天 22:00 → 复查签到状态（没签成功则补签）
         │
         └── 失败时推送微信（成功不打扰）
```

你的电脑全程不需要开机，所有操作都在 GitHub 的免费云服务器上完成。

## 文件结构

```
wnflb-checkin/
├── .github/workflows/
│   └── checkin.yml          # GitHub Actions 定时任务配置
├── checkin.py               # 签到核心脚本
├── requirements.txt         # Python 依赖
├── test_local.bat           # 本地测试工具（可选）
└── .gitignore
```

## 部署步骤

### 第一步：获取论坛 Cookie

1. 用浏览器打开 `https://www.wnflb2023.com` 并**登录**
2. 按 `F12` 打开开发者工具
3. 切换到 **Network（网络）** 标签
4. 按 `F5` 刷新页面
5. 在请求列表中点击最上面那条请求（如 `forum.php`）
6. 右侧面板选择 **Headers** 标签，向下滚动找到 **Request Headers**
7. 找到 `Cookie:` 那一行，复制 `Cookie:` 后面的**完整值**

> 也可以在 **Application** → **Cookies** → `wnflb2023.com` 中查看

Cookie 类似这样一长串：

```
X_CACHE_KEY=xxx; S5r8_2132_saltkey=xxx; S5r8_2132_auth=xxx; S5r8_2132_sid=xxx; ...
```

### 第二步：本地测试（推荐）

上传到 GitHub 之前，先在本地验证 Cookie 是否有效。

**安装 Python 依赖：**

```bash
pip install requests
```

**运行测试：**

Windows 用户直接双击 `test_local.bat`，粘贴 Cookie 后回车。

或者手动运行：

```bash
# Windows CMD
set FORUM_COOKIE=你的Cookie字符串
set CHECKIN_MODE=checkin
python checkin.py

# Linux / macOS
FORUM_COOKIE="你的Cookie字符串" CHECKIN_MODE=checkin python checkin.py
```

看到以下任一输出说明 Cookie 有效：

```
[OK] 今日已签到，无需重复操作        ← 今天已经签过了
[OK] 签到成功！                      ← 签到成功
```

如果提示 `Cookie 已过期`，重新登录论坛获取新 Cookie。

### 第三步：创建 GitHub 仓库并上传文件

1. 打开 [github.com](https://github.com)，注册/登录账号
2. 点击右上角 **`+`** → **New repository**
3. Repository name 填 `wnflb-checkin`
4. **务必选择 Private（私有仓库）**，因为 Cookie 是敏感信息
5. 点 **Create repository**

**上传文件（推荐用 Git 命令行）：**

```bash
# 进入项目文件夹
cd wnflb-checkin

# 初始化并提交
git init
git add .
git commit -m "福利吧自动签到"

# 关联远程仓库（替换成你的用户名）
git remote add origin https://github.com/你的用户名/wnflb-checkin.git
git branch -M main
git push -u origin main
```

> **网页上传方式**：点 **Add file** → **Upload files**，把 `checkin.py`、`requirements.txt`、`test_local.bat`、`.gitignore` 拖进去。然后点 **Add file** → **Create new file**，文件名输入 `.github/workflows/checkin.yml`，粘贴内容后保存。

### 第四步：配置 GitHub Secrets

Cookie 等敏感信息不能写在代码里，需要存储在 GitHub 的加密 Secrets 中。

1. 进入仓库页面 → **Settings** → **Secrets and variables** → **Actions**
2. 点 **New repository secret**，添加以下配置：

| Name | Value | 是否必填 |
|------|-------|----------|
| `FORUM_COOKIE` | 第一步复制的完整 Cookie 字符串 | **必填** |
| `PUSHPLUS_TOKEN` | PushPlus 的 token（见第六步） | 可选 |

`FORUM_COOKIE` 必填；`PUSHPLUS_TOKEN` 用于失败提醒，建议配置。

### 第五步：测试运行

1. 进入仓库 → **Actions** 标签
2. 左侧选择 **福利吧自动签到**
3. 点右侧 **Run workflow** → **Run workflow**
4. 等待约 1 分钟，点击运行记录查看日志
5. 看到 `[OK] 今日已签到` 或 `[OK] 签到成功` 即表示部署成功

### 第六步：配置失败提醒（可选）

配置后，**仅在签到失败时**推送微信提醒；签到成功或今日已签到不会打扰你。

**使用 PushPlus（推荐）：**

1. 浏览器访问 [www.pushplus.plus](http://www.pushplus.plus)
2. 微信扫码登录
3. 复制页面显示的 token
4. 回到 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
5. 点 **New repository secret**
   - **Name**：`PUSHPLUS_TOKEN`
   - **Value**：粘贴你的 token
6. 点 **Add secret**

配置完成后手动运行一次 workflow：若签到成功则不会推送（属正常）；可临时把 `FORUM_COOKIE` 改成错误值触发一次失败来验证推送。

## 定时任务说明

工作流文件 `.github/workflows/checkin.yml` 中配置了两个定时任务：

| cron 表达式 | UTC 时间 | 北京时间 | 动作 |
|-------------|----------|----------|------|
| `0 1 * * *` | 01:00 | 09:00 | 早起签到 |
| `0 14 * * *` | 14:00 | 22:00 | 晚间复查 |

- **早起签到**：检测签到状态，未签到则执行签到，已签到则跳过
- **晚间复查**：再次检测签到状态，如果没签成功则补签一次

> GitHub Actions 的定时任务可能有 5-15 分钟的延迟，不影响签到效果。

## 日常维护

### Cookie 过期了怎么办

Discuz 论坛的 Cookie 有效期一般为 7-30 天。收到"Cookie过期"的推送通知后：

1. 重新登录 `https://www.wnflb2023.com`
2. 按 F12 获取新 Cookie
3. GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
4. 点击 `FORUM_COOKIE` → **Update** → 粘贴新 Cookie → 保存

### 查看签到记录

仓库 → **Actions** 标签 → 点击任意一条运行记录 → 展开 **执行签到** 步骤查看详细日志。

### 手动触发签到

仓库 → **Actions** → **福利吧自动签到** → **Run workflow** → **Run workflow**。

### 修改签到时间

编辑 `.github/workflows/checkin.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 1 * * *'   # 修改这里的时间（UTC）
  - cron: '0 14 * * *'  # 北京时间 = UTC + 8
```

## 常见问题

**Q: 为什么 GitHub Actions 没有按时执行？**

GitHub Actions 的定时任务不保证准时，通常有 5-15 分钟延迟，高峰期可能更久。签到不需要精确到分钟，延迟不影响效果。

**Q: 私有仓库会收费吗？**

GitHub 私有仓库每月免费 2000 分钟 Actions 额度。签到脚本每次运行不到 1 分钟，每天 2 次，一个月约 60 分钟，完全够用。

**Q: 仓库可以设为 Public 吗？**

**不建议**。虽然 Cookie 存在 Secrets 中不会泄露，但设为 Private 更安全。如果你的 Cookie 不慎泄露，别人可以登录你的论坛账号。

**Q: 脚本运行失败怎么办？**

查看 Actions 运行日志，常见原因：
- `Cookie 已过期` → 按上文更新 Cookie
- `无法提取 formhash` → 论坛页面结构可能改版，需要更新脚本
- `网络请求失败` → GitHub 服务器临时网络问题，一般下次自动恢复

## 技术细节

- **签到机制**：论坛使用 `fx_checkin` 自定义签到插件，签到 API 为 `plugin.php?id=fx_checkin:checkin&formhash=xxx`
- **登录检测**：通过页面中的 `fx_checkin` 签到按钮、退出链接等标志判断登录状态
- **签到状态检测**：页面中 `fx_chk_menu = true` 表示已签到，`false` 表示未签到
- **Cookie 处理**：使用 `requests.Session` 的 `cookies` 属性设置 Cookie，支持服务器返回的新 Cookie 自动更新
- **编码处理**：论坛页面使用 GBK 编码，脚本自动检测并解码
