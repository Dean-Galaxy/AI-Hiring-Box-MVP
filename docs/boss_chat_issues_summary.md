## 背景概述

- **业务场景**: Boss 直聘「沟通」页面自动化招聘外卖员，分为推荐页 `Hunter` 和沟通页 `Farmer` 两大模块。
- **目标**:
  - 在沟通页稳定识别「未读会话」并自动回复。
  - 在候选人提供联系方式（手机号/微信/QQ）或平台生成系统联系方式卡片时，**准确提取并入库**。
  - 在推荐页实现「打招呼 -> 继续沟通 -> 发送首句 -> 关闭弹窗」的稳定闭环。
- **当前问题集中在**:
  - `core/farmer.py`：未读会话命中、交换微信卡片点击与提取逻辑。
  - `core/hunter.py`：打完招呼后打开会话、发送首句的稳定性。

---

## 1. 交换微信卡片相关问题（Farmer）

### 1.1 实际页面 DOM 结构（带交换微信卡片的完整窗口）

候选人先发一句「您好，这是我的微信」，平台随后下发一个绿底 WeChat 卡片：

```md
<div class="chat-message-list is-to-top">
  <!-- 系统提示 -->
  <div class="message-item">
    <div class="message-time"><span class="time">昨天 09:52</span></div>
    <div class="item-system clearfix">
      <div class="text">
        <span>该牛人通过”优选额外曝光“邀请，若您对牛人感兴趣请及时回复</span>
      </div>
    </div>
  </div>

  <!-- 候选人文字气泡：说明这是微信 -->
  <div class="message-item">
    <div class="item-friend clearfix">
      <div class="text">
        <span>您好，这是我的微信</span>
      </div>
      <div class="figure">
        <div class="avatar-content">
          <img src="https://img.bosszhipin.com/boss/avatar/avatar_8.png" />
        </div>
      </div>
    </div>
  </div>

  <!-- 关键：交换微信确认卡片 -->
  <div class="message-item">
    <div>
      <div class="item-friend" geek-info="[object Object]">
        <div class="text reset-message-text">
          <div class="message-card-wrap green">
            <div class="message-card-top-wrap">
              <div class="message-card-top-icon-content">
                <span class="message-dialog-icon message-dialog-icon-weixin"></span>
              </div>
              <div class="message-card-top-content">
                <div class="message-card-top-title-wrap">
                  <h3 class="message-card-top-title message-card-top-text">
                    我想要和您交换微信，您是否同意
                  </h3>
                </div>
                <p class="dialog-exchange-content"></p>
              </div>
            </div>
            <div class="message-card-buttons">
              <span class="card-btn">拒绝</span>
              <span d-c="61031" class="card-btn">同意</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 头像区域 -->
      <div class="figure">
        <div class="avatar-content">
          <img src="https://img.bosszhipin.com/boss/avatar/avatar_8.png" />
        </div>
      </div>
    </div>
  </div>

  <!-- 我方后续手动回的一条首句 -->
  <div class="message-item">
    <div class="message-time"><span class="time">11:34</span></div>
    <div class="item-myself clearfix">
      <div class="text">
        <i class="status status-delivery" style="color: rgb(153, 153, 153);">送达</i>
        <span>您好，我是美团骑手招聘专员……可以加个微信详细聊聊吗？</span>
      </div>
    </div>
  </div>
</div>
```

### 1.2 预期行为

- 当检测到上述 **绿底交换微信卡片** 或顶部的 **蓝色提示条**：
  - 自动点击「同意」。
  - 等平台生成联系方式卡片（微信号 / 手机号），随后抽取号码并入库。
- 在开启 `FARMER_DEBUG_CURRENT_CHAT=true` 时，即便会话已读、仅在「全部」tab 下存在，也应该在当前已打开会话上尝试：
  - 点击「同意」。
  - 扫描聊天窗口内所有候选人气泡与系统卡片，做一次独立的联系方式提取。

