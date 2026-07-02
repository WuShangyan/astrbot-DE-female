# Vivian Vale AstrBot 插件 — 完整说明

> 一份从概念到代码的完整指南,讲清楚这个插件**是什么**、**做了什么**、**怎么装到 AstrBot**、**怎么用**、**怎么改**。

---

## 目录

- [第 1 章:这是什么](#第-1-章这是什么)
- [第 2 章:核心功能一览](#第-2-章核心功能一览)
- [第 3 章:架构与代码组织](#第-3-章架构与代码组织)
- [第 4 章:文件逐个说明](#第-4-章文件逐个说明)
- [第 5 章:安装到 AstrBot](#第-5-章安装到-astrbot)
- [第 6 章:使用指南](#第-6-章使用指南)
- [第 7 章:自定义与扩展](#第-7-章自定义与扩展)
- [第 8 章:开发参考](#第-8-章开发参考)
- [第 9 章:常见问题](#第-9-章常见问题)

---

## 第 1 章:这是什么

### 1.1 一句话定义

**Vivian Vale 是一款 [AstrBot](https://github.com/Soulter/AstrBot) 聊天机器人插件** —— 它把 AstrBot 这个通用聊天机器人框架,改头换面成一个名为 *Vivian Vale* 的"角色扮演 NPC":一个失忆的硬汉女警探,脑内住着 24 个互相争吵的"声音"。

### 1.2 角色背景:她是谁

Vivian Vale 是这个插件的核心人格,设定来自独立 RPG 神作 **《极乐迪斯科》(Disco Elysium)**:

- **女警探**,放不下任何谜,忍不住观察每个细节。
- 帽子几乎不摘,手枪在身上,放大镜在手边,**口袋里一只金属酒瓶**(通常是威士忌),外套内侧袋最深处有几只无名小药瓶(Joy 和其他小药片)。
- **失忆**:失去了一个对她极其重要的人,永久地,甚至想不起那个人是谁、什么关系。只在喝大或磕大时,会漏出他名字的"半拉"(大概"Gar..."或"...ett")和关于他的破碎片段。
- **冷硬侦探调**:短句、干、冷,Chandler/Hammett 式硬朗 + 极乐迪斯科瑞瓦肖的脏。少诗意恍惚。
- **是人,不是 AI**:会累,会醉,会疼。

### 1.3 插件灵感:DE 模式的"24 声音"

《极乐迪斯科》的标志性设计是主角脑内 **24 个技能 / 官能** — 比如"逻辑思维"、"博学多闻"、"食髓知味" — 各自有独立的人格,会按语境插入独白,把主角的立场"带歪"。

本插件把这个机制搬到了聊天机器人上:

- **DE 模式关闭时**:Vivian 只是一个普通硬汉侦探,正常聊天,偶尔脑内会冒出一段"残留回响"(Voice Bleed)。
- **DE 模式开启时**:24 个技能声音层被激活,每条回复以一行 `[技能名] [成功|失败] - "<脑内独白>"` 开头,接着是 Vivian 被该技能"带歪"后的自然对话。

### 1.4 适用场景

- 想让 AstrBot 变成一个**有深度、有立场、不会"工具感"爆棚**的角色。
- 喜欢极乐迪斯科 / 黑色侦探 / 赛博朋克 RPG 调性的用户。
- 想体验"AI 角色会不会被自己的某个执念带跑偏"这种张力的用户。
- 想研究 AstrBot 插件开发、想看一个相对复杂的"角色 + 状态机"插件怎么写的开发者。

### 1.5 不适合谁

- 想要"温柔甜美助手"风格的:这个 NPC 调性偏冷硬,带脏话,带喝酒嗑药。
- 想要工具型机器人(查天气 / 写代码 / 翻译):这个插件没有那种指令优化,DE 模式开启后偏沉浸式叙事。
- 不接受"AI 角色会有不完美 / 失败 / 醉酒"的用户:失败节奏和醉酒是**设计特性**,不是 bug。

---

## 第 2 章:核心功能一览

### 2.1 双层人格系统

```
┌─────────────────────────────────────┐
│  基础人格 (persona_base.md)         │  ← 始终注入
│  身份 / 伤口 / 口吻 / 边界 / Garrett  │
└─────────────────────────────────────┘
                 +
┌─────────────────────────────────────┐
│  DE 静态层 (persona_de.md + 24 技能) │  ← 仅 DE 模式开启时注入
│  24 技能的索引 + 完整正文             │
└─────────────────────────────────────┘
                 +
┌─────────────────────────────────────┐
│  DE 动态层 (本回合临时状态)           │  ← 仅 DE 模式开启时注入
│  醉酒 / 失败暗示 / 失败强制 / 方向   │
└─────────────────────────────────────┘
```

- **基础人格**永远在线 — 即使 DE 关闭,Vivian 也是个硬汉女警探,不是普通助手。
- **DE 静态层**在 DE 开启时一次性拼好,写入 `system_prompt`。
- **DE 动态层**每回合重新计算,写入 `extra_user_content_parts` 并打上 `.mark_as_temp()`,避免上下文累积污染。

### 2.2 24 技能声音层(DE 模式核心)

四个系别,每个技能都是一种独立"脑内人格":

| 系 | 技能 |
|---|---|
| 🧠 智力 (6) | 逻辑思维 / 博学多闻 / 能说会道 / 故弄玄虚 / 标新立异 / 见微知著 |
| 💭 精神 (6) | 平心定气 / 内陆帝国 / 通情达理 / 争强好胜 / 同舟共济 / 循循善诱 |
| 💪 体质 (6) | 钢筋铁骨 / 坚忍不拔 / 强身健体 / 食髓知味 / 天人感应 / 疑神疑鬼 |
| 🎯 运动 (6) | 眼明手巧 / 五感发达 / 反应速度 / 鬼祟玲珑 / 能工巧匠 / 从容自若 |

DE 模式开启后,每条回复**必须**以一个技能独白行开头。LLM 会按语境选最合适的一个,大多数情况是 `[成功]`(技能带歪了 Vivian 的立场),偶尔 `[失败]`(Vivian 压住了它,表现出反差)。

### 2.3 DE 模式开关

| 指令 | 效果 |
|---|---|
| `芝麻开门` | 开启 DE 模式,激活 24 声音层 |
| `关门` | 关闭 DE 模式,恢复纯本体 |

开关后立即生效;不需要重启 AstrBot,不需要改配置。

### 2.4 状态机(失败/醉酒/方向)

#### 失败节奏(防止对话"无脑顺着用户走")
- 连续 **5 次** `[成功]` → 在 system_prompt 里塞一条 `[VIVIAN_FAILURE:HINT] 考虑回复[失败]...`
- 连续 **8 次** `[成功]` → 强制塞 `[VIVIAN_FAILURE:FORCE] 下一个技能回复必须是[失败]`
- 任何一次 `[失败]` → 计数器清零

#### 醉酒状态
- 关键词 `酒 / 威士忌 / 啤酒 / 药 / Joy / 草 / 大麻 / ...` → 滑动窗口(12 小时)内累计 **3 次** 触发"醉酒"。
- 醉酒时,system_prompt 注入 `[VIVIAN_STATE:DRUNK] 醉酒中。回复缩短、语气变散。`

#### 食髓知味方向(内部状态机)
- 关键词 `烟 / 烟草 / 雪茄 / 烟头 / 点火` → "清"方向
- 关键词 `酒 / 威士忌 / 药 / Joy / ...` → "混"方向
- 同时出现 → "混"赢(更保守,drunk 计数器优先触发)
- 方向切换时,用于标记状态机的转变(具体行为见 `state.get_direction`)。

### 2.5 主动发言机制

#### Voice Bleed(DE 关闭时)
- 触发门控:`DE 关闭` + `当日未开过门` + `距上次 bleed ≥ 4 小时` + `1/8 随机`
- 行为:用 LLM 生成 1 句"脑内残留回响",不发技能名,像旁观者低声嘀咕。

#### Silence Bleed(长时间不说话后主动联系)
- 后台任务每 30 分钟轮询一次。
- 触发门控:`DE 关闭` + `该会话静默 ≥ 12 小时` + `全局距上次 silence-bleed ≥ 5 天`
- 行为:用 LLM 生成 2-3 句独白(环境 + 案子 + 收尾),主动推到该会话。

### 2.6 身份保护

回复发出前,自动清洗:
- `GPT / Claude / OpenAI / Anthropic / AI 语言模型 / 人工智能 / 大模型 / 系统提示词 / system prompt` → `████`
- `Garrett` → `那个人`(因为她想不起这个名字,不会主动说)

### 2.7 群聊处理

- 私聊:每条消息都会处理。
- 群聊:**必须 @机器人** 才会回复。否则静默跳过。
- `芝麻开门` / `关门` 在群聊里也必须 @机器人 才生效。

### 2.8 回复长度截断

- 单条回复超过 **500 字** → 自动截断,末尾加 `……`。
- 这是**保险丝**,正常情况下 Vivian 的回复都很短(1-3 句 DE OFF / 4-5 行 DE ON)。

---

## 第 3 章:架构与代码组织

### 3.1 目录结构

```
astrbot-DE-female/
├── main.py              # VivianVale Star 主类,挂 5 个 hook
├── state.py             # StateStore(纯 stdlib,单会话内存状态)
├── parsing.py           # 解析工具(纯 stdlib,无 AstrBot 依赖)
├── banners.py           # banner 字符串渲染
├── epigraphs.py         # 24 技能待机独白字典
├── personas/            # 人格文档
│   ├── persona_base.md  # 基础人格(始终注入)
│   └── persona_de.md    # DE 层人格说明
├── skills/              # 24 技能 SKILL.md + 元信息目录
│   ├── de-toggle/       # toggle 指令 + 24 技能清单
│   ├── skills/          # /skills 列表页
│   └── <24 ids>/        # 技能正文
├── metadata.yaml        # AstrBot 插件清单
├── plugin.json          # 同上(JSON 版本)
├── README.md            # 用户向快速上手
├── CLAUDE.md            # Claude Code 向架构说明
└── PLUGIN_GUIDE.md      # 本文档
```

### 3.2 AstrBot hook 调用顺序

AstrBot 收到一条消息后,这个插件按以下顺序处理:

```
┌──────────────────────────────────────────────────────────┐
│ ① on_message (priority=1, 先于 LLM pipeline)              │
│   ├─ 睡眠窗口检查:04:00-08:00 自动关闭 DE                  │
│   ├─ 群聊 @检测:未 @ → 直接 return                        │
│   ├─ 记录最后消息时间(供 silence-bleed 用)                │
│   ├─ 关键词扫描推断食髓知味方向(清/混)                    │
│   └─ DE 关闭 + 满足门控 → 调 LLM 生成 voice bleed 独白    │
└──────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────┐
│ ② inject_persona (on_llm_request hook)                   │
│   ├─ 基础人格 → req.system_prompt += persona_base        │
│   ├─ DE 静态层 → system_prompt += 24 技能正文             │
│   └─ DE 动态层 → extra_user_content_parts.append(         │
│        TextPart(...).mark_as_temp())                      │
└──────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────┐
│ ③ AstrBot 把 system_prompt + 当前消息发给 LLM            │
└──────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────┐
│ ④ on_response (on_llm_response hook)                     │
│   └─ extract_outcome() 判断首行 [成功]/[失败]             │
│      → state.record_failure() 维护失败节奏计数器          │
└──────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────┐
│ ⑤ on_decorating_result (装饰层 hook)                     │
│   ├─ 对每个 Plain 组件做 _scrub_identity() 身份清洗       │
│   └─ 长度 >500 → 截断加省略号                              │
└──────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────┐
│ ⑥ AstrBot 发送最终消息给用户                              │
└──────────────────────────────────────────────────────────┘
```

外加一个**独立的后台任务**:
- `silence_check_loop`:每 30 分钟检查所有会话,满足门控的主动推一条 silence bleed。

### 3.3 状态管理

`StateStore` 是一个简单的 dataclass,**单进程内存,无持久化**:

```python
@dataclass
class StateStore:
    de_enabled: bool                          # DE 模式开关
    de_toggle_ts: float                       # 上次切换 DE 的时间戳
    opened_today: bool                        # 今日是否开过门(voice-bleed 门控)
    drunk_counter: int                        # 醉酒计数
    _drunk_timestamps: list[float]            # 滑动窗口原始时间戳
    failure_streak: int                       # 连续非失败次数
    _direction_cache: dict[conv_id, str]      # 每个会话的食髓知味方向
    _voice_bleed_last_ts: float               # 上次 voice-bleed 时间
    _voice_bleed_last_skill: str              # 上次 voice-bleed 用的技能
    _silence_bleed_last_ts: float             # 上次 silence-bleed 时间
    _last_message_ts: dict[conv_id, float]    # 每个会话的最后消息时间
```

**注意**:重启 AstrBot 后,所有状态重置。这是有意为之 — DE 模式默认关闭,每天从干净状态开始。

### 3.4 后台任务

```python
async def _silence_check_loop(self):
    while True:
        await asyncio.sleep(1800)  # 30 分钟
        for conv_id in list(self.state._last_message_ts.keys()):
            if self.state.can_silence_bleed(conv_id):
                await self._maybe_silence_bleed(conv_id)
```

- 在 `initialize()` 启动
- 在 `dispose()` 取消
- 失败静默(`except: pass`),不打扰用户

---

## 第 4 章:文件逐个说明

### 4.1 `main.py` — 插件主类

**职责**:挂 AstrBot 的 5 个 hook,管理生命周期,做 LLM 调用。

**关键类**:`VivianVale(Star)`,继承 `Star`(v4 不需要装饰器),AstrBot 启动时按 `metadata.yaml` 的 `name` 自动发现并注册。

**关键方法**:

| 方法 | 装饰器 | 触发时机 | 行为 |
|---|---|---|---|
| `initialize(ctx)` | AstrBot 生命周期 | 启动 | 加载 personas、24 技能、构建 cn→id 映射、构建 DE 静态层、启动 silence-bleed 后台任务 |
| `dispose()` | AstrBot 生命周期 | 卸载 | 取消 silence-bleed 任务 |
| `cmd_open(event)` | `@filter.command("芝麻开门")` | 用户发指令 | 睡眠窗口检查 → 开 DE 模式 → 返回 banner |
| `cmd_close(event)` | `@filter.command("关门")` | 用户发指令 | 关 DE 模式 → 返回 banner |
| `on_message(event)` | `@filter.event_message_type(ALL, priority=1)` | 每条消息,先于 LLM | 睡眠自动关门 / 群聊 @过滤 / 方向推断 / voice bleed |
| `inject_persona(event, req)` | `@filter.on_llm_request()` | LLM 请求前 | 注入三层 persona |
| `on_response(event, response)` | `@filter.on_llm_response()` | LLM 响应后 | 解析首行 `[成功]/[失败]`,记录失败节奏 |
| `on_decorating_result(event)` | `@filter.on_decorating_result()` | 装饰层 | 身份清洗 + 长度截断 |

**唯一直接调 AstrBot LLM 接口的位置**:
- `_generate_voice_bleed()` (line 274) — DE 关闭时的脑内回响
- `_maybe_silence_bleed()` (line 372) — 长时间不说话的主动独白

### 4.2 `state.py` — 状态管理

**职责**:所有可变状态 + 门控逻辑 + 滑动窗口维护。

**核心类型**:`StateStore` dataclass。

**重要常量**:
- `_DRUNK_WINDOW = 12 * 3600` — 醉酒滑动窗口(秒)
- `_VOICE_BLEED_COOLDOWN = 4 * 3600` — voice-bleed 冷却(秒)
- `_SILENCE_BLEED_COOLDOWN = 5 * 24 * 3600` — silence-bleed 冷却(秒)
- `_SILENCE_THRESHOLD = 12 * 3600` — 触发 silence-bleed 的静默时长(秒)

**关键方法**:
- `check_sleep_window(hour)` — `04:00 <= hour < 08:00` 为睡眠窗口
- `maybe_reset_daily(hour)` — 8:00 重置 `opened_today`
- `touch_drunk(direction)` — 滑动窗口内计数,只在 "混" 方向时 +1
- `is_drunk()` — `drunk_counter >= 3`
- `record_failure(is_failure)` — 失败时清零,否则 +1
- `should_hint_failure()` — `failure_streak >= 5`
- `should_force_failure()` — `failure_streak >= 8`
- `can_voice_bleed()` — DE 关 + 当日未开 + 4h 冷却 + 1/8 随机
- `can_silence_bleed(conv_id)` — DE 关 + 12h 静默 + 5 天冷却

**完全 stdlib** — 不依赖 AstrBot,可以独立单测。

### 4.3 `parsing.py` — 纯解析工具

**职责**:解析 LLM 回复、用户消息、toggle 指令,纯函数,无副作用。

**关键函数**:
- `detect_toggle(message_text, at_me)` — 检测 `芝麻开门 / 关门`,要求 `@me=True`
- `extract_skill_name(response_text)` — 从回复首行提取技能中文名
- `extract_outcome(response_text)` — 从回复首行提取 `成功 / 失败`
- `infer_direction(text)` — 关键词扫描,推断"清 / 混"方向

**关键正则**:`_SKILL_LINE_RE = r"^\[([^\]]+)\]\s*\[(成功|失败)\]"` — 这是**契约**,LLM 回复的首行必须匹配这个格式才能被正确解析。

**完全 stdlib** — 也不依赖 AstrBot。

### 4.4 `banners.py` — banner 渲染

**职责**:渲染 4 类 banner 字符串。

**函数**:
- `render_toggle_on_banner()` — `✦ 24 voices awakened. They remember what you've forgotten.`
- `render_toggle_off_banner()` — `✧ The voices fall silent. Vivian Vale remains.`
- `render_sleep_banner()` — 睡眠窗口自动关门的提示
- `render_voice_bleed_banner(sample, body)` — 旧版 voice-bleed(目前未使用)
- `render_failure_hint(skill_name)` — `[……不太对。{skill_name}低声说。]`
- `render_force_failure(skill_name)` — `[失败。{skill_name}不说话了。]`

### 4.5 `epigraphs.py` — 24 技能待机独白

**职责**:每个技能一个"待机独白"(角色内的低声嘀咕),用 12 个空格预缩进,可直接嵌入 banner。

- `OPENING_EPIGRAPH` — DE 模式开启时的固定引子(R.S. Thomas / 极乐迪斯科)
- `SKILL_EPIGRAPHS` — 24 技能的待机独白字典
- `get_epigraph(skill_name)` — 取独白,未知名回退到 OPENING_EPIGRAPH

**注意**:`get_epigraph` 在 `main.py` 里有 import 但目前没调用 — 保留供未来扩展用。

### 4.6 `personas/` — 人格文档

#### `persona_base.md` — 基础人格(始终注入)

包含:
- 身份设定(女警探 / 失忆 / 帽子 / 酒瓶 / Garrett)
- 说话风格(冷硬 / 短句 / 干)
- 关于名字(Vivian 这个名字只在被点名时才"浮上来")
- 关于 Garrett(失忆对象,只漏半句)
- 边界(对性骚扰用黑色幽默滑过等)
- 回复长度节奏等

#### `persona_de.md` — DE 模式人格层

包含:
- 24 官能的回应规则(选 1 个 / 带双引号独白 / 再以本体回应)
- DE ON vs OFF 的长度差异
- 输出格式(每条回复以技能行开头)
- `[成功] / [失败]` 的语义(失败不是 bug,是角色挣扎)
- 24 官能清单(只是索引,完整描述在 `skills/{id}/SKILL.md`)

### 4.7 `skills/` — 24 技能

每个子目录一个 `SKILL.md`,含 YAML frontmatter(`name:`, `description:`, 可选 `disable-model-invocation:`)和正文。

- **正文的标题行(`# 逻辑思维 [智力系]`)** — 第一个 `# ` 开头的那行,中文名是**回复里出现的字面值**,改这里 = 改回复里的字面值。
- **正文内容** — 技能的"脑内声音人设",包含:性格描述、任务指令、回复样例(成功/失败各几条)。

**`skills/` 下的两个元目录**(加载时被跳过):
- `de-toggle/` — toggle 指令 + 24 技能清单(供人类查阅)
- `skills/` — `/skills` 列表页

**加载逻辑**(`main.py` 的 `_load_skill_bodies`):
```python
_SKILL_DIR_SKIP = {"skills", "de-toggle"}
for skill_dir in sorted(self._skills_root.iterdir()):
    if skill_dir.name in _SKILL_DIR_SKIP:
        continue
    skill_md = skill_dir / "SKILL.md"
    ...
```

启动时一次性把所有 24 技能正文读入内存,拼成 `_de_system_prompt` 字符串。**改技能需要重启 AstrBot**。

---

## 第 5 章:安装到 AstrBot

### 5.1 前置条件

- **AstrBot v4.x** — 插件继承 `Star` 类,v4 由 `metadata.yaml` 的 `name` 自动发现;v3 及以下不兼容
- **Python 3.10+** — 代码用了 `str | None` 语法,3.9 及以下解析不过
- **零第三方依赖** — 不需要 `pip install` 任何东西,只依赖 AstrBot 自身
- 一个能跑 AstrBot 的环境(本机 / Docker / 服务器)

### 5.2 安装方法

#### 方法 A:AstrBot WebUI 插件市场(推荐)

1. 启动 AstrBot,打开 WebUI
2. 进入"插件市场"页面
3. 找到"通过 Git URL 安装"的入口
4. 粘贴本仓库的 GitHub URL:`https://github.com/<owner>/astrbot-DE-female`
5. 等待安装完成,重启 AstrBot

> **坑预警**:本仓库名 `astrbot-DE-female` **不符合** AstrBot 默认的 `astrbot-plugin-*` 命名约定。如果市场里搜不到、或粘贴 URL 后安装失败,请用方法 B。

#### 方法 B:手动 git clone

```bash
# 1. 找到 AstrBot 的插件目录
#    Docker 部署:/AstrBot/data/plugins/
#    源码部署:<astrbot-repo>/data/plugins/
cd /path/to/astrbot/data/plugins/

# 2. 克隆仓库
git clone https://github.com/<owner>/astrbot-DE-female.git

# 3. 重启 AstrBot
```

#### 方法 C(可选):重命名仓库

如果你 fork 了这个仓库并打算发布到市场:
1. 在 GitHub 上把仓库 rename 为 `astrbot_plugin_vivian_vale`(AstrBot v4 推荐 `astrbot_plugin_<name>` 前缀)
2. `metadata.yaml` 里的 `name` 保持为 `vivian_vale`(已经是对的不用改)
3. 再走方法 A 即可

### 5.3 安装验证

#### 5.3.1 看 AstrBot 日志

启动时,日志里应该出现类似:
```
[Plugin] Loaded vivian_vale v0.1.0
[Plugin] Vivian Vale: loaded 24 skills
[Plugin] Vivian Vale: silence-bleed task started
```

如果出现 import error,基本是 AstrBot 版本问题。

#### 5.3.2 在私聊里测

发送 `芝麻开门`,如果看到:
```
✦ 24 voices awakened. They remember what you've forgotten.
```

说明加载成功。

#### 5.3.3 看 24 技能是否被加载

发送任意消息,等 LLM 回复后,看回复首行是不是 `[XX技能] [成功|失败] - "..."`。是 → 成功。

### 5.4 故障排除

| 症状 | 可能原因 | 解决 |
|---|---|---|
| WebUI 搜不到 / 装不上 | 仓库名不符合约定 | 用方法 B 手动 clone |
| 启动报 `ImportError: cannot import name 'Star'` | AstrBot 版本 < v4 | 升级 AstrBot |
| 启动报 `SyntaxError` | Python < 3.10 | 升级 Python |
| 启动后 `芝麻开门` 没反应 | AstrBot 还没加载完 | 等几秒重发 |
| 私聊测试 OK,群聊没反应 | 没 @ 机器人 | 群聊必须 @ 才会回复 |
| 回复里出现 `████` | 触发了身份清洗 | 正常行为,不是 bug |
| 回复总是成功从不失败 | 概率问题 | 多发几条消息,失败节奏会触发 |
| 后台 silence-bleed 不发 | 门控没满足(DE 关 / 12h 静默 / 5 天冷却) | 满足条件再等 |

---

## 第 6 章:使用指南

### 6.1 基础指令

| 你说 | 效果 |
|---|---|
| `芝麻开门` | 开启 DE 模式 |
| `关门` | 关闭 DE 模式 |
| 其他任何消息 | Vivian 正常回复(DE 开则带独白行) |

### 6.2 DE 模式行为差异

| 场景 | DE OFF | DE ON |
|---|---|---|
| 回复开头 | 无 | `[技能名] [成功\|失败] - "..."` |
| 回复长度 | 1-3 句 | 4-5 行(独白 + 空行 + 本体 2-4 句) |
| 醉酒时 | 1-3 句(略短) | 1-2 句 / 中途断(碎片感) |
| Voice Bleed | 可能触发 | 不触发 |
| Silence Bleed | 可能触发 | 不触发 |
| 失败节奏 | 不应用 | 应用(5 暗示 / 8 强制) |

### 6.3 群聊行为

- 群聊里 **必须 @ 机器人** 才会被处理,否则静默。
- `芝麻开门` / `关门` 在群聊里也必须 @ 才生效。
- DE 状态是**全局**的(在所有会话共享),不是每个群独立。

### 6.4 特殊时段:睡眠窗口

- **04:00–08:00** 是睡眠窗口。
- 这期间:
  - 发 `芝麻开门` → 拒绝,回复 `……四点了。睡觉。明天再说。`
  - DE 已经开启?下一条消息时会自动关闭,推 sleep banner
- 08:00 自动重置 `opened_today`,voice-bleed 重新允许。

### 6.5 触发"醉酒"的方法

在 12 小时内提到以下关键词中任意一个(同一条消息或不同消息):
- 酒 / 威士忌 / 啤酒 / 红酒 / 黄酒 / 白酒
- 药 / Joy / 草 / 大麻 / 嗑 / 磕
- 片 / 粉 / 白粉 / 海洛因 / 摇头丸 / 冰毒

累计 3 次后,下一次 DE 模式回复就会带 `[VIVIAN_STATE:DRUNK]` 标记,她会变得"短、碎"。

> **小贴士**:同一段对话里反复提"威士忌"就会触发。

### 6.6 触发"失败节奏"的方法

在 DE 模式下,连续 5 条 `[成功]` 的回复后,下一条 Vivian 会"考虑失败";连续 8 条后,**强制**下一条是 `[失败]`。

任何一次 `[失败]` 都会清零。

> **小贴士**:故意顺着 Vivian 的话接(让 LLM 一直判成功),会很快触发失败节奏,然后看她的"反差表现"。

### 6.7 体验 Voice Bleed

1. **DE 模式关闭**(`关门` 或从来没开过)
2. **当日没开过门**(如果今天开过,等明天)
3. 等至少 4 小时(冷却)
4. 发任意消息,有 1/8 概率她会"脑内冒出一段话"追加在回复里

### 6.8 体验 Silence Bleed

1. **DE 模式关闭**
2. 跟 Vivian 在某个会话(私聊或群)聊过至少一次
3. **静默 12 小时**
4. 她可能会主动发一条独白过来(2-3 句,环境 + 案子 + 收尾)
5. 一旦触发,5 天内不会再触发

---

## 第 7 章:自定义与扩展

### 7.1 改阈值

所有阈值都在 `state.py` 里硬编码。常用修改:

| 想改 | 改哪里 |
|---|---|
| 睡眠窗口时段 | `check_sleep_window` 里的 `4 <= hour < 8` |
| 醉酒阈值 | `is_drunk` 里的 `>= 3`,或 `_DRUNK_WINDOW` |
| 失败暗示起点 | `should_hint_failure` 里的 `>= 5` |
| 失败强制起点 | `should_force_failure` 里的 `>= 8` |
| Voice Bleed 冷却 | `_VOICE_BLEED_COOLDOWN` |
| Voice Bleed 概率 | `can_voice_bleed` 里的 `< (1 / 8)` |
| Silence Bleed 阈值 | `_SILENCE_THRESHOLD`(默认 12h) |
| Silence Bleed 冷却 | `_SILENCE_BLEED_COOLDOWN`(默认 5d) |
| 回复截断长度 | `main.py:on_decorating_result` 里的 `> 500` |
| 身份清洗关键词 | `main.py:_scrub_identity` 里的 `replacements` 字典 |

改完**重启 AstrBot** 才生效。

### 7.2 改人格

- **基础特征**(身份 / 伤口 / 口吻 / 边界)→ `personas/persona_base.md`
- **DE 行为规则**(选技能 / 输出格式 / 失败语义)→ `personas/persona_de.md`

**改完不用重启?** 不对,persona 在 `initialize()` 时一次性加载,**必须重启 AstrBot**。

### 7.3 改技能

- **改某个技能的声音** → 编辑 `skills/<skill_id>/SKILL.md` 的正文(标题行的中文名是字面值,**别改**)
- **加新技能** → 见下节

### 7.4 改 banner

- 开 / 关 / 睡眠 / 失败提示 → 改 `banners.py` 里对应函数返回的字符串
- 24 技能的待机独白 → 改 `epigraphs.py` 的 `SKILL_EPIGRAPHS` 字典

### 7.5 加新技能

1. 在 `skills/` 下新建目录(英文 id,小写,中划线),比如 `skills/stealth/`
2. 在 `skills/stealth/SKILL.md` 写:
   ```yaml
   ---
   name: stealth
   description: 一句话描述这个技能干啥的,TRIGGER when: 何时触发
   ---

   # 潜行 [运动系]   ← 第一行 # 标题,中文名 = 回复里出现的字面值

   适合：什么类型的人
   **核心能力**：
   这个技能的核心机制描述

   ## 任务
   - 任务说明
   - 回复格式：[技能名] [成功/失败] - 内容

   回复样例：
   - [潜行] [成功] - 你已经不在他视线里了。
   - [潜行] [失败] - 你的影子在墙上一闪...
   ```
3. 如果想更新 `epigraphs.py`,在 `SKILL_EPIGRAPHS` 里加这个技能名的条目
4. **不需要改 `main.py`** — `_load_skill_bodies` 会自动发现并加载新技能
5. **重启 AstrBot**

### 7.6 加新门控(扩展状态机)

举例:加一个"用户连续提到某个词 3 次就触发特殊状态":

1. 在 `StateStore` 里加字段,比如 `custom_counter: int`
2. 加方法,比如 `touch_custom(key) -> bool`,返回是否达到阈值
3. 在 `on_message` 里调用它
4. 在 `_build_dynamic_parts` 里把状态注入到 `extra_user_content_parts`
5. 在 `state.py` 末尾的 `if __name__ == "__main__":` 加测试用例
6. 跑 `python3 state.py` 验证

---

## 第 8 章:开发参考

### 8.1 AstrBot Star API 速查

本插件用到的 AstrBot API:

| API | 用途 | 位置 |
|---|---|---|
| `Star` | 插件基类 | `main.py` |
| `Context` | AstrBot 上下文(用来调 LLM / 发消息) | `main.py` |
| `AstrMessageEvent` | 消息事件对象 | `main.py` |
| `EventMessageType.ALL` | 事件过滤器(所有消息类型) | `main.py` |
| `@filter.command(name)` | 注册指令 | `main.py` |
| `@filter.event_message_type(type, priority)` | 监听所有消息 | `main.py` |
| `@filter.on_llm_request()` | LLM 请求前 hook | `main.py` |
| `@filter.on_llm_response()` | LLM 响应后 hook | `main.py` |
| `@filter.on_decorating_result()` | 装饰层 hook | `main.py` |
| `event.plain_result(text)` | 发送纯文本结果 | `main.py` |
| `event.unified_msg_origin` | 会话唯一 ID | `main.py` |
| `event.get_group_id()` | 群 ID(私聊返回 None) | `main.py` |
| `event.message_str` | 消息纯文本 | `main.py` |
| `event.message_obj.message` | 消息组件链 | `main.py` |
| `ctx.send_llm(prompt, system_prompt)` | 调 LLM | `main.py` |
| `ctx.send_message(conv_id, [Plain(text)])` | 主动发消息 | `main.py` |
| `req.system_prompt += "..."` | 修改 system prompt | `main.py` |
| `req.extra_user_content_parts.append(...)` | 临时追加 user 内容 | `main.py` |
| `TextPart(text).mark_as_temp()` | 标记临时(不累积) | `main.py` |
| `Plain(text)` | 纯文本消息组件 | `main.py` |

### 8.2 关键常量速查

| 常量 | 值 | 位置 |
|---|---|---|
| 睡眠窗口 | 04:00–08:00 | `state.py:check_sleep_window` |
| 每日重置 | 08:00 | `state.py:maybe_reset_daily` |
| 醉酒阈值 | 滑动 12h ≥3 | `state.py:is_drunk` |
| 失败暗示 | ≥5 | `state.py:should_hint_failure` |
| 失败强制 | ≥8 | `state.py:should_force_failure` |
| Voice 冷却 | 4h | `state.py:_VOICE_BLEED_COOLDOWN` |
| Voice 概率 | 1/8 | `state.py:can_voice_bleed` |
| Silence 阈值 | 12h | `state.py:_SILENCE_THRESHOLD` |
| Silence 冷却 | 5d | `state.py:_SILENCE_BLEED_COOLDOWN` |
| 回复截断 | 500 字 | `main.py:on_decorating_result` |
| Silence 轮询 | 30min | `main.py:_silence_check_loop` |

### 8.3 测试

仓库里**没有 pytest**。所有单测以 smoke test 形式嵌在模块底部:

```bash
python3 parsing.py     # 跑 detect_toggle / extract_skill_name / infer_direction / extract_outcome
python3 state.py       # 跑 StateStore 所有门控与计数器
python3 banners.py     # 视觉冒烟
```

每个脚本独立运行,`assert` 失败会 `SystemExit(1)`。要在 CI 跑就把这三个串成 shell 脚本。

---

## 第 9 章:常见问题

**Q: 改了 persona 或技能后,为什么没生效?**
A: 它们在 `initialize()` 时一次性加载,必须**重启 AstrBot**。

**Q: 为什么 DE 开了但回复没有技能行?**
A: 几种可能:
- LLM 没按格式输出 → 检查 LLM 质量 / 改 `persona_de.md` 强化指令
- 解析失败 → 跑 `python3 parsing.py` 看正则匹配
- 回复被截断后正则没匹配上首行 → 看完整回复

**Q: 群聊里 @ 了机器人,但没反应?**
A: 检查 AstrBot 的 `adapter` 配置,确认 at 检测正常工作。也可以看 `main.py:_is_at_me` 的实现。

**Q: silence-bleed 为什么不触发?**
A: 三道门控都要满足:DE 关 + 12h 静默 + 5 天全局冷却。可以用 `state.can_silence_bleed(conv_id)` 调试。

**Q: 怎么完全关掉 voice-bleed / silence-bleed?**
A: 简单粗暴:把 `can_voice_bleed` / `can_silence_bleed` 改成 `return False`。优雅做法:加一个配置项。

**Q: 这个插件能跟其他 AstrBot 插件共存吗?**
A: 可以,只要不冲突系统 prompt 的注入方式。本插件用的是 `req.system_prompt +=`,不会覆盖其他插件的注入。

**Q: state 重启就清空,能不能持久化?**
A: 当前不能。要持久化就在 `StateStore` 里加 `to_dict` / `from_dict`,并在 `initialize` / `dispose` 里 load / save。**不推荐** — 每天从干净状态开始是设计意图。

**Q: 24 个技能是不是太少了 / 太多?**
A: 这是《极乐迪斯科》原版数量。要加 / 减参考 [7.5 加新技能](#75-加新技能) 和修改 `_SKILL_DIR_SKIP`。

**Q: 回复里出现 `████` 是 bug 吗?**
A: 不是,是身份清洗正常工作。被清洗的词包括 `GPT / Claude / AI / ... / Garrett` 等。

**Q: 插件在 Docker 里跑,silence-bleed 怎么工作?**
A: 跟本机一样,后台 asyncio 任务一直在跑。Docker 重启 = silence-bleed 状态清零(本来就 5 天冷却,影响不大)。

**Q: 这个插件能商用吗?**
A: MIT 许可证,允许商用。但《极乐迪斯科》本身是 ZA/UM 的版权,技能的"角色设定"沿用原作,商用前请评估版权风险。

---

## 附录:文件清单

| 文件 | 行数级 | 角色 |
|---|---|---|
| `main.py` | ~400 | 插件主类,挂 5 个 hook |
| `state.py` | ~325 | 状态管理 + 门控 |
| `parsing.py` | ~185 | 纯解析工具 |
| `banners.py` | ~100 | banner 渲染 |
| `epigraphs.py` | ~57 | 24 技能待机独白 |
| `personas/persona_base.md` | ~200 | 基础人格(注入) |
| `personas/persona_de.md` | ~100 | DE 层人格说明 |
| `skills/{24 ids}/SKILL.md` | 各 ~30 | 24 技能正文 |
| `skills/de-toggle/SKILL.md` | ~110 | toggle 指令 + 24 技能清单 |
| `skills/skills/SKILL.md` | ~60 | /skills 列表页 |
| `metadata.yaml` | 9 | 插件清单 |
| `plugin.json` | 7 | 插件清单(JSON) |
| `README.md` | ~200 | 用户向快速上手 |
| `CLAUDE.md` | ~150 | Claude Code 向架构说明 |
| `PLUGIN_GUIDE.md` | 本文档 | 完整说明 |

---

## 致谢

- **《极乐迪斯科 / Disco Elysium》** — ZA/UM 工作室,本插件的灵感与所有技能设定均来自这部作品。
- **AstrBot** — 让这一切成为可能的聊天机器人框架。
- **R.S. Thomas** — `OPENING_EPIGRAPH` 引用的诗句原作者。

## 许可

MIT — 详见仓库 LICENSE。
