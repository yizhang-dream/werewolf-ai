import type { GameRules, Phase, RoleId } from "../types/game";

export type RoleTeam = "wolf" | "god" | "villager";

export type RoleLibraryItem = {
  id: RoleId;
  label: string;
  color: string;
  bg: string;
  desc: string;
  team: RoleTeam;
};

export const ROLE_LIBRARY: RoleLibraryItem[] = [
  { id: "werewolf", label: "狼人", color: "#ff6b57", bg: "rgba(255,107,87,0.14)", desc: "夜晚与狼队友共同决定刀口。", team: "wolf" },
  { id: "wolf_beauty", label: "狼美人", color: "#ff7d97", bg: "rgba(255,125,151,0.14)", desc: "夜晚魅惑一名玩家，自己出局时对方殉情。", team: "wolf" },
  { id: "white_wolf", label: "白狼王", color: "#ff9d5c", bg: "rgba(255,157,92,0.14)", desc: "白天可以自爆并带走一名玩家。", team: "wolf" },
  { id: "hidden_wolf", label: "隐狼", color: "#dc6a4d", bg: "rgba(220,106,77,0.14)", desc: "前期不显狼相，普通狼出局后觉醒。", team: "wolf" },
  { id: "wolf_king", label: "狼王", color: "#ffbf67", bg: "rgba(255,191,103,0.14)", desc: "被放逐或非毒死亡时可以开枪。", team: "wolf" },
  { id: "evil_spirit_knight", label: "恶灵骑士", color: "#bf89ff", bg: "rgba(191,137,255,0.14)", desc: "被查验或被毒会反噬对应神职。", team: "wolf" },
  { id: "stone_gargoyle", label: "石像鬼", color: "#8f97ff", bg: "rgba(143,151,255,0.14)", desc: "觉醒前可验具体身份，觉醒后参与狼刀。", team: "wolf" },
  { id: "seer", label: "预言家", color: "#67b8ff", bg: "rgba(103,184,255,0.14)", desc: "每晚查验一名玩家阵营。", team: "god" },
  { id: "witch", label: "女巫", color: "#ce8dff", bg: "rgba(206,141,255,0.14)", desc: "拥有一瓶解药和一瓶毒药。", team: "god" },
  { id: "hunter", label: "猎人", color: "#ffc75f", bg: "rgba(255,199,95,0.14)", desc: "非中毒死亡时可以开枪。", team: "god" },
  { id: "guard", label: "守卫", color: "#59d49b", bg: "rgba(89,212,155,0.14)", desc: "每晚守护一名玩家。", team: "god" },
  { id: "knight", label: "骑士", color: "#67d5f2", bg: "rgba(103,213,242,0.14)", desc: "白天可发起一次决斗。", team: "god" },
  { id: "idiot", label: "白痴", color: "#ecd76c", bg: "rgba(236,215,108,0.14)", desc: "被投出时翻牌免死，但失去投票权。", team: "god" },
  { id: "silencer", label: "禁言长老", color: "#4bd1c1", bg: "rgba(75,209,193,0.14)", desc: "夜晚让一名玩家次日无法发言。", team: "god" },
  { id: "gravekeeper", label: "守墓人", color: "#d0d7d5", bg: "rgba(208,215,213,0.14)", desc: "夜晚得知前一日被放逐者的阵营。", team: "god" },
  { id: "villager", label: "平民", color: "#c4beb1", bg: "rgba(196,190,177,0.14)", desc: "依靠发言、站边和投票取胜。", team: "villager" },
];

export const ROLE_META = Object.fromEntries(ROLE_LIBRARY.map((role) => [role.id, role])) as Record<RoleId, RoleLibraryItem>;

export const PHASE_META: Record<Phase, { label: string; color: string; tone: string }> = {
  setup: { label: "准备中", color: "#b7bcc8", tone: "rgba(183,188,200,0.18)" },
  night: { label: "黑夜", color: "#8695ff", tone: "rgba(134,149,255,0.18)" },
  day_announce: { label: "天亮公告", color: "#f2bc63", tone: "rgba(242,188,99,0.18)" },
  day_discuss: { label: "白天讨论", color: "#71d2b8", tone: "rgba(113,210,184,0.18)" },
  day_vote: { label: "放逐投票", color: "#eba65f", tone: "rgba(235,166,95,0.18)" },
  hunter_revenge: { label: "猎人开枪", color: "#ff8f71", tone: "rgba(255,143,113,0.18)" },
  game_over: { label: "游戏结束", color: "#dfb3ff", tone: "rgba(223,179,255,0.18)" },
};