### 1.3 当前观测到的问题

1. **调试开关打开时无反应**
   - 现象：
     - `FARMER_DEBUG_CURRENT_CHAT=true` 时，用户手动切到包含交换微信卡片的会话。
     - 脚本无自动点击「同意」动作，也没有新线索写入外部表格。
   - 日志表现：
     - 多次出现：
       - `farmer debug fallback to right-panel-only`
       - `farmer debug current chat fallback candidate=当前会话(调试)`
     - 没有任何 `clicked wechat agree` 或 `lead extracted` 类日志。
   - 推断：
     - 调试模式生效了，但**没有识别到左侧列表中的“当前选中会话项”**，始终走「只看右侧气泡」的弱路径。
     - 现有选择器可能没有成功命中 `.message-card-wrap green` 中的「同意」按钮（例如作用域不对、节点不可见或者 Shadow/嵌套问题）。

2. **系统联系方式卡片未被统一解析**
   - Boss 直聘存在几类「卡片式」系统消息：
     - 电话卡片（可复制手机号）：
       - `.message-card-wrap.green` + `.message-dialog-icon-contact` + `h3.message-card-top-title` 包含 `手机号：<br>11位号码`。
     - 微信交换确认卡片（上文所示）。
     - 蓝色提示条（顶部提醒「我想要和您交换微信，您是否同意」）：
       - `.notice-list.notice-blue-list` 内部 `.text` 与 `.op a.btn / a:has-text('同意')`。
   - 当前 `Farmer` 的提取逻辑虽然已经开始扫描这些选择器，但从日志看：
     - 没有任何「lead extracted」「clicked wechat agree」的记录，说明在真实页面上仍然存在未命中情况。

---

## 2. 未读会话扫描与 tab 行为（Farmer）

### 2.1 Tabs DOM 结构

- 「新招呼」tab（带红点与计数）：
  - `.chat-label-item` + `.badge-dot.badge-dot-common` + 文本 `新招呼(15)`。
- 「沟通中」tab（带红点、无计数）：
  - `.chat-label-item.selected` + `.badge-dot.badge-dot-common` + 文本 `沟通中`。
- 「全部」tab 示例：

```md
<div title="全部" class="chat-label-item selected">
  <span class="badge">
    <span class="content">全部<!----></span>
    <!----> <!-- 有时这里不会渲染红点 -->
  </span>
</div>
```

### 2.2 当前实现（已修复状态）

- **多 tab 遍历策略**
  - Farming 现在会依次在三个 tab 中扫描未读：
    - 第一轮：`新招呼 -> 沟通中 -> 全部`，只看「红点/数字」未读。
    - 若仍无未读命中，再进行第二轮「历史兜底」：`全部 -> 沟通中 -> 新招呼`。
  - 每次 `switch_tab` 后会把左侧会话列表滚回顶部，避免从中间开始漏扫。

- **分页滚动 + 未读检测**
  - 在单个 tab 内，未读扫描采用「分页式滚动」：
    - 通过鼠标滚轮 / 列表容器滚动，最多向下翻若干页。
    - 每页上查找：
      - 带数字角标的 `.badge-count / [class*='badge-count']`。
      - 仅红点的 `.badge-dot / [class*='badge-dot'] / [class*='unread-dot']`。
    - 命中后才点击进入该会话。

- **去重与 converted 跳过**
  - 扫描过程中为每个会话构造 `candidate_key = candidate_id or name_normalized`：
    - 同一轮扫描内不会对同一个 key 重复进入。
    - 若 `contacted_list` 中该 key 已标记为 `status=converted`，会直接跳过。

### 2.3 历史上曾出现的问题（已作为背景保留）

> 这些是之前版本中观测到的问题，当前实现已经按上面的策略做了修复。保留在此，方便后来者理解为什么会有现在这套逻辑。

