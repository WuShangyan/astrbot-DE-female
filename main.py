import asyncio
import datetime
import json
import random
from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star

from .state import StateStore
from .parsing import detect_toggle, extract_skill_name, infer_direction, extract_outcome
from .banners import (
    render_open_banner,
    render_close_banner,
    render_clear_banner,
    render_haze_banner,
    render_voice_bleed_banner,
    render_sleep_banner,
)
from .epigraphs import get_epigraph

# ============================================================
# 常量
# ============================================================

_SKILL_DIR_SKIP = {"skills"}

# ============================================================
# 插件主类
# ============================================================

class VivianVale(Star):
    """极乐迪斯科 · Vivian Vale — AstrBot Star 插件"""

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------

    async def initialize(self):
        self._ctx = self.context  # v4: Star.__init__ already set self.context
        self._plugin_dir = Path(__file__).parent
        self.state = StateStore(self._plugin_dir / "state.json")
        self._skills_root = self._plugin_dir / "skills"

        # 加载 persona 文件
        self._persona_base = self._read_text(self._plugin_dir / "personas" / "persona_base.md")
        self._persona_de = self._read_text(self._plugin_dir / "personas" / "persona_de.md")

        # 预加载 24 个技能正文
        self._skill_bodies = self._load_skill_bodies()
        self._cn_to_id = self._build_cn_to_id_map()

        # 构建 DE 系统提示词(静态部分,写入 system_prompt)
        self._de_system_prompt = self._build_de_system_prompt()

        # 启动 silence-bleed 后台轮询
        self._silence_task = asyncio.create_task(self._silence_check_loop())

    async def terminate(self):
        """插件卸载时取消后台任务 (v4 lifecycle hook)"""
        self._silence_task.cancel()
        try:
            await self._silence_task
        except asyncio.CancelledError:
            pass

    # --------------------------------------------------------
    # Duty 1: toggle + sleep (event handler, yield)
    # --------------------------------------------------------

    @filter.command("芝麻开门")
    async def cmd_open(self, event: AstrMessageEvent):
        now = datetime.datetime.now()
        if self.state.check_sleep_window(now.hour):
            yield event.plain_result("……四点了。睡觉。明天再说。")
            return
        conv_id = event.unified_msg_origin
        self.state.set_open(conv_id, True, toggle_ts=now.timestamp())
        yield event.plain_result(render_open_banner())

    @filter.command("关门")
    async def cmd_close(self, event: AstrMessageEvent):
        conv_id = event.unified_msg_origin
        last_skill = self.state.get_last_skill(conv_id)
        self.state.set_open(conv_id, False)
        self.state.failure_streak = 0  # §4.3:芝麻关门清零 failure_streak
        self.state._save()              # 立即持久化(单字段写)
        yield event.plain_result(render_close_banner(last_skill))

    # --------------------------------------------------------
    # Duty 1b: 睡眠窗口 + 群聊过滤 + 方向推断 + voice bleed
    # (event handler, priority=1 → 先于 LLM pipeline)
    # --------------------------------------------------------

    @filter.event_message_type(EventMessageType.ALL, priority=1)
    async def on_message(self, event: AstrMessageEvent):
        now = datetime.datetime.now()
        hour = now.hour
        conv_id = event.unified_msg_origin
        is_sleep_now = self.state.check_sleep_window(hour)
        was_asleep = self.state.get_was_asleep(conv_id)

        # ── 醒→睡 转换:首次进入睡眠窗口时自动收摊 ──
        if (not was_asleep) and is_sleep_now:
            if self.state.de_enabled:
                last_skill = self.state.get_last_skill(conv_id)
                self.state.set_open(conv_id, False)
                self.state.clear_full_session(conv_id)
                yield event.plain_result(render_close_banner(last_skill))
            self.state.set_was_asleep(conv_id, True)
            return  # auto-close banner already conveyed "she's asleep"

        # ── 睡→醒 转换:首条醒来消息静默 reset drunk 相关状态 ──
        if was_asleep and (not is_sleep_now):
            self.state.clear_drunk_state(conv_id)
            self.state.set_was_asleep(conv_id, False)
            # fall through to normal wake-time processing

        self.state.maybe_reset_daily(hour)

        # ── 仍在睡眠窗口:任何后续消息都 yield sleep_banner ──
        if is_sleep_now:
            if self.state.de_enabled:
                # 防御性:若 was_asleep 状态因 reload 缺失导致漏掉了 auto-close
                self.state.set_open(conv_id, False)
            yield event.plain_result(render_sleep_banner())
            return

        # ── 群聊: 未 @ 跳过 ──
        if event.get_group_id() and not self._is_at_me(event):
            return

        # ── 记录消息时间(供 silence-bleed 判断) ──
        conv_id = event.unified_msg_origin
        self.state.touch_last_message(conv_id)

        # ── 推断方向(缓存到 state,供 on_llm_request 读取) ──
        user_text = event.message_str or ""
        direction = infer_direction(user_text)
        if direction:
            conv_id = event.unified_msg_origin
            self.state.set_direction(conv_id, direction)
            self.state.touch_drunk(direction)

        # ── DE OFF: voice bleed(3-tuple: 技能名 + 独白 + 本体一行) ──
        if not self.state.de_enabled and self._should_voice_bleed():
            triple = await self._generate_voice_bleed(event)
            if triple:
                skill_name, sample_line, body_line = triple
                yield event.plain_result(
                    render_voice_bleed_banner(skill_name, sample_line, body_line)
                )

    # --------------------------------------------------------
    # Duty 3: 注入 persona (LLM request hook, 不 yield)
    # --------------------------------------------------------

    @filter.on_llm_request()
    async def inject_persona(self, event: AstrMessageEvent, req):
        """在 LLM 请求发出前注入 persona 和动态状态"""

        # 基础人格始终注入(不带哨兵——AstrBot 每次清空 req)
        req.system_prompt += "\n\n" + self._persona_base

        # DE 层: 静态 + 动态
        if self.state.de_enabled:
            # 静态层 → system_prompt
            req.system_prompt += "\n\n" + self._de_system_prompt

            # 动态层 → extra_user_content_parts(.mark_as_temp())
            conv_id = event.unified_msg_origin
            dynamic_parts = self._build_dynamic_parts(conv_id)
            if dynamic_parts:
                from astrbot.api.message_components import TextPart
                req.extra_user_content_parts.append(
                    TextPart(text=dynamic_parts).mark_as_temp()
                )

    # --------------------------------------------------------
    # Duty 7: 失败节奏(回复后检查)
    # --------------------------------------------------------

    @filter.on_llm_response()
    async def on_response(self, event: AstrMessageEvent, response):
        resp_text = response.completion_text
        outcome = extract_outcome(resp_text)
        self.state.record_failure(outcome == "失败")
        if self.state.de_enabled:
            skill_name = extract_skill_name(resp_text)
            if skill_name:
                conv_id = event.unified_msg_origin
                self.state.set_last_skill(conv_id, skill_name)

    # --------------------------------------------------------
    # Duty 9: 身份边界 + 语音守卫(装饰层)
    # --------------------------------------------------------

    @filter.on_decorating_result()
    async def on_decorating(self, event: AstrMessageEvent):
        result = event.get_result()
        if not result or not result.chain:
            return

        # --- Direction transition: emit clear/haze banner if changed --------
        conv_id = event.unified_msg_origin
        resp_text = "".join(
            comp.text for comp in result.chain if isinstance(comp, Plain)
        )
        new_direction = infer_direction(resp_text)
        prev_direction = self.state.get_direction(conv_id)
        if self.state.de_enabled and new_direction and new_direction != prev_direction:
            banner = render_clear_banner() if new_direction == "清" else render_haze_banner()
            try:
                # AstrBot v4: use Context.send_message with conv_id (no event.send API).
                await self._ctx.send_message(conv_id, [Plain(text=banner)])
            except Exception:
                pass  # never block the main reply
        if new_direction:
            self.state.set_direction(conv_id, new_direction)

        # --- Identity scrub + length cap (existing behavior) ---------------
        for comp in result.chain:
            if isinstance(comp, Plain):
                # 身份边界: 替换泄露
                comp.text = self._scrub_identity(comp.text)
                # 语音守卫: 截断
                if len(comp.text) > 500:
                    comp.text = comp.text[:500] + "……"

    # ========================================================
    # 内部方法
    # ========================================================

    # ── 文件加载 ──

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8").strip()

    def _load_skill_bodies(self) -> dict[str, str]:
        """加载 24 个技能正文,{skill_id: body_md}"""
        bodies = {}
        for skill_dir in sorted(self._skills_root.iterdir()):
            if skill_dir.name in _SKILL_DIR_SKIP:
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            body = self._extract_skill_body(skill_md)
            if body:
                bodies[skill_dir.name] = body
        return bodies

    def _extract_skill_body(self, path: Path) -> str:
        """提取 SKILL.md 正文(从第一个 # 标题开始,去掉 YAML frontmatter)"""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        body_start = 0
        in_frontmatter = False
        for i, line in enumerate(lines):
            if i == 0 and line.strip() == "---":
                in_frontmatter = True
                continue
            if in_frontmatter and line.strip() == "---":
                body_start = i + 1
                in_frontmatter = False
                continue
            if not in_frontmatter and line.startswith("# "):
                body_start = i
                break
        return "\n".join(lines[body_start:]).strip()

    def _build_cn_to_id_map(self) -> dict[str, str]:
        """中文技能名 → skill_id 的映射"""
        mapping = {}
        for skill_id, body in self._skill_bodies.items():
            first_line = body.split("\n")[0]
            name = first_line.replace("# ", "").split("[")[0].strip()
            if name:
                mapping[name] = skill_id
        return mapping

    # ── DE 系统提示词 ──

    def _build_de_system_prompt(self) -> str:
        """静态层: persona_de.md + 24 个技能正文"""
        parts = [self._persona_de, "", "---", ""]
        for skill_id, body in self._skill_bodies.items():
            parts.append(f"[SKILL:{skill_id}]")
            parts.append(body)
            parts.append("")
        return "\n".join(parts)

    # ── 动态层 ──

    def _build_dynamic_parts(self, conv_id: str) -> str:
        """构建 extra_user_content_parts 的动态文本"""
        lines = []

        # 醉酒状态
        if self.state.is_drunk():
            lines.append("[VIVIAN_STATE:DRUNK] 醉酒中。回复缩短、语气变散。")

        # 失败节奏注入
        if self.state.should_force_failure():
            lines.append("[VIVIAN_FAILURE:FORCE] 下一个技能回复必须是[失败]。")
        elif self.state.should_hint_failure():
            lines.append("[VIVIAN_FAILURE:HINT] 考虑回复[失败]。连续成功太多了。")

        # 方向提示
        direction = self.state.get_direction(conv_id)
        if direction:
            label = "清冽" if direction == "清" else "混沌"
            lines.append(f"[VIVIAN_DIRECTION:{direction}] {label}状态。")

        return "\n".join(lines)

    # ── Voice bleed(LLM 生成,与上下文相关) ──

    def _should_voice_bleed(self) -> bool:
        """检查 voice bleed 是否应该触发(只做门控判断)"""
        return self.state.can_voice_bleed()

    async def _generate_voice_bleed(
        self, event: AstrMessageEvent
    ) -> tuple[str, str, str] | None:
        """Voice-bleed: code picks skill_name and body_line; LLM only writes
        the sample_line (one short utterance matching the chosen skill's voice).

        Returns (skill_name, sample_line, body_line) or None on any failure.
        Caller passes the tuple to render_voice_bleed_banner(...).
        """
        # 1. Code-side: pick a skill (random, excluding last voice-bleed skill)
        from .epigraphs import SKILL_EPIGRAPHS  # relative import (matches AstrBot v4 plugin convention)

        exclude = self.state._voice_bleed_last_skill
        candidates = [k for k in SKILL_EPIGRAPHS if k != exclude]
        if not candidates:
            candidates = list(SKILL_EPIGRAPHS.keys())
        skill_name = random.choice(candidates)

        # 2. Code-side: pick a Vivian reaction line
        from .banners import _VOICE_BLEED_BODY_LINES  # relative import
        body_line = random.choice(_VOICE_BLEED_BODY_LINES)

        # 3. LLM-side: write the skill's whisper (one sentence)
        skill_desc = SKILL_EPIGRAPHS.get(skill_name, "")
        prompt = (
            "你是 Vivian Vale,失忆硬汉女警探。DE 模式关闭时,脑子里偶尔会有一个声音漏出来。\n"
            f"现在漏出的声音来自技能「{skill_name}」——这个声音的内核是:\n"
            f"{skill_desc.strip()}\n\n"
            "用这个技能的口吻,写一句 8-30 字的脑内独白(用'你'称呼用户)。\n"
            "输出格式(JSON,严格): {\"sample\": \"<你的独白>\"}\n"
            "不要加任何解释、标签、或额外文字。"
        )

        try:
            response = await self._ctx.send_llm(
                prompt=prompt,
                system_prompt=self._persona_base,
            )
            text = response.completion_text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.strip("`").lstrip("json").strip()
            data = json.loads(text)
            sample_line = data["sample"].strip()
            if sample_line:
                self.state.record_voice_bleed(skill_name)
                return (skill_name, sample_line, body_line)
        except Exception:
            pass
        return None

    def _skill_cn_name(self, skill_id: str) -> str | None:
        """从 skill_id 获取中文名"""
        body = self._skill_bodies.get(skill_id, "")
        if not body:
            return None
        first_line = body.split("\n")[0]
        return first_line.replace("# ", "").split("[")[0].strip() or None

    # ── 群聊 @ 检测 ──

    @staticmethod
    def _is_at_me(event: AstrMessageEvent) -> bool:
        """扫描消息组件链,检查是否有 @bot"""
        chain = event.message_obj.message
        for comp in chain:
            if comp.type == "at" and comp.qq == str(event.get_self_id()):
                return True
        return False

    # ── 身份边界清洗 ──

    @staticmethod
    def _scrub_identity(text: str) -> str:
        """替换可能泄露身份的关键词"""
        replacements = {
            "GPT": "████",
            "Claude": "████",
            "AI 语言模型": "████",
            "人工智能": "████",
            "OpenAI": "████",
            "Anthropic": "████",
            "大模型": "████",
            "系统提示词": "████",
            "system prompt": "████",
            "Garrett": "那个人",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    # ── Silence-bleed: 定时轮询 ──

    async def _silence_check_loop(self):
        """每 30 分钟检查一次,超过 12 小时没对话就主动嘟囔"""
        while True:
            await asyncio.sleep(1800)  # 30 分钟
            for conv_id in list(self.state._last_message_ts.keys()):
                if self.state.can_silence_bleed(conv_id):
                    await self._maybe_silence_bleed(conv_id)

    async def _maybe_silence_bleed(self, conv_id: str):
        """调 LLM 生成一段环境+案子独白,主动发到会话"""
        prompt = (
            "Vivian Vale 已经超过 12 小时没有和任何人说话了。"
            "请以 Vivian 的口吻写一段 2-3 句的独白,格式要求:\n"
            "1. 第一句写环境(她在干什么、周围什么声音、什么光线、什么天气)\n"
            "2. 第二句从种子案例池里挑一个案子嘟囔(不需要完整信息,就是放不下)\n"
            "3. 可以收一句冷的(……算了 / 不关你的事),或者什么都不收\n"
            "不要加任何标签、不要解释。直接输出独白。"
        )
        try:
            # 调 AstrBot LLM 接口
            response = await self._ctx.send_llm(
                prompt=prompt,
                system_prompt=self._persona_base,
            )
            text = response.completion_text.strip()
            if text:
                # 身份边界清洗
                text = self._scrub_identity(text)
                # 主动推送到会话
                await self._ctx.send_message(conv_id, [Plain(text=text)])
                self.state.record_silence_bleed()
        except Exception:
            pass  # 静默失败,不打扰用户
