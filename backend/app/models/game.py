from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    WEREWOLF = "werewolf"
    WOLF_BEAUTY = "wolf_beauty"
    WHITE_WOLF = "white_wolf"
    HIDDEN_WOLF = "hidden_wolf"
    WOLF_KING = "wolf_king"
    EVIL_SPIRIT_KNIGHT = "evil_spirit_knight"
    STONE_GARGOYLE = "stone_gargoyle"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    GUARD = "guard"
    KNIGHT = "knight"
    IDIOT = "idiot"
    SILENCER = "silencer"
    GRAVEKEEPER = "gravekeeper"
    VILLAGER = "villager"


class Phase(str, Enum):
    SETUP = "setup"
    NIGHT = "night"
    DAY_ANNOUNCE = "day_announce"
    DAY_DISCUSS = "day_discuss"
    DAY_VOTE = "day_vote"
    HUNTER_REVENGE = "hunter_revenge"
    GAME_OVER = "game_over"


class PlayerStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"


class WinRule(str, Enum):
    SLAUGHTER_SIDE = "slaughter_side"
    TOTAL_ELIMINATION = "total_elimination"
    PARITY = "parity"


class WitchSelfSaveRule(str, Enum):
    NEVER = "never"
    FIRST_NIGHT_ONLY = "first_night_only"
    ALWAYS = "always"


WOLF_ROLES = {
    Role.WEREWOLF,
    Role.WOLF_BEAUTY,
    Role.WHITE_WOLF,
    Role.HIDDEN_WOLF,
    Role.WOLF_KING,
    Role.EVIL_SPIRIT_KNIGHT,
    Role.STONE_GARGOYLE,
}

GOD_ROLES = {
    Role.SEER,
    Role.WITCH,
    Role.HUNTER,
    Role.GUARD,
    Role.KNIGHT,
    Role.IDIOT,
    Role.SILENCER,
    Role.GRAVEKEEPER,
}

VISIBLE_PACK_WOLF_ROLES = {
    Role.WEREWOLF,
    Role.WOLF_BEAUTY,
    Role.WHITE_WOLF,
    Role.WOLF_KING,
    Role.EVIL_SPIRIT_KNIGHT,
}

COMMON_WOLF_ROLES = {
    Role.WEREWOLF,
}

ROLE_NAMES_ZH = {
    Role.WEREWOLF: "狼人",
    Role.WOLF_BEAUTY: "狼美人",
    Role.WHITE_WOLF: "白狼王",
    Role.HIDDEN_WOLF: "隐狼",
    Role.WOLF_KING: "狼王",
    Role.EVIL_SPIRIT_KNIGHT: "恶灵骑士",
    Role.STONE_GARGOYLE: "石像鬼",
    Role.SEER: "预言家",
    Role.WITCH: "女巫",
    Role.HUNTER: "猎人",
    Role.GUARD: "守卫",
    Role.KNIGHT: "骑士",
    Role.IDIOT: "白痴",
    Role.SILENCER: "禁言长老",
    Role.GRAVEKEEPER: "守墓人",
    Role.VILLAGER: "平民",
}


class GameRules(BaseModel):
    win_rule: WinRule = WinRule.SLAUGHTER_SIDE
    witch_self_save_rule: WitchSelfSaveRule = WitchSelfSaveRule.FIRST_NIGHT_ONLY
    same_guard_save_survives: bool = False
    guard_can_self_protect: bool = True
    first_night_last_words: bool = True
    sheriff_enabled: bool = True
    sheriff_vote_multiplier: float = 1.5
    white_wolf_explode_during_day: bool = True
    white_wolf_explode_ends_day: bool = True
    knight_duel_ends_discussion: bool = True