1. **只优先处理「新招呼」tab 的未读**（历史）
   - 早期版本只在「新招呼」tab 上识别未读，导致「沟通中」或「全部」中的未读长期不处理。

2. **列表不滚动导致漏扫下方未读**（历史）
   - 「全部」tab 中，下拉滚动条后才出现的红点不会被扫描到。

3. **历史兜底扫描会反复点击同一个候选人**（历史）
   - 之前 `_open_first_pending_by_history` 没有基于 `candidate_key` 做去重，也没有充分利用 `converted` 状态，导致：
     - 在历史兜底阶段，会多次命中同一个候选人（例如日志里反复出现 `李怀贞`）。
     - 已经有联系方式的候选人，仍可能重复被打开和上报。 

---

## 3. 推荐页打招呼与继续沟通问题（Hunter）

### 3.1 推荐卡片 DOM 结构

- 带「打招呼」按钮的卡片：
  - `.candidate-card, .geek-card, .card-item ...` 内包含：
    - `button.btn.btn-greet` 文案为 `打招呼`。
    - 推荐理由区域 `.recommend-reason .highlight-info` 文案含 `想当骑手意愿强`。
- 已有「继续沟通」按钮的卡片：
  - 同样 `candidate-card` 结构，但操作区包含：
    - `.btn-continue-wrap > button.btn.btn-continue.btn-outline` 文案为 `继续沟通`。

### 3.2 现有 `Hunter` 行为抽象

- 从代码与日志综合看，流程为：
  1. 在推荐页收集所有候选人卡片，优先「想当骑手意愿强」。
  2. 点击卡片上的 `打招呼` 按钮。
  3. 通过 `_open_chat_after_greet(card, candidate_name=...)`：
     - 优先在 **该 card 作用域** 内寻找 `继续沟通 / 已沟通 / 沟通` 按钮。
     - 若失败，再走全局 fallback：
       - `global_continue = page.locator("button:has-text('继续沟通'), ...")`。
  4. 聊天弹窗打开后，根据配置：
     - 按模板发送首句；
     - 关闭弹窗。

### 3.3 当前观测问题

1. **只会点「打招呼」，不会稳定点「继续沟通」**
   - 日志中多次出现：
     - `hunter failed to open chat after greet candidate_id=card-33`
     - `hunter proactive message failed candidate_id=card-35`
   - 同一时间段也有成功记录：
     - `hunter proactive message sent candidate_id=card-105`
     - `hunter round greeted=3 open_chat=3/3 rate=100.00%`
   - 说明：
     - `Hunter` 逻辑在部分页面/账号版本下可以正常工作，但在另一些情况下掉到 fallback 分支，导致：
       - 「打招呼」按钮点了；
       - 「继续沟通」按钮没找到或没点成功；
       - 于是 `open_chat=0/1`，主动首句也就失败。

2. **Fallback 分支频繁触发**
   - 日志频繁出现：
     - `hunter fallback buttons=16`
     - 随后 `hunter proactive message failed candidate_id=fallback-0`。
   - Fallback 的特点：
     - 不是从 card 作用域推导聊天窗口，而是“全页面找打招呼按钮 + 全局再找继续沟通”。
     - 天生容易受到 DOM 改版 / 悬浮弹层干扰。

3. **`TargetClosedError` 反复出现**

```text
playwright._impl._errors.TargetClosedError: Target page, context or browser has been closed
```

- 表明在某些时刻：
  - 推荐页或弹出的聊天窗口在脚本操作中被关闭 / 切换，导致后续点击或输入失败。
  - 对「打招呼 -> 继续沟通」链路的稳定性产生额外噪音。

---

## 4. 线索入库与重复提交问题

### 4.1 飞书表格重复记录

- 截图中可见同一候选人多行相同手机号，例如：
  - 多条 `candidate_name=李怀贞, contact=13814464626`。
