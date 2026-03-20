# 原始内容（保留）

Here is the complete Product Requirements Document (PRD) detailing the architecture, business logic, and execution strategy for the AI recruiting system.

# Product Requirements Document (PRD): AI Hiring Box for Delivery Stations

## Project Overview

The "AI Hiring Box" is a hardware-software integrated SaaS solution designed specifically for food delivery station managers (e.g., Meituan). The system operates as an autonomous, 24/7 virtual HR assistant. It uses a combination of Robotic Process Automation (RPA) and Large Language Models (LLMs) to actively source candidates on platforms like Boss Zhipin, conduct initial conversational screening, answer basic job-related questions, and extract candidate contact information (WeChat/Phone numbers) to generate high-quality recruiting leads.

The commercial model relies on a high-margin hardware buyout (a pre-configured mini-PC acting as the "box") coupled with an ongoing subscription/recharge model for AI conversation tokens.

## Core Requirements

* **Anti-Ban Resiliency:** The system must operate locally on a dedicated device (hardware box) using localized IP addresses and human-like interaction pacing to avoid triggering platform anti-bot mechanisms and account bans.
* **Zero-Friction User Experience:** End-users (station managers) lack technical expertise. The final product must be "plug-and-play," requiring only a QR code scan to log in and simple text inputs for configuration.
* **Cost Efficiency:** The underlying LLM must be highly cost-effective to maximize profit margins on token recharges.
* **Non-Intrusive Delivery:** Lead generation notifications must not spam the user. Data should be compiled silently into an easily accessible, centralized location.

## Core Features

* **Automated Target Hunting:** The system actively scrolls through candidate recommendation pages and automatically initiates conversations based on strict hardcoded filters (e.g., "Active Today/Just Now," Job Intent matches "Rider/Courier," Age 18-45).
* **Human-like Screening & Contact Extraction:** AI engages the candidate with an initial screening question (e.g., "Do you have your own e-bike?") to lower defenses, before pivoting to request a phone number or WeChat ID.
* **Station Knowledge Base (RAG):** Managers can input custom station policies (e.g., piece-rate pay, vehicle rental options, accommodation). The AI references this knowledge base to answer complex candidate questions naturally before steering the conversation back to requesting contact info.
* **Automated Lead Harvesting:** The system uses regular expressions (Regex) to instantly detect phone numbers or WeChat IDs in the candidate's replies, tags the candidate as "converted," and stops further AI messaging to prevent robotic looping.

## Core Components

* **The Hardware Node (Execution Engine):** A low-cost, low-spec Windows mini-PC (e.g., Intel N100 processor). Acts as the physical host for the RPA scripts and browser instance.
* **The RPA Controller:** The automation layer responsible for DOM parsing, simulating human mouse movements/clicks, managing browser cookies, and reading/sending messages.
* **The LLM Brain:** The cloud-based AI model that analyzes candidate text, queries the knowledge base, and generates contextual, goal-oriented responses.
* **Data Delivery Pipeline:** A lightweight integration that pushes converted leads directly into an external spreadsheet without requiring a custom frontend dashboard.

## App/User Flow

### Manager (User) Flow

1. **Setup (Demo Phase):** Manager joins a video call, scans a QR code displayed on the developer's screen via the Boss Zhipin mobile app to grant login access.
2. **Configuration:** Manager provides a brief text summary of station benefits, rules, and salary structure (Knowledge Base).
3. **Daily Operation:** Manager checks a designated Feishu/Tencent online spreadsheet at their convenience to view the daily harvested leads (Name, Phone/WeChat, E-bike status) and adds them manually to their contact list.

### System (Bot) Flow

1. **Hunting Loop:**
* Launch browser and inject authentication cookies.
* Navigate to candidate lists.
* Parse UI elements to filter by active status, age, and job intent.
* Simulate human clicks to open profiles and send the initial ice-breaker message.
* Pause/Sleep randomly to mimic human pacing.


2. **Farming Loop:**
* Periodically check the message inbox for unread indicators (red dots).
* Read the candidate's reply.
* Send context + Knowledge Base to the LLM.
* Receive LLM response and type it out into the chat.
* Run Regex scan on the candidate's text. If a number/ID is found -> trigger Webhook to spreadsheet -> tag as "Done" -> exit chat.



## Techstack

* **Primary Language:** Python (for both RPA and backend logic).
* **RPA/Automation:** Playwright (Superior to Selenium for evading anti-bot detection; handles asynchronous tasks efficiently).
* **Backend Framework:** FastAPI (Lightweight, fast, and handles concurrent API calls smoothly).
* **LLM Provider:** DeepSeek API or Qwen (Alibaba) API. (Chosen for exceptional Chinese language comprehension, instruction following, and ultra-low token costs).
* **Data Storage/Sync:** Feishu (Lark) Open API or Tencent Docs Webhook (Direct-to-spreadsheet integration, eliminating the need for a custom database and frontend in the early stages).
* **Hardware (Target Commercial):** Sub-$150 USD Windows Mini PCs (e.g., Intel N100).

## Implementation Plan

### Phase 1: MVP & Core Loop Verification (Weeks 1-2)

* Set up the Playwright environment locally.
* Implement the manual QR code login bypass and cookie extraction.
* Build the *Hunting Loop* (Hardcoded DOM parsing and automated initial messaging).
* *Milestone:* System can successfully log in and send 20 targeted greeting messages without being flagged.

