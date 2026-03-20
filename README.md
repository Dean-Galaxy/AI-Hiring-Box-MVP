# 自动招聘外卖员（AI Hiring Box MVP）

基于 `Playwright + Python + LLM` 的本地自动化招聘系统 MVP。  
目标：在 Boss 端自动筛选候选人、发起沟通、处理回复并提取联系方式（手机号/微信/QQ），再推送到外部表格或 webhook。

## 功能概览

- 自动浏览候选人推荐页，按规则筛选并打招呼
- 自动轮询未读会话，提取最近上下文并调用 LLM 回复
- 正则检测手机号/微信号/QQ 号，命中后标记 `converted`
- 可将线索通过 webhook 推送到飞书/腾讯文档或测试接口
- 本地持久化候选人状态，避免重复触达

## 项目结构

```text
.
├── config/
│   ├── contacted_list.json
│   ├── station_kb.txt
│   ├── state.json               # 可选导出登录态（调试用）
│   └── user_data/               # 持久化浏览器用户目录（主流程复用）
├── core/
│   ├── browser_manager.py
│   ├── hunter.py
│   ├── farmer.py
│   ├── llm_service.py
│   └── extractor.py
├── scripts/
│   └── manual_login.py
├── logs/
├── main.py
├── run_main.bat
├── requirements.txt
└── .env.example
```

## 环境要求

- Python 3.10+
- Windows（目标部署）或 macOS（开发调试）
- 可访问 LLM API（DeepSeek/Qwen OpenAI 兼容接口）

## 快速开始

1) 创建虚拟环境并安装依赖

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

2) 配置环境变量

```bash
cp .env.example .env                # Windows: copy .env.example .env
```

编辑 `.env`：

- `OPENAI_API_KEY`：你的 API Key
- `LLM_BASE_URL`：如 `https://api.deepseek.com`
- `LLM_MODEL`：如 `deepseek-chat`
- `FEISHU_WEBHOOK_URL`：线索推送地址（可为空，空则只本地标记）
- `FEISHU_WEBHOOK_TOKEN`：可选，给 webhook 增加鉴权请求头 `X-Webhook-Token`
- `BOSS_LOGIN_URL` / `BOSS_RECOMMEND_URL` / `BOSS_INBOX_URL`：站点 URL（默认已给）
  - 推荐（骑手招聘账号）：`BOSS_RECOMMEND_URL=https://www.zhipin.com/web/chat/recommend`
  - 沟通（聊天列表）：`BOSS_INBOX_URL=https://www.zhipin.com/web/chat/index`
- `HEADLESS`：`false`（建议）
- `BROWSER_CHANNEL`：浏览器渠道，默认 `chrome`（推荐，避免使用 testing 浏览器）
- `BROWSER_EXECUTABLE_PATH`：可选，手动指定浏览器可执行文件路径；若配置则优先于 `BROWSER_CHANNEL`
- `BROWSER_USER_AGENT`：可选，自定义 UA；留空则使用浏览器真实 UA（更稳）
- `BROWSER_USE_NATIVE_WINDOW`：默认 `true`，使用系统原生窗口尺寸（避免固定 viewport 指纹）
- `BROWSER_IGNORE_ENABLE_AUTOMATION`：默认 `true`，移除 `--enable-automation` 启动参数
- `BROWSER_LOCALE`：默认 `zh-CN`
- `BROWSER_ACCEPT_LANGUAGE`：默认 `zh-CN,zh;q=0.9,en;q=0.8`
- `BROWSER_TIMEZONE_ID`：默认 `Asia/Shanghai`
- `BROWSER_USE_CDP`：默认 `false`，设为 `true` 后改为“手工启动 Chrome + Playwright 接管”
- `BROWSER_CDP_ENDPOINT`：默认 `http://127.0.0.1:9222`
- `HUNT_BATCH_SIZE`：每轮打招呼人数，默认 `3`（每 3 人切一次沟通）
- `FARM_ROUNDS_PER_BATCH`：每轮穿插沟通处理未读次数，默认 `8`
- `HUNT_WINDOW_MINUTES`：hunting 阶段时长（分钟），默认 `10`
- `HUNT_MAX_GREETINGS`：hunting 阶段最多打招呼人数，默认 `20`
- `HUNT_DAILY_MAX_GREETINGS`：每日打招呼总上限（跨循环累计），默认 `60`
- `PROACTIVE_FIRST_MESSAGE_ENABLED`：是否启用主动首句，默认 `false`
- `PROACTIVE_FIRST_MESSAGE_TEMPLATE`：主动首句模板（启用后生效）
- `API_AUTH_TOKEN`：本地 API 鉴权令牌（建议必填，OpenClaw 调用时使用 Bearer Token）
- `LOCAL_API_HOST`：本地 API 监听地址，默认 `0.0.0.0`
- `LOCAL_API_PORT`：本地 API 监听端口，默认 `8787`