ROLE_DESCRIPTIONS = {
    Role.WEREWOLF: "普通狼人。夜晚与狼队友共同决定刀口。",
    Role.WOLF_BEAUTY: "夜晚可以魅惑一名玩家，自己出局时被魅惑者会殉情。",
    Role.WHITE_WOLF: "白天发言阶段可以自爆并带走一名玩家。",
    Role.HIDDEN_WOLF: "普通狼人存活时不与狼队互认，且被预言家查验显示为好人；所有普通狼人出局后觉醒，获得夜刀。",
    Role.WOLF_KING: "被放逐或因非毒原因死亡时，可以开枪带走一名玩家。",
    Role.EVIL_SPIRIT_KNIGHT: "被预言家查验或被女巫毒时会反噬对应神职。",
    Role.STONE_GARGOYLE: "普通狼人存活时不参与狼刀，每晚可查验一名玩家的准确身份；所有普通狼人出局后觉醒，获得夜刀。",
    Role.SEER: "每晚可以查验一名玩家阵营。",
    Role.WITCH: "拥有一瓶解药和一瓶毒药，每种只能使用一次，每晚最多用一瓶。",
    Role.HUNTER: "因非中毒原因死亡时，可以开枪带走一名玩家。",
    Role.GUARD: "每晚守护一名玩家，通常不能连续两晚守同一人。",
    Role.KNIGHT: "白天讨论阶段可以决斗一名玩家，若对方是狼则其死亡，否则自己死亡。",
    Role.IDIOT: "被投票放逐时翻牌免死，之后永久失去投票权。",
    Role.SILENCER: "每晚禁言一名玩家，使其第二天无法发言但仍可投票。",
    Role.GRAVEKEEPER: "每晚得知前一天被放逐玩家是否属于狼人阵营。",
    Role.VILLAGER: "没有主动技能，依靠发言和投票找狼。",
}


class PlayerConfig(BaseModel):
    name: str
    personality: str = ""
    llm_provider: str = ""
    model_name: str = ""


class GameConfig(BaseModel):
    players: list[PlayerConfig]
    roles: list[Role]
    auto_advance: bool = False
    step_delay: float = 2.0
    rules: GameRules = Field(default_factory=GameRules)


class GameTemplate(BaseModel):
    id: str
    name: str
    description: str
    roles: list[Role]
    rules: GameRules


def derive_default_rules(roles: list[Role]) -> GameRules:
    has_guard = Role.GUARD in roles
    return GameRules(
        win_rule=WinRule.SLAUGHTER_SIDE,
        witch_self_save_rule=WitchSelfSaveRule.FIRST_NIGHT_ONLY,
        same_guard_save_survives=False,
        guard_can_self_protect=True,
        first_night_last_words=True,
        sheriff_enabled=True,
        sheriff_vote_multiplier=1.5,
        white_wolf_explode_during_day=True,
        white_wolf_explode_ends_day=True,
        knight_duel_ends_discussion=True,
    )


def build_template(template_id: str, name: str, description: str, roles: list[Role]) -> GameTemplate:
    return GameTemplate(
        id=template_id,
        name=name,
        description=description,
        roles=roles,
        rules=derive_default_rules(roles),
    )


def summarize_rules(rules: GameRules) -> str:
    win_text = {
        WinRule.SLAUGHTER_SIDE: "屠边",
        WinRule.TOTAL_ELIMINATION: "屠城",
        WinRule.PARITY: "人狼平票即狼赢",
    }[rules.win_rule]
    self_save_text = {
        WitchSelfSaveRule.NEVER: "女巫不可自救",
        WitchSelfSaveRule.FIRST_NIGHT_ONLY: "女巫仅首夜可自救",
        WitchSelfSaveRule.ALWAYS: "女巫可以自救",
    }[rules.witch_self_save_rule]
    guard_save_text = "同守同救存活" if rules.same_guard_save_survives else "同守同救死亡"
    sheriff_text = f"警长票重 {rules.sheriff_vote_multiplier:g}" if rules.sheriff_enabled else "无警长"
    white_wolf_text = "白狼王白天可自爆" if rules.white_wolf_explode_during_day else "白狼王仅出局触发"
    return f"{win_text} / {self_save_text} / {guard_save_text} / {sheriff_text} / {white_wolf_text}"


