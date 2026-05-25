import { create } from "zustand";
import type {
  GameState,
  GMAnnouncementEventData,
  PhaseChangeEventData,
  SeatingEventData,
  SheriffUpdateEventData,
  SpeechEventData,
  SpeechRecord,
  SSEEvent,
  WolfChatRecord,
  Winner,
} from "../types/game";

interface GameStore {
  events: SSEEvent[];
  phase: string;
  roundNumber: number;
  winner: Winner;
  gmAnnouncement: string;
  sheriffName: string | null;
  speeches: SpeechRecord[];
  wolfChat: WolfChatRecord[];
  deaths: string[];
  seating: string[];
  connected: boolean;
  connectionError: string | null;
  replayMode: boolean;

  addEvent: (event: SSEEvent) => void;
  mergeSpeeches: (serverSpeeches: SpeechRecord[]) => void;
  mergeWolfChat: (serverWolfChat: WolfChatRecord[]) => void;
  setSheriffName: (name: string | null) => void;
  setConnected: (connected: boolean) => void;
  setConnectionError: (message: string | null) => void;
  rebuildEvents: (log: GameState) => void;
  loadReplay: (log: GameState) => void;
  reset: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  events: [],
  seating: [],
  phase: "setup",
  roundNumber: 0,
  winner: null,
  gmAnnouncement: "",
  sheriffName: null,
  speeches: [],
  wolfChat: [],
  deaths: [],
  connected: false,
  connectionError: null,
  replayMode: false,