3) 先执行扫码登录（保存会话）

```bash
python3 -m scripts.manual_login
```

登录成功后会写入 `config/user_data/`，后续主流程默认复用该目录下的登录态。  
`config/state.json` 作为可选导出文件保留（便于调试/迁移），但不是主流程复用的必要条件。

4) 启动主流程

```bash
python3 main.py
```

5) （可选）启动本地 API（给 OpenClaw 远程调用）

```bash
uvicorn api_server:app --host ${LOCAL_API_HOST:-0.0.0.0} --port ${LOCAL_API_PORT:-8787}
```

Windows PowerShell：

```powershell
uvicorn api_server:app --host 0.0.0.0 --port 8787
```

## 运行逻辑（Orchestrator）

`main.py` 会循环执行：

- Hunting 与 Farming 穿插执行：每轮先在推荐页打招呼（默认最多 3 人），再切到沟通页处理未读
- 默认 hunting 窗口约 10 分钟或最多发送 20 次问候；并受每日总上限控制（默认 60 次），结束后再补跑一小段 farming
- 可选主动首句：打招呼成功后可自动发送一条模板消息（由 `.env` 开关控制）
- 异常自动捕获并重启浏览器上下文，不会因单次超时直接退出

## 站点知识库（RAG）

编辑 `config/station_kb.txt`，填写你真实站点规则，例如：

- 单价/薪资结构
- 是否提供住宿
- 车辆租赁方案
- 出勤要求与区域范围

该文件内容会注入系统提示词，影响 LLM 回答策略。

## 线索提取与推送

- 手机号：匹配中国大陆 11 位号码
- 微信号：支持关键词前缀（微信/vx/wx）和常见账号格式
- QQ 号：支持关键词前缀（qq/扣扣/企鹅号）并自动清洗空格、短横线
- 命中后会：
  - 调用 webhook（若配置）
  - 更新 `config/contacted_list.json` 为 `status: converted`
  - 后续 unread 会跳过已 converted 候选人

## 日志与排障

- 日志文件：`logs/runner.log`
- 使用了滚动日志，防止长期运行占满硬盘
- 常见问题：
  - 未登录：先执行 `python3 -m scripts.manual_login`
  - 打开空白页/疑似风控：确认 `.env` 中 `BROWSER_CHANNEL=chrome`，并保持 `BROWSER_USER_AGENT` 为空；建议启用 `BROWSER_USE_NATIVE_WINDOW=true`、`BROWSER_IGNORE_ENABLE_AUTOMATION=true`
  - CDP 接管失败：确认手工 Chrome 已用 `--remote-debugging-port=9222` 启动，且 `BROWSER_CDP_ENDPOINT` 与端口一致
  - 无法调用 LLM：检查 `.env` 中 `OPENAI_API_KEY / LLM_BASE_URL / LLM_MODEL`
  - 无法推送：确认 `FEISHU_WEBHOOK_URL` 可用且网络可达，若配置了 `FEISHU_WEBHOOK_TOKEN`，需与服务端一致

## 手工登录后接管（CDP）SOP

适用场景：登录页容易空白/疑似风控，希望先人工登录再让脚本接管后续“找候选人 + 跟进消息”。

### Step 0：准备 `.env`

在 `.env` 中设置：

```bash
BROWSER_USE_CDP=true
BROWSER_CDP_ENDPOINT=http://127.0.0.1:9222
```

建议同时保留：

```bash
HEADLESS=false
BROWSER_USER_AGENT=
```

### Step 1：每次先手工启动 Chrome（带调试端口）

> 请先完全退出已有 Chrome 进程，再执行以下命令（避免端口和会话冲突）。

macOS：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir="$PWD/config/manual_chrome_profile"
```

Windows（PowerShell）：

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-address=127.0.0.1 `
  --remote-debugging-port=9222 `
  --user-data-dir="$PWD\config\manual_chrome_profile"
```

### Step 2：在这个 Chrome 里手工登录 Boss 并停留主页

手工打开并完成：

- 登录页：`BOSS_LOGIN_URL`
- 登录成功后跳到 Boss 已登录页面（建议停留在推荐页或聊天页）

### Step 3：保存登录态（可选但建议）

在项目目录运行：

```bash
python3 -m scripts.manual_login
```

CDP 模式下该脚本不会强制跳转登录页，而是检测当前页面登录态并保存 `config/state.json`。

### Step 4：启动主流程（接管后自动执行）

```bash
python3 main.py
```

### Step 5：验证“接管成功”的信号

以下信号同时满足基本可判定接管成功：