export function countRoles(roles: RoleId[]) {
  const counts = new Map<RoleId, number>();
  for (const role of roles) {
    counts.set(role, (counts.get(role) || 0) + 1);
  }
  return ROLE_LIBRARY.filter((role) => counts.has(role.id)).map((role) => ({
    ...role,
    count: counts.get(role.id) || 0,
  }));
}

export function summarizeTeams(roles: RoleId[]) {
  const totals = {
    wolf: 0,
    god: 0,
    villager: 0,
  };
  for (const role of roles) {
    totals[ROLE_META[role].team] += 1;
  }
  return totals;
}

export function formatRules(rules: GameRules) {
  const winText = {
    slaughter_side: "屠边",
    total_elimination: "屠城",
    parity: "人狼平票即狼胜",
  }[rules.win_rule];

  const selfSaveText = {
    never: "女巫不可自救",
    first_night_only: "女巫首夜可自救",
    always: "女巫全程可自救",
  }[rules.witch_self_save_rule];

  const guardSaveText = rules.same_guard_save_survives ? "同守同救存活" : "同守同救死亡";
  const guardSelfText = rules.guard_can_self_protect ? "守卫可自守" : "守卫不可自守";
  const sheriffText = rules.sheriff_enabled ? `警长票权 ${rules.sheriff_vote_multiplier}` : "无警长";
  return [winText, selfSaveText, guardSaveText, guardSelfText, sheriffText].join(" / ");
}

export function describeRules(rules: GameRules) {
  return [
    { label: "胜利规则", value: { slaughter_side: "屠边", total_elimination: "屠城", parity: "平票狼胜" }[rules.win_rule] },
    { label: "女巫自救", value: { never: "不可", first_night_only: "仅首夜", always: "始终可用" }[rules.witch_self_save_rule] },
    { label: "同守同救", value: rules.same_guard_save_survives ? "存活" : "死亡" },
    { label: "守卫自守", value: rules.guard_can_self_protect ? "允许" : "禁止" },
    { label: "首夜遗言", value: rules.first_night_last_words ? "开启" : "关闭" },
    { label: "警长系统", value: rules.sheriff_enabled ? `开启 x${rules.sheriff_vote_multiplier}` : "关闭" },
    { label: "白狼王自爆", value: rules.white_wolf_explode_during_day ? "白天可爆" : "禁用" },
    { label: "白狼王结束白天", value: rules.white_wolf_explode_ends_day ? "结束" : "继续" },
    { label: "骑士决斗后结束讨论", value: rules.knight_duel_ends_discussion ? "是" : "否" },
  ];
}

export function getThoughtPhaseMeta(phase: string) {
  const labels: Record<string, { label: string; color: string }> = {
    discuss: { label: "白天讨论", color: "#71d2b8" },
    vote: { label: "投票决策", color: "#eba65f" },
    last_words: { label: "遗言", color: "#f2bc63" },
    sheriff_nomination: { label: "警长竞选", color: "#f2bc63" },
    sheriff_vote: { label: "警长投票", color: "#eba65f" },
    sheriff_tiebreak: { label: "警长归票", color: "#eba65f" },
    sheriff_transfer: { label: "警徽移交", color: "#f2bc63" },
    sheriff_campaign: { label: "竞选发言", color: "#f2bc63" },
    sheriff_runoff: { label: "警长PK发言", color: "#f09a5f" },
    night_werewolf: { label: "狼人决策", color: "#8695ff" },
    night_wolf_beauty: { label: "狼美人行动", color: "#ff7d97" },
    night_stone_gargoyle: { label: "石像鬼查验", color: "#8f97ff" },
    night_seer: { label: "预言家行动", color: "#67b8ff" },
    night_witch: { label: "女巫行动", color: "#ce8dff" },
    night_guard: { label: "守卫行动", color: "#59d49b" },
    night_silencer: { label: "禁言长老行动", color: "#4bd1c1" },
    night_gravekeeper: { label: "守墓人情报", color: "#d0d7d5" },
    hunter_revenge: { label: "猎人开枪", color: "#ff8f71" },
    werewolf_self_destruct: { label: "狼人自爆", color: "#ff6b57" },
    white_wolf_self_destruct: { label: "白狼王自爆", color: "#ff9d5c" },
    wolf_king_revenge: { label: "狼王开枪", color: "#ffbf67" },
    knight_duel: { label: "骑士决斗", color: "#67d5f2" },
  };

  return labels[phase] || { label: phase, color: "#d7dedc" };
}

export function getWinnerLabel(winner: "village" | "werewolf" | null) {
  if (winner === "village") {
    return "好人阵营";
  }
  if (winner === "werewolf") {
    return "狼人阵营";
  }
  return "未决出";
}