### Phase 2: LLM Integration & Data Extraction (Weeks 3-4)

* Integrate DeepSeek/Qwen API.
* Draft and test the System Prompts for screening and the RAG-based Knowledge Base implementation.
* Implement Regex for phone/WeChat detection.
* Connect the Webhook to push successful extractions to a Feishu/Tencent spreadsheet.
* *Milestone:* System can hold a conversation, answer a basic question, extract a provided number, and populate the spreadsheet.

### Phase 3: Hardware Packaging & Commercialization (Weeks 5+)

* Procure test hardware (Mini PCs).
* Configure Windows environments to auto-run the Python/FastAPI payload on boot.
* Develop a minimal local UI or configuration file system for managers to update their Knowledge Base text easily.
* *Milestone:* First "Smart Hiring Box" is shipped to a pilot station manager for real-world stress testing.

---

# 260317 更新内容（追加）

# PRD（260317更新版）：第7天自动二次问候

## 1. 背景与目标

在现有“自动打招呼 + 自动聊天 + 联系方式提取”基础上，新增一个稳定的二次触达闭环：  
对首次打招呼后 7 天内仍未拿到联系方式的候选人，于第7天北京时间10:00自动发送一次固定问候，提升触达覆盖与流程稳定性。

主验收指标：
- 二次问候发送成功率 >= 95%

## 2. 功能范围

### 2.1 In Scope（本期实现）
- 第7天自动二次问候（每天10:00统一执行）
- 二次问候文案全局可配置
- 每日发送上限（30条）与超量顺延
- 发送节流（3-8秒随机）
- 失败重试与次日补发（最多补发1天）
- 每天20:00飞书日报（每天都发，即使0失败）
- 手动重跑“当日任务”入口
- 功能总开关（上线默认开启）

### 2.2 Out of Scope（本期不做）
- 历史数据回溯纳入（仅上线后新数据生效）
- 人工排除名单
- 多告警渠道并行（V1仅飞书机器人）

## 3. 业务规则（已冻结）

### 3.1 候选人判定
- “未理我们”定义：未拿到有效联系方式
- 有效联系方式：手机号 / 微信号 / QQ / 其他任一都算
- 判定策略：偏召回（宁可误判为有联系方式，也不二次打扰）
- 即使候选人明确拒绝，第7天也照常发送一次

### 3.2 时间与调度
- 时区：`Asia/Shanghai`
- 计时方式：首次打招呼当天为第0天，按自然日计，第7天10:00发送
- 10:00任务每日只跑一次（不做当日多轮补扫）
- 若系统宕机错过窗口：恢复后补发，仍保证每人最多1次成功发送

### 3.3 次数与幂等
- 每位候选人最多1次二次问候成功发送
- 发送成功标准：点击发送成功且消息出现在聊天窗口

### 3.4 去重键
固定去重键使用以下5字段拼接（缺失字段用空字符串）：
- 昵称
- 首次打招呼日期
- 年龄
- 城市
- 期望岗位

## 4. 发送策略

- 每日上限：30条
- 排序优先级：
  1) 首次打招呼日期最早优先  
  2) 同日按进入队列时间先后
- 节流：每条间隔随机3-8秒
- 文案：全局配置（默认值采用已确认固定话术）

## 5. 失败与补发策略

- 单条发送失败：立即重试，最多2次
- 仍失败：次日10:00补发
- 补发上限：最多补发1天
- 超过补发窗口：终止并标记 `补发失败`

## 6. 告警与日报

- 渠道：飞书机器人
- 时间：每天20:00（北京时间）
- 频率：每天都发（失败数=0也发）
- 内容字段（固定）：
  - 日期
  - 当天补发失败总次数
  - 涉及候选人数
  - 失败原因Top3
  - 当天二次问候发送成功率

## 7. 指标与口径

- 主指标：二次问候发送成功率
- 口径：  
  `成功率 = 成功发送人数 /（计划发送人数 - 被总开关关闭或当天上限顺延人数）`
- 达标线：`>=95%`

## 8. 上线策略

- 发布方式：一次性全量上线
- 默认开关：上线即开启
- 手动兜底：提供“手动重跑当日任务”命令入口

## 9. 配置项（260317新增）

- `FOLLOWUP_ENABLED=true`
- `FOLLOWUP_TIMEZONE=Asia/Shanghai`
- `FOLLOWUP_FEATURE_START_DATE=YYYY-MM-DD`
- `FOLLOWUP_MESSAGE_TEMPLATE=...`
- `FOLLOWUP_DAILY_LIMIT=30`
- `FOLLOWUP_INTERVAL_MIN_SEC=3`
- `FOLLOWUP_INTERVAL_MAX_SEC=8`
- `FOLLOWUP_IMMEDIATE_RETRY=2`
- `FOLLOWUP_MAX_RETRY_DAYS=1`
- `FOLLOWUP_RUN_HOUR=10`
- `FOLLOWUP_RUN_MINUTE=0`
- `FOLLOWUP_REPORT_HOUR=20`
- `FOLLOWUP_REPORT_MINUTE=0`
- `FEISHU_BOT_WEBHOOK_URL=...`

## 10. 非功能要求

- 可追踪：每条候选人的状态变化可回溯
- 可恢复：任务中断后可继续推进
- 可运维：支持开关控制、手动重跑、日报验证
- 可扩展：后续支持按站点文案、多渠道告警、灰度规则