- 触发场景：
  - Farming 阶段多次命中「同一候选人的相同会话」，尤其是在：
    - 历史兜底 `_open_first_pending_by_history` 中反复点击同一个 `thread`。
    - `converted` 状态校验仅基于 `candidate_id`，当 `candidate_id` 缺失或不稳定时，去重失效。

### 4.2 期望规则

- 对同一候选人的同一联系方式，应保证：
  - 在一定时间窗口内（例如进程存活期间 / 当天）**只入库一次**。
  - 已经标记为 `status=converted` 的候选人：
    - Farming 不再作为“需要回复/提取”的目标。
    - 愿意的话可继续对话，但不再触发 webhook / 新 lead 写入。

---

## 5. 建议后续 AI 讨论/设计的技术方案方向

> 以下不是具体实现，而是为其他 AI 设计方案时准备的讨论要点。

1. **可观测性优先**
   - 在 `Hunter` 和 `Farmer` 中增加更详细的日志字段：
     - 选择器命中数量（例如：`wechat_cards_found=n`, `blue_notices_found=n`）。
     - 每次尝试点击的 CSS 选择器及是否 `is_visible()`。
     - 当前 tab 名称 / 是否有红点 / 当前滚动页索引。

2. **DOM 兼容层**
   - 基于当前已收集的 HTML 片段，将关键组件抽象为：
     - 左侧会话列表 item。
     - 顶部 tab 标签（新招呼/沟通中/全部）。
     - 聊天气泡（系统/我方/候选人）。
     - 系统卡片（职位卡、电话卡、交换微信卡片、蓝色提示条）。
   - 为每类组件设计一组“主选择器 + fallback 选择器”，并在日志中打出实际命中的路径。

3. **更鲁棒的未读扫描策略**
   - 每个 tab 中：
     - 从顶部开始，按页滚动列表，记录每页扫描过的会话 key（`candidate_id` + `name`）。
     - 对每个有红点或数字角标的会话只处理一次。
   - 保证「全部」tab 下方的未读也能被覆盖。

4. **强绑定的推荐卡片 -> 聊天窗口映射**
   - 对 `Hunter`：
     - 在点击 `打招呼` 前，从 card 中读取 `data-geekid` 与候选人姓名。
     - 打完招呼后，只在该 card 作用域内寻找 `继续沟通` / `已沟通`。
     - 聊天弹窗打开后，通过标题区域 `chatview-name` 再次校验姓名匹配（已部分实现）。

5. **线索去重与幂等**
   - 在本地 `contacted_list` 中：
     - 以 `candidate_key = candidate_id or name_normalized` 作为主键。
     - 存储 `lead` 列表或最后一次 `lead`，并增加本地内存级别的“当轮去重缓存”。
   - 在 webhook 调用前，先查询本地状态，避免重复 push。

---

## 6. 供其他 AI 快速上手的关键文件与入口

- `core/hunter.py`
  - 推荐页逻辑，负责「打招呼 -> 继续沟通 -> 首句」。
  - 关键函数：
    - `greet_candidates`
    - `_open_chat_after_greet`
    - `_send_proactive_once_then_close`
- `core/farmer.py`
  - 沟通页逻辑，负责「未读扫描 -> 自动回复 -> 联系方式提取」。
  - 关键函数：
    - `process_unread`
    - `process_once`
    - `_open_top_unread` / `_open_first_pending_by_history`
    - `_extract_lead_from_chat`
    - `_accept_exchange_wechat`
- `core/extractor.py`
  - 纯文本线索提取（手机号/微信/QQ 正则），需要结合上面的 DOM 提取拼接使用。
- `logs/runner.log`
  - 所有关键行为的日志出口，当前已包含：
    - `hunter scan cards=...`
    - `hunter fallback buttons=...`
    - `hunter proactive message sent/failed ...`
    - `farmer switched tab=...`
    - `farmer picked unread thread tab=...`
    - 以及近期新增的 `farmer debug ...` 等调试日志。