  rebuildEvents: (log: GameState) =>
    set((state) => {
      const history = (log as any).history as Array<Record<string, unknown>> | undefined;

      type TimedEvent = { round: number; seq: number; build: () => SSEEvent | SSEEvent[] };
      const timed: TimedEvent[] = [];
      const nightPhases = new Set(["night_werewolf", "night_witch", "night_seer", "night_guard", "night_wolf_beauty", "night_stone_gargoyle", "night_silencer", "night_gravekeeper", "night_hidden_wolf"]);

      // Speeches
      (log.speeches ?? []).forEach((s, i) => {
        const r = s.round_number;
        if (nightPhases.has(s.phase)) {
          const label = s.phase === "night_werewolf" ? "狼人夜刀" : s.phase === "night_witch" ? "女巫用药" : s.phase === "night_seer" ? "预言家查验" : s.phase === "night_guard" ? "守卫守护" : "夜间行动";
          const detail = s.skill_info || (s.inner_thought ? s.inner_thought.slice(0, 80) : "");
          timed.push({ round: r, seq: i, build: () => ({ event: "night_action", data: { message: `${label}：${s.speaker}${detail ? ` — ${detail}` : ""}` } }) });
        } else if (s.public_speech) {
          timed.push({ round: r, seq: i, build: () => ({ event: "speech", data: { speaker: s.speaker, inner_thought: s.inner_thought ?? "", public_speech: s.public_speech, round: r, phase: s.phase } }) });
        }
      });

      // Pre-compute: max speech seq per round
      const maxSpeechSeqByRound2: Record<number, number> = {};
      for (const t of timed) {
        if (t.round > 0 && t.seq > (maxSpeechSeqByRound2[t.round] ?? -1)) {
          maxSpeechSeqByRound2[t.round] = t.seq;
        }
      }

      // History events — place after the last speech of the same round
      (history ?? []).forEach((h, i) => {
        const r = (h.round as number) ?? 0;
        const base = maxSpeechSeqByRound2[r] ?? -1;
        const seq = base + 1 + i;
        if (h.type === "death") {
          const dh = h as any;
          timed.push({ round: r, seq, build: () => ({ event: "death", data: { player: dh.player, cause: dh.phase ?? "unknown", role: dh.role, message: `${dh.player} 死亡` } }) });
        } else if (h.type === "sheriff_election") {
          const se = h as any;
          timed.push({ round: r, seq, build: () => {
            const result: SSEEvent[] = [{ event: "vote_result", data: { message: `警长竞选，当选：${se.winner || "无"}` } }];
            for (const v of (se.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "sheriff" } });
            return result;
          }});
        } else if (h.type === "day_vote") {
          const dv = h as any;
          timed.push({ round: r, seq, build: () => {
            const result: SSEEvent[] = [];
            for (const v of (dv.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "exile" } });
            for (const vr of (dv.vote_rounds ?? [])) {
              for (const v of (vr.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "exile_pk" } });
            }
            const eliminated = dv.eliminated ? `，放逐 ${dv.eliminated}` : "";
            result.push({ event: "vote_result", data: { message: `投票${eliminated}` } });
            return result;
          }});
        }
      });

      timed.sort((a, b) => a.round - b.round || a.seq - b.seq);

      const events: SSEEvent[] = [{ event: "phase_change", data: { phase: log.phase, round: log.round_number, message: "" } }];
      for (const t of timed) {
        const built = t.build();
        if (Array.isArray(built)) events.push(...built);
        else events.push(built);
      }

      if (log.winner) {
        events.push({ event: "game_over", data: { winner: log.winner } });
      }

      // Keep events that are newer than what we rebuilt
      const rebuiltIds = new Set(events.map((e) => JSON.stringify(e)));
      const newerEvents = state.events.filter((e) => !rebuiltIds.has(JSON.stringify(e)));

      return {
        events: [...events, ...newerEvents],
        phase: log.phase,
        roundNumber: log.round_number ?? 0,
        winner: log.winner ?? null,
        gmAnnouncement: log.gm_announcement ?? "",
        sheriffName: log.sheriff_name ?? null,
        deaths: (log.history ?? []).filter((h: any) => h.type === "death").map((h: any) => h.player as string),
        seating: log.players?.map((p) => p.name) ?? state.seating,
      };
    }),

  loadReplay: (log) =>
    set(() => {
      const deaths: string[] = [];
      const history = (log as any).history as Array<Record<string, unknown>> | undefined;
      const seating = log.players?.map((p) => p.name) ?? [];

      // Build sorted events: speeches (by array order) + history events (by array order),
      // each tagged with round and a sequence index, then sort chronologically.
      type TimedEvent = { round: number; seq: number; build: () => SSEEvent | SSEEvent[] };
      const timed: TimedEvent[] = [];

      const nightPhases = new Set(["night_werewolf", "night_witch", "night_seer", "night_guard", "night_wolf_beauty", "night_stone_gargoyle", "night_silencer", "night_gravekeeper", "night_hidden_wolf"]);

      // Speeches
      (log.speeches ?? []).forEach((s, i) => {
        const r = s.round_number;
        if (nightPhases.has(s.phase)) {
          const label = s.phase === "night_werewolf" ? "狼人夜刀" : s.phase === "night_witch" ? "女巫用药" : s.phase === "night_seer" ? "预言家查验" : s.phase === "night_guard" ? "守卫守护" : "夜间行动";
          const detail = s.skill_info || (s.inner_thought ? s.inner_thought.slice(0, 80) : "");
          timed.push({ round: r, seq: i, build: () => ({ event: "night_action", data: { message: `${label}：${s.speaker}${detail ? ` — ${detail}` : ""}` } }) });
        } else if (s.public_speech) {
          timed.push({ round: r, seq: i, build: () => ({ event: "speech", data: { speaker: s.speaker, inner_thought: s.inner_thought ?? "", public_speech: s.public_speech, round: r, phase: s.phase } }) });
        }
      });

      // Pre-compute: for each round, find the max seq among speeches
      const maxSpeechSeqByRound: Record<number, number> = {};
      for (const t of timed) {
        if (t.round > 0 && t.seq > (maxSpeechSeqByRound[t.round] ?? -1)) {
          maxSpeechSeqByRound[t.round] = t.seq;
        }
      }

      // History events — place after the last speech of the same round
      (history ?? []).forEach((h, i) => {
        const r = (h.round as number) ?? 0;
        const base = maxSpeechSeqByRound[r] ?? -1;
        const seq = base + 1 + i; // right after the last speech of this round
        if (h.type === "death") {
          const dh = h as any;
          deaths.push(dh.player as string);
          const roleStr = dh.role ? `（${dh.role}）` : "";
          timed.push({ round: r, seq, build: () => ({ event: "death", data: { player: dh.player, cause: dh.phase ?? "unknown", role: dh.role, message: `${dh.player}${roleStr} 死亡` } }) });
        } else if (h.type === "sheriff_election") {
          const se = h as any;
          timed.push({ round: r, seq, build: () => {
            const result: SSEEvent[] = [{ event: "vote_result", data: { message: `警长竞选，当选：${se.winner || "无"}` } }];
            for (const v of (se.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "sheriff" } });
            return result;
          }});
        } else if (h.type === "day_vote") {
          const dv = h as any;
          timed.push({ round: r, seq, build: () => {
            const result: SSEEvent[] = [];
            for (const v of (dv.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "exile" } });
            for (const vr of (dv.vote_rounds ?? [])) {
              for (const v of (vr.votes ?? [])) result.push({ event: "vote_cast", data: { voter: v.voter, target: v.target, context: "exile_pk" } });
            }
            const eliminated = dv.eliminated ? `，放逐 ${dv.eliminated}` : "";
            result.push({ event: "vote_result", data: { message: `投票${eliminated}` } });
            return result;
          }});
        } else if (h.type === "seer_check") {
          const sc = h as any;
          timed.push({ round: r, seq, build: () => ({ event: "night_action", data: { message: `预言家查验：${sc.player} 验 ${sc.target} → ${sc.is_wolf ? "狼人" : "好人"}` } }) });
        }
      });

      // Sort: by round, then by seq
      timed.sort((a, b) => a.round - b.round || a.seq - b.seq);

      // Flatten
      const events: SSEEvent[] = [{ event: "phase_change", data: { phase: "setup", round: log.round_number, message: "" } }];
      for (const t of timed) {
        const built = t.build();
        if (Array.isArray(built)) events.push(...built);
        else events.push(built);
      }

      if (log.winner) {
        events.push({ event: "game_over", data: { winner: log.winner } });
      }

      return {
        events,
        phase: "game_over",
        roundNumber: log.round_number ?? 0,
        winner: log.winner ?? null,
        gmAnnouncement: "",
        sheriffName: log.sheriff_name ?? null,
        speeches: log.speeches ?? [],
        wolfChat: log.wolf_chat ?? [],
        deaths,
        seating,
        connected: false,
        connectionError: null,
        replayMode: true,
      };
    }),

  addEvent: (event) =>
    set((state) => {
      const updates: Partial<GameStore> = { events: [...state.events, event] };
      const d = event.data;

      switch (event.event) {
        case "phase_change": {
          const data = d as PhaseChangeEventData;
          updates.phase = data.phase;
          if (typeof data.round === "number") {
            updates.roundNumber = data.round;
          }
          break;
        }
        case "gm_announcement": {
          const data = d as GMAnnouncementEventData;
          updates.gmAnnouncement = data.message;
          break;
        }
        case "sheriff_update": {
          const data = d as SheriffUpdateEventData;
          updates.sheriffName = data.sheriff;
          break;
        }
        case "speech": {
          const data = d as SpeechEventData;
          updates.speeches = [
            ...state.speeches,
            {
              speaker: data.speaker,
              inner_thought: data.inner_thought,
              public_speech: data.public_speech,
              round_number: data.round,
              phase: data.phase ?? (state.phase === "day_discuss" ? "discuss" : state.phase),
            },
          ];
          break;
        }
        case "wolf_chat": {
          const data = d as WolfChatRecord;
          updates.wolfChat = [...state.wolfChat, data];
          break;
        }
        case "death":
          updates.deaths = [...state.deaths, String((d as { player: string }).player)];
          break;
        case "game_over":
          updates.winner = (d as { winner: Winner }).winner;
          break;
        case "seating":
          updates.seating = (d as SeatingEventData).order;
          break;
      }

      return updates;
    }),

  mergeSpeeches: (serverSpeeches) =>
    set((state) => {
      const existingKeys = new Set(
        state.speeches.map((s) => `${s.speaker}|${s.round_number}|${s.phase}|${s.public_speech}|${s.skill_info ?? ""}`)
      );
      const newOnes = serverSpeeches.filter(
        (s) => !existingKeys.has(`${s.speaker}|${s.round_number}|${s.phase}|${s.public_speech}|${s.skill_info ?? ""}`)
      );
      if (newOnes.length === 0) return {};
      return { speeches: [...state.speeches, ...newOnes] };
    }),

  mergeWolfChat: (serverWolfChat) =>
    set((state) => {
      const existingKeys = new Set(
        state.wolfChat.map((item) => `${item.speaker}|${item.round_number}|${item.kill_target ?? ""}|${item.message}`)
      );
      const newOnes = serverWolfChat.filter(
        (item) => !existingKeys.has(`${item.speaker}|${item.round_number}|${item.kill_target ?? ""}|${item.message}`)
      );
      if (newOnes.length === 0) return {};
      return { wolfChat: [...state.wolfChat, ...newOnes] };
    }),

  setSheriffName: (sheriffName) => set({ sheriffName }),
  setConnected: (connected) => set({ connected }),
  setConnectionError: (connectionError) => set({ connectionError }),
  reset: () =>
    set({
      events: [],
      phase: "setup",
      roundNumber: 0,
      winner: null,
      gmAnnouncement: "",
      sheriffName: null,
      speeches: [],
      wolfChat: [],
      deaths: [],
      seating: [],
      connected: false,
      connectionError: null,
      replayMode: false,
    }),
}));
