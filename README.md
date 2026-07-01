# 极乐迪斯科 · Vivian Vale

> 一个失忆的硬汉女警探,来自极乐迪斯科世界观。
> 基础人格始终在线,开启"芝麻开门"后激活 24 个 DE 技能声音层。

**Vivian Vale** 是一款 [AstrBot](https://github.com/Soulter/AstrBot) 插件,把聊天机器人变成一个 Chandler / Hammett 式冷硬侦探调的女警探,脑内住着 24 个互相争吵的"声音"。

- 帽子几乎不摘,手枪在身上,放大镜在手边,口袋里一只金属酒瓶。
- 失去了一个极其重要的人,想不起他是谁,也不说——喝到位了会漏半句。
- DE 模式开启后,24 个技能声音按语境轮流"带歪"她的立场和措辞。

---

## 功能特性

- **双层人格** — 基础人格(身份、伤口、口吻、边界)始终生效;DE 模式开启后叠加 24 个技能声音层。
- **24 个技能声音** — 分智力 / 精神 / 体质 / 运动四系,每个技能都是一种独立的"脑内人格",会按 `[技能名] [成功/失败]` 格式插入独白行。
- **DE 模式开关** — `芝麻开门` 开启 24 声音层,`关门` 收声。
- **睡眠窗口** — 凌晨 4:00–8:00 自动关闭 DE 模式。
- **失败节奏** — 连续 5 次 `[成功]` 后开始暗示失败,连续 8 次强制下一次为 `[失败]`,保持对话张力。
- **醉酒状态** — 检测"酒 / 威士忌 / 药"等关键词,12 小时滑动窗口内累计 3 次触发"醉酒",回复会变短、变碎。
- **食髓知味方向** — 内部追踪"清(烟 / 烟草)"vs"混(酒 / 药 / Joy)"的倾向,作为状态机的一部分。
- **Voice Bleed** — DE 模式关闭时,每条消息有 1/8 概率触发一段上下文相关的脑内独白(4 小时冷却,且当日未开过门时不触发)。
- **Silence Bleed** — 同一个会话静默超过 12 小时后,她可能会主动发一条独白过来(5 天冷却,需 DE 关闭时)。
- **身份边界清洗** — 自动替换可能泄露身份的关键词(`GPT` / `Claude` / `AI 语言模型` → `████`,`Garrett` → `那个人`);单条回复超过 500 字自动截断。
- **群聊过滤** — 群聊消息必须 @ 机器人才会回复。

---

## 安装

### 方式一:AstrBot WebUI 插件市场(推荐)

在 AstrBot 的 WebUI 插件市场中,直接粘贴本仓库的 GitHub URL 即可安装。

> **注意:** 仓库名 `astrbot-DE-female` 不符合 AstrBot 默认的 `astrbot-plugin-*` 命名约定。如果市场里搜不到或粘贴 URL 安装失败,请用方式二。

### 方式二:手动安装

```bash
cd /path/to/astrbot/data/plugins
git clone https://github.com/<your-fork>/astrbot-DE-female.git
```

然后重启 AstrBot。

### 版本要求

- **AstrBot v3.x**(使用 `@register_star` / `Star` / `Context.send_llm` API)
- Python 3.10+(代码用了 `str | None` 语法)
- 零第三方 Python 依赖,只依赖 AstrBot 自身

---

## 使用

装好之后,直接私聊或 @机器人 发指令即可。

| 指令 | 效果 |
|------|------|
| `芝麻开门` | 开启 DE 模式,激活 24 个技能声音层 |
| `关门` | 关闭 DE 模式,恢复纯本体人格 |

**DE 模式开启后**,每条回复以一行 `[技能名] [成功\|失败] - "<脑内独白>"` 开头,接着是 Vivian 的自然对话(无前缀)。

**DE 模式关闭后**,Vivian 正常聊天,但偶尔会有一段"脑子里冒出来"的独白(Voice Bleed)。

> 在凌晨 4:00–8:00 之间发 `芝麻开门` 会被睡眠窗口挡掉,回复 `……四点了。睡觉。明天再说。`。

---

## 24 个技能

### 🧠 智力系
- **逻辑思维** (logic) — 透过现象分析本质,察觉自相矛盾
- **博学多闻** (encyclopedia) — 冷知识储备,迷人轶事
- **能说会道** (rhetoric) — 辩论 / 修辞 / 说服
- **故弄玄虚** (drama) — 戏剧化叙事,看穿表演
- **标新立异** (conceptualization) — 创意联想,后现代艺术
- **见微知著** (visual-calculus) — 重构现场,空间推理

### 💭 精神系
- **平心定气** (volition) — 维持意志,不崩溃
- **内陆帝国** (inland-empire) — 直觉,清醒梦境
- **通情达理** (empathy) — 镜像情感,察觉隐藏情绪
- **争强好胜** (authority) — 威吓,支配,领导
- **同舟共济** (esprit-de-corps) — 团队,搭档,战友情
- **循循善诱** (suggestion) — 软实力,社交工程

### 💪 体质系
- **钢筋铁骨** (endurance) — 承受打击,生命值
- **坚忍不拔** (pain-threshold) — 受伤也继续,痛苦转化
- **强身健体** (physical-instrument) — 体力,挥拳,回旋踢
- **食髓知味** (electrochemistry) — 酒 / 药 / 感官放纵
- **天人感应** (shivers) — 城市之音,环境氛围
- **疑神疑鬼** (half-light) — 本能警觉,战斗 / 逃跑

### 🎯 运动系
- **眼明手巧** (hand-eye) — 枪法,接物,手眼协调
- **五感发达** (perception) — 观察细节,搜寻证据
- **反应速度** (reaction-speed) — 闪避,街头反应
- **鬼祟玲珑** (savoir-faire) — 潜行,杂技,优雅
- **能工巧匠** (interfacing) — 机械,电子,系统
- **从容自若** (composure) — 压力下保持冷静

每个技能的完整描述、触发语境、台词风格、回复样例见 [`skills/<skill_id>/SKILL.md`](skills/)。

---

## 架构概览

```
┌─ AstrBot 收到消息 ────────────────────────┐
│   ↓                                       │
│ on_message (priority=1, 先于 LLM pipeline) │
│   • 睡眠窗口自动关门                        │
│   • 群聊 @过滤                            │
│   • 关键词扫描推断食髓知味方向                │
│   • DE 关闭时可能触发 Voice Bleed           │
│   ↓                                       │
│ inject_persona (on_llm_request)            │
│   • 基础人格 → req.system_prompt           │
│   • DE 静态层(24 技能正文)→ system_prompt  │
│   • DE 动态层(醉酒/失败/方向)→             │
│     extra_user_content_parts(.mark_as_temp)│
│   ↓                                       │
│ LLM 生成回复                               │
│   ↓                                       │
│ on_response → 记录成功 / 失败节奏           │
│   ↓                                       │
│ on_decorating_result                       │
│   • 身份关键词清洗(████████)                │
│   • 截断 >500 字                           │
└────────────────────────────────────────────┘
```

后台还有一个 30 分钟轮询的 `silence_check_loop`,在会话静默超过 12 小时后主动推送一条独白。

详细代码结构与开发约定见 [CLAUDE.md](CLAUDE.md)。

---

## 目录结构

```
.
├── main.py              插件主类(VivianVale Star)
├── state.py             状态管理(StateStore,纯 stdlib)
├── parsing.py           解析工具(toggle / 技能名 / 方向 / 结果,纯 stdlib)
├── banners.py           banner 字符串渲染
├── epigraphs.py         24 技能的"待机独白"
├── personas/            人格文档
│   ├── persona_base.md  基础人格(始终生效)
│   └── persona_de.md    DE 模式人格层
├── skills/              24 个技能 SKILL.md + 元信息目录
│   ├── de-toggle/       toggle 指令 + 技能清单
│   ├── skills/          /skills 列表页
│   └── <24 skill_ids>/  技能正文
├── metadata.yaml        AstrBot 插件清单
├── plugin.json          同上(JSON 版本)
└── README.md
```

---

## 配置 / 自定义

这个插件**没有配置文件**——所有阈值都硬编码在 [`state.py`](state.py) 里:

| 项 | 默认值 | 位置 |
|---|---|---|
| 睡眠窗口 | 04:00–08:00 | `StateStore.check_sleep_window` |
| 每日重置 | 08:00 | `StateStore.maybe_reset_daily` |
| 醉酒阈值 | 滑动窗口 12h 内 ≥3 次 | `_DRUNK_WINDOW` / `is_drunk` |
| 失败暗示 | 连续 5 次 `[成功]` | `should_hint_failure` |
| 失败强制 | 连续 8 次 `[成功]` | `should_force_failure` |
| Voice Bleed 冷却 | 4 小时 | `_VOICE_BLEED_COOLDOWN` |
| Voice Bleed 概率 | 1/8 | `can_voice_bleed` |
| Silence Bleed 阈值 | 12 小时静默 | `_SILENCE_THRESHOLD` |
| Silence Bleed 冷却 | 5 天 | `_SILENCE_BLEED_COOLDOWN` |
| 身份清洗关键词 | `GPT/Claude/.../Garrett` | `_scrub_identity` |
| 回复截断长度 | 500 字 | `on_decorating_result` |

要改这些值,直接编辑 `state.py` 对应常量,然后重启 AstrBot。

要改人格表述,编辑 `personas/persona_base.md` / `persona_de.md`。
要改某个技能的声音,编辑 `skills/<skill_id>/SKILL.md` 的正文(标题行的中文名是技能在回复里出现的字面值,不要改)。

---

## 测试

仓库里**没有 pytest 套件**——单测以 smoke test 的形式嵌在模块末尾:

```bash
python3 parsing.py     # detect_toggle / extract_skill_name / infer_direction / extract_outcome
python3 state.py       # StateStore 全套门控与计数器
python3 banners.py     # 视觉冒烟
```

每个脚本独立运行,`assert` 失败会 `SystemExit(1)`。

---

## 致谢

- 致敬 **[Disco Elysium / 极乐迪斯科](https://discoelysium.com/)** — ZA/UM 工作室的 RPG 神作,本插件的灵感与所有技能设定均来自这部作品。
- 致敬 **[AstrBot](https://github.com/Soulter/AstrBot)** — 让这一切成为可能的聊天机器人框架。

---

## 许可

MIT — 详见仓库 LICENSE。
