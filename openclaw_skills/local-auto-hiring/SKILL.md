---
name: local-auto-hiring
description: 本地启动并管理自动招聘项目（同机部署，不走 API）
version: 1.0.0
user-invocable: true
---

# 本地自动招聘技能（同机直控版）

这个 Skill 用于在 **OpenClaw 与本项目部署在同一台电脑** 时，直接通过本地命令控制项目，不经过 `api_server.py`。

## 适用场景

- OpenClaw 和项目代码在同一台机器
- 你希望直接 `start / status / stop` 主流程
- 你是新手，希望按固定步骤执行，不手敲复杂命令

## 运行前检查（每次执行前先做）

1. 当前目录必须是项目根目录（包含 `main.py`、`scripts/`、`.env`）。
2. `.env` 必须存在；不存在就从 `.env.example` 复制。
3. 首次建议先执行一次“安装招聘所需配置”（会自动安装依赖并生成 `.env`）。
4. 首次运行前必须先登录：`python3 -m scripts.manual_login`。

## 可修改设置（给新手的配置说明）

下面这些配置都在 `.env`，按需修改：

- `OPENAI_API_KEY`：LLM 密钥（必填）。
- `LLM_BASE_URL`：LLM 网关地址（例如 DeepSeek 或本地 OpenAI 兼容网关）。
- `LLM_MODEL`：模型名（例如 `deepseek-chat`）。
- `HEADLESS`：`false` 为可视化浏览器，`true` 为无头模式（新手建议 `false`）。
- `HUNT_BATCH_SIZE`：每轮打招呼人数（建议新手先 `2~3`）。
- `HUNT_MAX_GREETINGS`：单次 hunting 最多打招呼数（建议先 `10~20`）。
- `FOLLOWUP_ENABLED`：是否启用第 7 天二次触达（`true/false`）。
- `FOLLOWUP_MESSAGE_TEMPLATE`：二次触达文案。
- `FEISHU_WEBHOOK_URL`：线索推送地址（不用可留空）。

> 注意：这个 Skill 不使用 `API_AUTH_TOKEN`、`LOCAL_API_HOST`、`LOCAL_API_PORT`。

## 标准动作（OpenClaw 应按以下方式调用）

## 中文意图触发（核心要求）

当用户直接说中文时，OpenClaw 必须自动执行，不要求用户输入任何命令行。

触发映射：

- “安装招聘所需配置 / 安装招聘环境 / 初始化招聘环境” -> `python3 -m scripts.install_recruitment_setup`
- “准备招聘 / 准备开始招聘 / 打开招聘浏览器” -> `python3 -m scripts.prepare_recruitment`
- “开始招聘 / 启动招聘 / 开始招人” -> `python3 -m scripts.local_runner_ctl 开始招聘`
- “查看状态 / 招聘状态 / 现在在跑吗” -> `python3 -m scripts.local_runner_ctl 查看状态`
- “停止招聘 / 结束招聘 / 暂停招聘” -> `python3 -m scripts.local_runner_ctl 停止招聘`

严格约束：

1. 不要要求用户输入 `python3 ...` 命令。
2. 用户说“安装招聘所需配置”时，必须执行一键安装脚本，完成环境准备。
3. 用户说“准备招聘”时，必须先执行浏览器准备命令，确保 CDP 端口就绪。
4. 用户只说“开始招聘”，就直接执行对应命令。
5. 若检测到 CDP 端口未就绪，应先自动执行一次“准备招聘”再启动主流程。
6. 执行后只返回人话结果，例如“已开始招聘，进程号 12345”。
7. 仅在失败时附带简短排障建议（例如去看 `logs/runner.log`）。

> 控制脚本已支持中文别名，不要求用户输入 `start/status/stop` 英文参数。

### 1) 初始化环境（首次或新机器）

```bash
python3 -m scripts.install_recruitment_setup
```

### 2) 手工扫码登录（首次必做）

```bash
source venv/bin/activate
python3 -m scripts.manual_login
```

### 3) 启动主流程（后台）

```bash
source venv/bin/activate
python3 -m scripts.local_runner_ctl 开始招聘
```

> 推荐流程：先执行“准备招聘”，再执行“开始招聘”。

### 4) 查看运行状态

```bash
source venv/bin/activate
python3 -m scripts.local_runner_ctl 查看状态
```

### 5) 停止主流程

```bash
source venv/bin/activate
python3 -m scripts.local_runner_ctl 停止招聘
```

### 6) 查看日志（排障）

```bash
tail -f logs/runner.log
```

## 执行策略（给 OpenClaw 的行为约束）

1. 若 `查看状态` 返回 `running`，禁止重复 `开始招聘`。
2. 若 `开始招聘` 后 10 秒内不是 `running`，读取 `logs/runner.log` 给出错误摘要。
3. 若用户要求“停止”，先执行 `停止招聘`，再执行一次 `查看状态` 验证。
4. 遇到配置缺失（如 `OPENAI_API_KEY` 为空）时，先提示用户补 `.env`，不要盲目重试。
5. 用户聊天里出现“开始招聘/停止招聘/查看状态”时，优先按触发词处理，不再反问“要不要执行命令”。

## 常见问题提示

- `stopped`：说明主流程未运行，可直接 `开始招聘`。
- `start_timeout_pid_not_ready`：通常是环境依赖或登录态异常，先看 `logs/runner.log` 和 `logs/main.stderr.log`。
- 浏览器未登录：重新执行 `python3 -m scripts.manual_login`。
