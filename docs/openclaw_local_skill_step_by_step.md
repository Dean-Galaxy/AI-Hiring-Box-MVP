# OpenClaw 本地 Skill 调用教程（新手版）

本文目标：让你在 **OpenClaw 与本项目同机部署** 的情况下，直接通过 Skill 本地启动和管理自动招聘流程，**不走 API 控制**。

---

## 0. 你会用到的文件

- Skill 描述文件：`openclaw_skills/local-auto-hiring/SKILL.md`
- 本地控制脚本：`scripts/local_runner_ctl.py`
- 一键安装脚本：`scripts/install_recruitment_setup.py`
- 一键准备脚本：`scripts/prepare_recruitment.py`
- 项目配置文件：`.env`
- 主日志：`logs/runner.log`

---

## 1. 第一次准备（只做一次）

### Step 1：一句话安装依赖和基础配置（推荐）

你对 OpenClaw 说：`安装招聘所需配置`

它会自动执行：

- 创建 `venv`
- 安装 `requirements.txt`
- 安装 `playwright chromium`
- 若不存在则创建 `.env`

成功标志：返回 `ready setup_installed`

### Step 2：补齐 `.env` 的关键项

打开 `.env`，至少填写这 3 项（安装脚本不会自动填密钥）：

- `OPENAI_API_KEY=你的密钥`
- `LLM_BASE_URL=你的模型网关地址`
- `LLM_MODEL=你的模型名`

新手建议：

- `HEADLESS=false`（先看得见浏览器，方便排查）
- `HUNT_BATCH_SIZE=2`（先小流量试跑）

### Step 3：扫码登录 Boss（首次必做）

```bash
source venv/bin/activate
python3 -m scripts.manual_login
```

看到“登录成功，已保存 state.json”后再继续。

---

## 2. 把 Skill 加到 OpenClaw

> 不同版本 OpenClaw 的 Skill 导入入口名字可能略有不同（例如 Skills / Tools / Playbooks）。

### Step 1：打开 OpenClaw 的 Skill 管理页

- 找到 “Skills” 或 “创建 Skill / 导入 Skill” 入口。

### Step 2：新建 Skill 并粘贴内容

- 读取并复制 `openclaw_skills/local-auto-hiring/SKILL.md` 全文。
- 在 OpenClaw 里新建 Skill，粘贴并保存。

### Step 3：确认 Skill 可见

- 在 OpenClaw 对话里能看到 `local-auto-hiring`（或你保存时的名称）即成功。

---

## 3. 日常如何调用（最常用）

建议每次都按这个顺序：

### Step 1：你只说一句“查看状态”

你对 OpenClaw 说：`查看状态` 或 `现在在跑吗`

返回：
- `running pid=xxxx`：说明已经在跑
- `stopped`：说明没在跑

### Step 2：先说“准备招聘”（一键拉起可接管 Chrome）

你对 OpenClaw 说：`准备招聘`

返回 `ready cdp=127.0.0.1:9222 ...` 说明浏览器已就绪。

### Step 3：如果没跑，你再说“开始招聘”

你对 OpenClaw 说：`开始招聘` 或 `启动招聘`

启动成功会返回：`started pid=xxxx`

### Step 4：查看运行日志（可选但推荐）

```bash
tail -f logs/runner.log
```

看到 `hunting loop` / `farming loop` 相关日志，说明流程正常推进。

### Step 5：需要停止时，你只说“停止招聘”

你对 OpenClaw 说：`停止招聘`

然后再说一次：`查看状态`

最后应看到 `stopped`。

---

## 4. 你可以直接对 OpenClaw 说的话（示例）

- “安装招聘所需配置。”
- “查看状态。”
- “准备招聘。”
- “开始招聘。”
- “停止招聘。”
- “先准备招聘，再开始招聘，并告诉我是否成功。”
- “读取最近 80 行日志，帮我看看有没有报错。”

也可以更口语化（同样可触发）：

- “把招聘环境先装好。”
- “准备开始招聘，先把浏览器打开。”
- “开始招聘。”
- “现在招聘程序在跑吗？”
- “停止招聘，今天先不跑了。”

---

## 5. 常见问题（新手必看）

### Q1：`start_timeout_pid_not_ready`

处理顺序：

1. 看 `logs/main.stderr.log`
2. 看 `logs/runner.log`
3. 确认 `.env` 的 `OPENAI_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 已填
4. 重新执行一次扫码登录：`python3 -m scripts.manual_login`

### Q2：提示 `setup_failed`

这表示安装脚本某一步失败。优先处理：

1. 让 OpenClaw 返回完整错误摘要（通常会带 step 命令和退出码）
2. 检查 Python 版本是否 >= 3.10
3. 检查网络是否能访问 pip 源（安装依赖和 playwright 需要联网）

### Q3：提示 `cdp_not_ready`

这表示调试端口没准备好。优先处理：

1. 让 OpenClaw 先执行一次“准备招聘”
2. 若仍失败，检查本机 Chrome 是否被系统权限拦截
3. 必要时在 `.env` 中配置 `BROWSER_EXECUTABLE_PATH` 为 Chrome 的绝对路径

### Q4：提示已经在运行，无法重复启动

这是正常保护机制，避免重复实例。  
先 `查看状态`，确认在运行就不要重复 `开始招聘`。

### Q5：我不想用 API 控制

当前方案就是本地直控：

- 启动/停止/状态全部走 `scripts/local_runner_ctl.py`
- 不依赖 `api_server.py`

---

## 6. 推荐你的第一天操作清单

1. 先说 `安装招聘所需配置`，等待安装完成。
2. 填好 `.env` 关键参数并完成一次扫码登录。
3. 对 OpenClaw 说：`查看状态 -> 准备招聘 -> 开始招聘 -> 查看状态`。
4. 跑 10~20 分钟，观察 `runner.log`。
5. 结束后说 `停止招聘`，再次说 `查看状态` 确认。

---

## 7. 关键说明（避免误解）

- 你不需要输入 `python3 -m ...`。
- 你只需要说中文意图（例如“开始招聘”）。
- OpenClaw 会在后台自动执行本地命令，并把结果用人话告诉你。
