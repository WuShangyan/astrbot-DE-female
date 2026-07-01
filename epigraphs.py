"""Skill-to-epigraph lookup. Used to fill the close banner.

The opening epigraph is the fixed R.S. Thomas / Disco Elysium line; the
24 per-skill epigraphs are short Chinese sentences, each an in-character
inner voice whisper that captures the skill's essence when idle — not
advice, not a command, just a mood.

All returned strings are pre-indented (12 leading spaces) so they can be
embedded directly between the top bar and the divider in a banner.
"""

OPENING_EPIGRAPH = (
    "            复仇女神就在家中的镜子里；那便是她们的住址。\n"
    "          哪怕这世间最澄清的水，只要够深，也能让人沉溺。"
)

SKILL_EPIGRAPHS: dict[str, str] = {
    # 智力系 (6)
    "逻辑思维": "            世界是一道数学题，而我少了一页草稿纸。",
    "博学多闻": "            你知道吗？不，你不知道。",
    "能说会道": "            每一句话都是武器，我还没选好口径。",
    "故弄玄虚": "            嘘——这出戏才刚开场。",
    "标新立异": "            所有的平庸都在等一个隐喻把它们炸开。",
    "见微知著": "            碎片指向外面。打碎窗户的人站在里面。",
    # 精神系 (6)
    "平心定气": "            挺住。挺住就是一切。",
    "内陆帝国": "            那条领带在看着你。它有话要说。",
    "通情达理": "            她在笑，但她不是真的在笑。",
    "争强好胜": "            别退。把那句话再说一遍。",
    "循循善诱": "            话已经自己跑出来了，不是我说的。",
    "同舟共济": "            楼下那个人——你没见过面，但他会替你挡子弹。",
    # 体质系 (6)
    "钢筋铁骨": "            头在痛，胃在翻，但你还能再跑十公里。",
    "坚忍不拔": "            这只是一点宿畏光。不要大惊小怪。",
    "强身健体": "            肌肉记得，比脑子快。",
    "食髓知味": "            你得一直醉着。醉于酒、醉于诗，或醉于美德，随你的便。",
    "天人感应": "            雪融进墙缝，淌进下水道。地面的第一朵铃兰正在开花。",
    "疑神疑鬼": "            摸口袋！摸——该死，你不知道里面有什么。",
    # 运动系 (6)
    "眼明手巧": "            那枪打歪了。肩膀太高，眼睛不信手。",
    "五感发达": "            地板下面有气味。糖罐里有光。",
    "反应速度": "            她要走了。身体比脑子先动。",
    "鬼祟玲珑": "            一个漂亮的翻身就能解决所有问题。",
    "能工巧匠": "            手指和机器之间，没有缝隙。",
    "从容自若": "            真是漂亮。谁也没看出你在发抖。",
}


def get_epigraph(skill_name):
    """Return the indented epigraph body for the given skill name.

    Falls back to OPENING_EPIGRAPH for None or unknown skill names.
    """
    if skill_name and skill_name in SKILL_EPIGRAPHS:
        return SKILL_EPIGRAPHS[skill_name]
    return OPENING_EPIGRAPH
