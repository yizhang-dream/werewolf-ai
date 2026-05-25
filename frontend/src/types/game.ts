export type Phase =
  | "setup"
  | "night"
  | "day_announce"
  | "day_discuss"
  | "day_vote"
  | "hunter_revenge"
  | "game_over";

export type Winner = "village" | "werewolf" | null;
export type WinRule = "slaughter_side" | "total_elimination" | "parity";
export type WitchSelfSaveRule = "never" | "first_night_only" | "always";

export type RoleId =
  | "werewolf"
  | "wolf_beauty"
  | "white_wolf"
  | "hidden_wolf"
  | "wolf_king"
  | "evil_spirit_knight"
  | "stone_gargoyle"
  | "seer"
  | "witch"
  | "hunter"
  | "guard"
  | "knight"
  | "idiot"
  | "silencer"
  | "gravekeeper"
  | "villager";

export interface GameRules {
  win_rule: WinRule;
  witch_self_save_rule: WitchSelfSaveRule;
  same_guard_save_survives: boolean;
  guard_can_self_protect: boolean;
  first_night_last_words: boolean;
  sheriff_enabled: boolean;
  sheriff_vote_multiplier: number;
  white_wolf_explode_during_day: boolean;
  white_wolf_explode_ends_day: boolean;
  knight_duel_ends_discussion: boolean;
}

export interface Player {
  name: string;
  role?: RoleId;
  status: "alive" | "dead";
  personality: string;
  llm_provider: string;
  model_name: string;
  vote_right?: boolean;
}

export interface SpeechRecord {
  speaker: string;
  inner_thought: string;
  public_speech: string;
  round_number: number;
  phase: string;
  skill_info?: string;
}

export interface WolfChatRecord {
  speaker: string;
  message: string;
  round_number: number;
  kill_target?: string | null;
  visible_to?: string[];
}

export interface GameState {
  game_id: string;
  players: Player[];
  phase: Phase;
  round_number: number;
  night_kills: string[];
  day_eliminated: string | null;
  winner: Winner;
  speeches: SpeechRecord[];
  wolf_chat?: WolfChatRecord[];
  gm_announcement: string;
  auto_advance: boolean;
  step_delay: number;
  rules: GameRules;
  sheriff_name?: string | null;
  agent_notes?: Record<string, string[]>;
  history?: Array<Record<string, unknown>>;
  created_at?: string;
  finished_at?: string | null;
  sheriff_election_completed?: boolean;
}

export interface GameTemplate {
  id: string;
  name: string;
  description: string;
  roles: RoleId[];
  rules: GameRules;
}

export interface PlayerConfig {
  name: string;
  personality: string;
  llm_provider: string;
  model_name: string;
}

export interface CreateGamePayload {
  players: PlayerConfig[];
  roles: RoleId[];
  auto_advance: boolean;
  step_delay?: number;
  rules?: GameRules;
}

export interface GameCreationResponse {
  game_id: string;
  players: Player[];
  rules: GameRules;
}

export interface QuickStartResponse extends GameCreationResponse {
  template: string;
}

export interface ProviderInfo {
  name: string;
  provider_type: string;
  base_url: string;
  models: string[];
  has_key: boolean;
}

export interface HealthStatus {
  status: string;
}

export interface ProviderPayload {
  name: string;
  provider_type: string;
  api_key?: string;
  base_url?: string;
  models: string[];
}

export interface AgentInfo {
  name: string;
  personality: string;
  total_games: number;
  wins: number;
  losses: number;
  strategies: string[];
  lesson_count: number;
  last_game_id?: string;
  last_role?: string;
  last_won?: boolean | null;
  last_rounds_played?: number;
  last_reflection?: string;
}

export interface AgentLesson {
  game_id: string;
  role: string;
  won: boolean;
  reflection: string;
  key_moments: string[];
  player_count: number;
  role_config: string;
  rounds_played: number;
  survived_to_end: boolean;
  final_status: string;
  winner: string;
  useful_takeaways: string[];
}

export interface RoleMemorySummary {
  role: string;
  total_games: number;
  wins: number;
  losses: number;
  strengths: string[];
  pitfalls: string[];
  signals_to_watch: string[];
  role_tips: string[];
  recent_examples: string[];
  last_updated_game_id: string;
}

export interface AgentDetail {
  agent_name: string;
  personality: string;
  total_games: number;
  wins: number;
  losses: number;
  strategies: string[];
  lessons: AgentLesson[];
  role_summaries: Record<string, RoleMemorySummary>;
  memory_version: number;
}

export interface PhaseChangeEventData {
  phase: Phase;
  round?: number;
  message?: string;
  winner?: Winner;
}

export interface SpeechEventData {
  speaker: string;
  public_speech: string;
  inner_thought: string;
  round: number;
  phase?: string;
}

export interface GMAnnouncementEventData {
  message: string;
  deaths: string[];
}

export interface DeathEventData {
  player: string;
  cause: string;
  role?: string;
  message?: string;
}

export interface VoteCastEventData {
  voter: string;
  target: string;
  context?: string;
  round?: number;
}

export interface SeatingEventData {
  order: string[];
}

export interface VoteResultEventData {
  message: string;
}

export interface NightActionEventData {
  role: string;
  player?: string;
  message: string;
}

export interface SheriffUpdateEventData {
  sheriff: string | null;
  previous?: string | null;
  reason: string;
  message: string;
}

export interface GameOverEventData {
  winner: Winner;
}

export interface AgentNotesUpdateEventData {
  agent_notes: Record<string, string[]>;
}

export interface WolfChatEventData extends WolfChatRecord {}

export type SSEEventData =
  | PhaseChangeEventData
  | SpeechEventData
  | GMAnnouncementEventData
  | DeathEventData
  | VoteCastEventData
  | SeatingEventData
  | VoteResultEventData
  | NightActionEventData
  | SheriffUpdateEventData
  | GameOverEventData
  | AgentNotesUpdateEventData
  | WolfChatEventData
  | Record<string, unknown>;

export interface SSEEvent<T = SSEEventData> {
  event: string;
  data: T;
}
