# 自动招聘外卖员（AI Hiring Box MVP）

基于 `Playwright + Python + LLM` 的本地自动化招聘系统 MVP。  
目标：在 Boss 端自动筛选候选人、发起沟通、处理回复并提取联系方式（手机号/微信），再推送到外部表格或 webhook。

## 功能概览

- 自动浏览候选人推荐页，按规则筛选并打招呼
- 自动轮询未读会话，提取最近上下文并调用 LLM 回复
- 正则检测手机号/微信号，命中后标记 `converted`
- 可将线索通过 webhook 推送到飞书/腾讯文档或测试接口
- 本地持久化候选人状态，避免重复触达

## 项目结构

```text
.
├── config/
│   ├── contacted_list.json
│   ├── station_kb.txt
│   └── state.json               # 扫码登录后自动生成
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
- `BOSS_LOGIN_URL` / `BOSS_RECOMMEND_URL` / `BOSS_INBOX_URL`：站点 URL（默认已给）
- `HEADLESS`：`false`（建议）

3) 先执行扫码登录（保存会话）

```bash
python scripts/manual_login.py
```

登录成功后会生成 `config/state.json`，后续启动可复用登录态。

4) 启动主流程

```bash
python main.py
```

## 运行逻辑（Orchestrator）

`main.py` 会循环执行：

- Hunting：推荐页运行约 10 分钟或最多发送 20 次问候
- Farming：消息页运行约 5 分钟并处理未读
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
- 命中后会：
  - 调用 webhook（若配置）
  - 更新 `config/contacted_list.json` 为 `status: converted`
  - 后续 unread 会跳过已 converted 候选人

## 日志与排障

- 日志文件：`logs/runner.log`
- 使用了滚动日志，防止长期运行占满硬盘
- 常见问题：
  - 未登录：先执行 `python scripts/manual_login.py`
  - 无法调用 LLM：检查 `.env` 中 `OPENAI_API_KEY / LLM_BASE_URL / LLM_MODEL`
  - 无法推送：确认 `FEISHU_WEBHOOK_URL` 可用且网络可达

## Windows 开机自启

- 启动脚本：`run_main.bat`
- 详细步骤见：`docs/windows_startup.md`
- 核心做法：将 `run_main.bat` 快捷方式放入 `shell:startup`

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