1. `main.py` 启动后，手工 Chrome 当前窗口能看到自动跳转到 `BOSS_RECOMMEND_URL` / `BOSS_INBOX_URL`
2. `logs/runner.log` 中出现 `hunting loop current sent=...` 或 `farming loop handled=...`
3. `config/contacted_list.json` 出现新增/更新记录

若失败，优先检查：

- 端口占用或未启动：`BROWSER_CDP_ENDPOINT` 不可达
- 连接了错误 Chrome 实例：没使用同一 `--user-data-dir`
- 你手工登录后又切换了未登录标签页
- 若终端提示“超时：5分钟内未检测到登录成功”，通常是页面结构变化导致单一 selector 失效；当前版本已使用“URL + DOM + Cookie”联合判定，可直接重试 `python3 -m scripts.manual_login`

## Windows 开机自启

- 启动脚本：`run_main.bat`
- 详细步骤见：`docs/windows_startup.md`
- 核心做法：将 `run_main.bat` 快捷方式放入 `shell:startup`

## OpenClaw 接入（API 模式）

适用场景：OpenClaw 部署在云端，但浏览器自动化仍在你本机执行。  
推荐架构：`OpenClaw(云端)` -> `本地 API` -> `main.py`

### 第 1 步：先在本地准备好登录态

```bash
python3 -m scripts.manual_login
```

### 第 2 步：配置 `.env` 的 API 参数

```bash
API_AUTH_TOKEN=请换成一个强随机字符串
LOCAL_API_HOST=0.0.0.0
LOCAL_API_PORT=8787
```

### 第 3 步：启动 API 服务

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8787
```

### 第 4 步：先本机验证 API

1. 健康检查（无需鉴权）：

```bash
curl http://127.0.0.1:8787/healthz
```

2. 启动主流程（需要 Bearer Token）：

```bash
curl -X POST http://127.0.0.1:8787/run/start \
  -H "Authorization: Bearer <API_AUTH_TOKEN>"
```

3. 查看状态：

```bash
curl http://127.0.0.1:8787/run/status \
  -H "Authorization: Bearer <API_AUTH_TOKEN>"
```

4. 获取已转化线索（默认 `status=converted`）：

```bash
curl "http://127.0.0.1:8787/leads?status=converted&limit=100" \
  -H "Authorization: Bearer <API_AUTH_TOKEN>"
```

5. 停止主流程：

```bash
curl -X POST http://127.0.0.1:8787/run/stop \
  -H "Authorization: Bearer <API_AUTH_TOKEN>"
```

### 第 5 步：让 OpenClaw 调用本地 API

云端不能直接访问 `127.0.0.1`，需要把本地 API 暴露为一个公网 HTTPS 地址（例如内网穿透）。  
拿到地址后，在 OpenClaw 中按“HTTP 工具 / API 工具”配置：

- Base URL：`https://你的公网域名`
- Header：`Authorization: Bearer <API_AUTH_TOKEN>`
- 动作 1（启动）：`POST /run/start`
- 动作 2（查状态）：`GET /run/status`
- 动作 3（拉线索）：`GET /leads?status=converted&limit=100`
- 动作 4（停止）：`POST /run/stop`

### 推荐工作流（新手版）

1. OpenClaw 触发 `POST /run/start`
2. 每 1-2 分钟轮询 `GET /run/status`
3. 若 `running=true`，继续轮询；若异常，告警你人工处理
4. 每 5 分钟调用 `GET /leads?status=converted` 拉取线索
5. 下班或维护时调用 `POST /run/stop`

## GitHub 部署（仓库发布）说明

该项目的 GitHub 部署目标是：**代码托管 + 自动检查**。  
由于需要本地扫码登录并复用 `config/state.json`，不建议直接在 GitHub 云端运行主流程。

已内置配置：

- `.gitignore`：自动忽略 `.env`、`venv/`、`logs/`、`config/state.json`、`config/contacted_list.json`
- `.github/workflows/ci.yml`：在 push / PR 时自动执行 Python 依赖安装与语法检查
- 详细文档：`docs/github_deploy.md`

推荐发布步骤：

1. 初始化并提交代码（不要提交 `.env` 与运行态文件）
2. 推送到 GitHub 仓库
3. 在 GitHub 页面确认 Actions 的 `Python CI` 通过
4. 实际运行请在本地 Windows/Mac 设备执行（按“快速开始”与“Windows 开机自启”）

## 合规与风控提示

该项目仅用于自动化流程验证。请确保：

- 遵守目标平台服务协议和当地法律法规
- 严格控制频率、间隔和行为节奏，避免过度自动化
- 妥善保护候选人隐私数据与访问凭据

启动 OpenClaw 隧道（前台）
ssh -N -L 18789:127.0.0.1:18789 openclaw-tx
长期稳定版
autossh -M 0 -N -L 18789:127.0.0.1:18789 openclaw-tx
http://127.0.0.1:18789