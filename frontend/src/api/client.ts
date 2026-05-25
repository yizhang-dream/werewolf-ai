import type {
  AgentDetail,
  AgentInfo,
  CreateGamePayload,
  GameCreationResponse,
  GameState,
  GameTemplate,
  HealthStatus,
  ProviderInfo,
  ProviderPayload,
  QuickStartResponse,
} from "../types/game";

const BASE = "/api";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers = new Headers(opts?.headers);
  if (opts?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  health: () => request<HealthStatus>("/health"),

  // Game
  createGame: (data: CreateGamePayload) =>
    request<GameCreationResponse>("/games", { method: "POST", body: JSON.stringify(data) }),
  getGame: (id: string) => request<GameState>(`/games/${id}`),
  getGameFull: (id: string) => request<GameState>(`/games/${id}/full`),
  startGame: (id: string) => request<{ status: string }>(`/games/${id}/start`, { method: "POST" }),
  listGames: () => request<Array<{ game_id: string; winner: string | null; finished_at: string | null; created_at: string | null; player_count: number; round_number: number }>>("/games"),
  getGameLog: (id: string) => request<GameState>(`/games/${id}/log`),
  listTemplates: () => request<GameTemplate[]>("/games/templates/list"),
  quickStart: (templateId: string) =>
    request<QuickStartResponse>(
      `/games/templates/quick-start?template_id=${encodeURIComponent(templateId)}`,
      { method: "POST" }
    ),

  // Settings
  listProviders: () => request<{ providers: ProviderInfo[]; default_provider: string }>("/settings/providers"),
  setDefaultProvider: (name: string) =>
    request<{ ok: boolean; default_provider: string }>("/settings/default-provider", { method: "POST", body: JSON.stringify({ default_provider: name }) }),
  saveProvider: (data: ProviderPayload) =>
    request<{ ok: boolean }>("/settings/providers", { method: "POST", body: JSON.stringify(data) }),
  deleteProvider: (name: string) => request<{ ok: boolean }>(`/settings/providers/${name}`, { method: "DELETE" }),
  importCcSwitch: () => request<{ ok: boolean; imported: number }>("/settings/import-ccswitch", { method: "POST" }),

  // Agents
  listAgents: () => request<AgentInfo[]>("/agents"),
  getAgent: (name: string) => request<AgentDetail>(`/agents/${name}`),
  resetAgent: (name: string) => request<{ ok: boolean }>(`/agents/${name}`, { method: "DELETE" }),
};