GAME_TEMPLATES: list[GameTemplate] = [
    build_template(
        "6p_beginner",
        "6人入门局（预女）",
        "2狼 + 预言家 + 女巫 + 2平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.SEER, Role.WITCH, Role.VILLAGER, Role.VILLAGER],
    ),
    build_template(
        "8p_standard",
        "8人标准局（预女）",
        "3狼 + 预言家 + 女巫 + 3平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.SEER, Role.WITCH, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    ),
    build_template(
        "9p_hunter",
        "9人预女猎",
        "3狼 + 预言家 + 女巫 + 猎人 + 3平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.SEER, Role.WITCH, Role.HUNTER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    ),
    build_template(
        "12p_standard",
        "12人标准局（预女猎白）",
        "4狼 + 预言家 + 女巫 + 猎人 + 白痴 + 4平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.SEER, Role.WITCH, Role.HUNTER, Role.IDIOT, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    ),
    build_template(
        "12p_wolf_king_guard",
        "12人狼王守卫",
        "3狼 + 狼王 + 预言家 + 女巫 + 猎人 + 守卫 + 4平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.WOLF_KING, Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    ),
    build_template(
        "12p_white_wolf_guard",
        "12人白狼王守卫",
        "3狼 + 白狼王 + 预言家 + 女巫 + 猎人 + 守卫 + 4平民",
        [Role.WEREWOLF, Role.WEREWOLF, Role.WEREWOLF, Role.WHITE_WOLF, Role.SEER, Role.WITCH, Role.HUNTER, Role.GUARD, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER],
    ),
]

DEFAULT_AI_NAMES = ["阿尔法", "贝塔", "伽马", "德尔塔", "艾普", "泽塔", "伊塔", "西塔", "约塔", "卡帕", "拉姆达", "缪"]

DEFAULT_PERSONALITIES = [
    "冷静理性，善于逻辑推理，发言简洁有力。",
    "热情冲动，直觉敏锐，喜欢大胆点名。",
    "细心谨慎，擅长观察细节，表达条理清晰。",
    "幽默活跃，善于带动气氛，但分析也很认真。",
    "沉稳老练，喜欢复盘投票和发言中的矛盾点。",
    "锋利直接，敢于质疑权威，不怕得罪人。",
    "温和大方，擅长团结好人阵营，投票不盲从。",
    "机智灵活，擅长试探与反诈，让对手难以摸透。",
    "安静观察，话不多，但每句话尽量有信息量。",
    "大胆激进，喜欢先发制人，争取话语主动权。",
    "心思缜密，擅长拆解每个人的发言漏洞。",
    "果断干练，投票坚决，不轻易弃票。",
]


class Player(BaseModel):
    name: str
    role: Role
    status: PlayerStatus = PlayerStatus.ALIVE
    personality: str = ""
    is_ai: bool = True
    llm_provider: str = ""
    model_name: str = ""
    vote_right: bool = True


class NightAction(BaseModel):
    werewolf_target: Optional[str] = None
    seer_target: Optional[str] = None
    seer_result: Optional[Role] = None
    witch_save: bool = False
    witch_poison_target: Optional[str] = None
    guard_target: Optional[str] = None
    last_guard_target: Optional[str] = None
    wolf_beauty_target: Optional[str] = None
    last_wolf_beauty_target: Optional[str] = None
    silencer_target: Optional[str] = None
    last_silencer_target: Optional[str] = None
    stone_gargoyle_target: Optional[str] = None
    stone_gargoyle_result: Optional[Role] = None
    gravekeeper_alignment: Optional[str] = None
    reflected_target: Optional[str] = None
    reflected_reason: Optional[str] = None


class VoteRecord(BaseModel):
    voter: str
    target: str


class SpeechRecord(BaseModel):
    speaker: str
    inner_thought: str
    public_speech: str
    round_number: int
    phase: str
    skill_info: str = ""


class WolfChatRecord(BaseModel):
    speaker: str
    message: str
    round_number: int
    kill_target: Optional[str] = None
    visible_to: list[str] = Field(default_factory=list)


class GameState(BaseModel):
    game_id: str
    players: list[Player]
    phase: Phase = Phase.SETUP
    round_number: int = 0
    night_actions: Optional[NightAction] = None
    speeches: list[SpeechRecord] = Field(default_factory=list)
    wolf_chat: list[WolfChatRecord] = Field(default_factory=list)
    votes: list[VoteRecord] = Field(default_factory=list)
    night_kills: list[str] = Field(default_factory=list)
    day_eliminated: Optional[str] = None
    hunter_target: Optional[str] = None
    witch_has_save: bool = True
    witch_has_poison: bool = True
    winner: Optional[str] = None
    history: list[dict] = Field(default_factory=list)
    created_at: str = ""
    finished_at: Optional[str] = None
    auto_advance: bool = False
    step_delay: float = 2.0
    gm_announcement: str = ""
    rules: GameRules = Field(default_factory=GameRules)
    sheriff_name: Optional[str] = None
    sheriff_election_completed: bool = False
    current_charmed_target: Optional[str] = None
    silenced_player: Optional[str] = None
    agent_notes: dict[str, list[str]] = Field(default_factory=dict)
