import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useParams } from "react-router-dom";

import { api } from "../../api/client";
import { PHASE_META, ROLE_META, countRoles, describeRules, getThoughtPhaseMeta, getWinnerLabel } from "../../lib/gameUi";
import { useSSE } from "../../hooks/useSSE";
import { useGameStore } from "../../store/gameStore";
import type {
  AgentNotesUpdateEventData,
  DeathEventData,
  GameState,
  GMAnnouncementEventData,
  NightActionEventData,
  Phase,
  PhaseChangeEventData,
  SeatingEventData,
  SheriffUpdateEventData,
  SpeechRecord,
  SSEEvent,
  VoteCastEventData,
  VoteResultEventData,
  WolfChatRecord,
} from "../../types/game";

const WOLF_ROLE_IDS = new Set([
  "werewolf",
  "wolf_beauty",
  "white_wolf",
  "hidden_wolf",
  "wolf_king",
  "evil_spirit_knight",
  "stone_gargoyle",
]);

export default function GameBoard() {
  const { gameId } = useParams<{ gameId: string }>();
  const location = useLocation();
  const isReplay = location.pathname.startsWith("/replay/");
  const [game, setGame] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(true);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null);
  const [showRulesPanel, setShowRulesPanel] = useState(false);
  const [showSnapshotPanel, setShowSnapshotPanel] = useState(false);
  const [topExpanded, setTopExpanded] = useState(false);
  const [thoughtMode, setThoughtMode] = useState<"focus" | "all">("focus");
  const publicLogRef = useRef<HTMLDivElement>(null);
  const thoughtLogRef = useRef<HTMLDivElement>(null);

  const phase = useGameStore((state) => state.phase);
  const roundNumber = useGameStore((state) => state.roundNumber);
  const winner = useGameStore((state) => state.winner);
  const gmAnnouncement = useGameStore((state) => state.gmAnnouncement);
  const sheriffName = useGameStore((state) => state.sheriffName);
  const speeches = useGameStore((state) => state.speeches);
  const wolfChat = useGameStore((state) => state.wolfChat);
  const events = useGameStore((state) => state.events);
  const seating = useGameStore((state) => state.seating);
  const connected = useGameStore((state) => state.connected);
  const connectionError = useGameStore((state) => state.connectionError);
  const replayMode = useGameStore((state) => state.replayMode);
  const mergeSpeeches = useGameStore((state) => state.mergeSpeeches);
  const mergeWolfChat = useGameStore((state) => state.mergeWolfChat);
  const setSheriffName = useGameStore((state) => state.setSheriffName);
  const loadReplay = useGameStore((state) => state.loadReplay);
  const rebuildEvents = useGameStore((state) => state.rebuildEvents);

  // Replay mode: never use SSE. Load full log once, then poll for in-progress games.
  useSSE(isReplay ? undefined : gameId);

  // Replay mode: load saved game log and inject into store
  useEffect(() => {
    if (!isReplay || !gameId) return;
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const log = await api.getGameLog(gameId!);
        if (!active) return;
        loadReplay(log);
        setGame(log);
        setStarted(true);
        if (log.players?.length > 0) {
          setSelectedPlayer(log.players[0].name);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "加载回放失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [isReplay, gameId]);

  // Replay mode: manual refresh for in-progress games
  async function refreshReplay() {
    if (!gameId) return;
    try {
      const updated = await api.getGameLog(gameId);
      rebuildEvents(updated);
      setGame(updated);
    } catch { /* ignore */ }
  }

  useEffect(() => {
    const latestEvent = events[events.length - 1];
    if (latestEvent?.event !== "agent_notes_update") {
      return;
    }

    const data = latestEvent.data as AgentNotesUpdateEventData;
    setGame((current) => (current ? { ...current, agent_notes: data.agent_notes } : current));
  }, [events]);

  useEffect(() => {
    if (isReplay) return;
    void refreshSnapshot(true);
  }, [gameId, isReplay]);

  useEffect(() => {
    if (isReplay || !gameId || phase === "setup" || !started) {
      return;
    }
    void refreshSnapshot();
  }, [gameId, phase, roundNumber, started, isReplay]);

  useEffect(() => {
    if (isReplay || !gameId || !winner) {
      return;
    }
    void refreshSnapshot();
  }, [gameId, winner, isReplay]);

  useEffect(() => {
    if (publicLogRef.current) {
      publicLogRef.current.scrollTop = publicLogRef.current.scrollHeight;
    }
  }, [events]);

  useEffect(() => {
    if (thoughtLogRef.current) {
      thoughtLogRef.current.scrollTop = thoughtLogRef.current.scrollHeight;
    }
  }, [speeches]);

  async function refreshSnapshot(initial = false) {
    if (!gameId) {
      return;
    }

    if (initial) {
      setLoading(true);
      setError(null);
    }

    try {
      const result = await api.getGameFull(gameId);
      setGame(result);
      mergeSpeeches(result.speeches ?? []);
      mergeWolfChat(result.wolf_chat ?? []);
      setSheriffName(result.sheriff_name ?? null);
      setStarted(result.phase !== "setup");
      if (initial) {
        rebuildEvents(result);
      }
      if (!selectedPlayer && result.players.length > 0) {
        setSelectedPlayer(result.players[0].name);
      }
    } catch (err) {
      if (initial) {
        setError(err instanceof Error ? err.message : "加载对局失败");
      }
    } finally {
      if (initial) {
        setLoading(false);
      }
    }
  }

  async function handleStart() {
    if (!gameId) {
      return;
    }
    await api.startGame(gameId);
    setStarted(true);
  }

  const players = game?.players ?? [];
  const currentPhase = (phase || game?.phase || "setup") as Phase;
  const currentRound = roundNumber || game?.round_number || 0;
  const alivePlayers = players.filter((player) => player.status === "alive");
  const seatOrder = seating.length > 0 ? seating : players.map((player) => player.name);
  const gameOver = currentPhase === "game_over" || Boolean(winner) || Boolean(game?.winner);
  const currentWinner = winner || game?.winner || null;
  const winnerLabel = getWinnerLabel(currentWinner);
  const phaseMeta = PHASE_META[currentPhase];
  const currentSheriff = sheriffName || game?.sheriff_name || null;
  const rules = game?.rules;
  const roleBreakdown = countRoles(players.map((player) => player.role).filter(Boolean) as Array<NonNullable<(typeof players)[number]["role"]>>);
  const thoughtFeed = useMemo(() => [...speeches].sort((left, right) => left.round_number - right.round_number), [speeches]);
  const thoughtsByPlayer = useMemo(() => {
    const grouped: Record<string, SpeechRecord[]> = {};
    for (const speech of speeches) {
      grouped[speech.speaker] ??= [];
      grouped[speech.speaker].push(speech);
    }
    return grouped;
  }, [speeches]);
  const selectedThoughts = selectedPlayer ? thoughtsByPlayer[selectedPlayer] ?? [] : [];
  const deathNames = players.filter((player) => player.status === "dead").map((player) => player.name);
  const selectedPlayerInfo = players.find((player) => player.name === selectedPlayer) ?? null;
  const selectedRoleMeta = selectedPlayerInfo?.role ? ROLE_META[selectedPlayerInfo.role] : null;
  const selectedAgentNotes = selectedPlayer ? [...(game?.agent_notes?.[selectedPlayer] ?? [])].reverse() : [];
  const selectedIsWolf = Boolean(selectedPlayerInfo?.role && WOLF_ROLE_IDS.has(selectedPlayerInfo.role));
  const selectedWolfChat = selectedPlayer
    ? wolfChat.filter((item) => item.speaker === selectedPlayer || item.visible_to?.includes(selectedPlayer))
    : [];
  const shortGameId = gameId && gameId.length > 15 ? `${gameId.slice(0, 8)}...${gameId.slice(-4)}` : gameId || "未命名";

  if (loading) {
    return <div className="empty-state">正在加载对局...</div>;
  }

  if (error) {
    return <div className="alert-banner">{error}</div>;
  }

  return (
    <div className="page-stack">
      <section className="board-toolbar">
        <div className="board-toolbar-main">
          <span className="mini-chip board-toolbar-chip">Live Match</span>
          <div className="board-toolbar-copy">
            <h2 className="board-toolbar-heading">对局控制台</h2>
            <span className="board-toolbar-id" title={gameId || "未命名"}>
              {shortGameId}
            </span>
          </div>
        </div>
        <div className="hero-actions">
          <span className="page-badge" style={{ color: phaseMeta.color, background: phaseMeta.tone }}>
            {phaseMeta.label}
          </span>
          <button className="action-secondary" onClick={() => void refreshSnapshot()}>
            刷新快照
          </button>
          {!started && !gameOver && (
            <button className="action-primary" onClick={() => void handleStart()}>
              开始游戏
            </button>
          )}
        </div>
      </section>

      <section
        className={`top-collapsible-rail${topExpanded ? " expanded" : ""}`}
        onMouseEnter={() => setTopExpanded(true)}
        onMouseLeave={() => setTopExpanded(false)}
        onFocus={() => setTopExpanded(true)}
        onBlur={(event) => {
          const nextTarget = event.relatedTarget;
          if (!nextTarget || !event.currentTarget.contains(nextTarget as Node)) {
            setTopExpanded(false);
          }
        }}
      >
        <button type="button" className="top-collapsible-trigger" aria-label="本局信息" aria-expanded={topExpanded}>
          <span className="mini-chip top-collapsible-chip">局</span>
        </button>

        <div className="top-collapsible-panel">
          <div className="section-card top-collapsible-card">
            <div className="section-headline">
              <div>
                <h4 className="section-title">本局概况</h4>
                <p className="section-copy">座位图、状态概览和当前聚焦合并在一起，展开后直接展示全部信息。</p>
              </div>
              <div className="cluster">
                <button className="action-secondary" type="button" onClick={() => setShowRulesPanel((value) => !value)}>
                  {showRulesPanel ? "收起规则" : "展开规则"}
                </button>
                <button className="action-secondary" type="button" onClick={() => setShowSnapshotPanel((value) => !value)}>
                  {showSnapshotPanel ? "收起快照" : "展开快照"}
                </button>
              </div>
            </div>

            <div className="board-overview-grid" style={{ marginTop: 16 }}>
              <div className="command-deck">
                <div className="command-deck-topbar">
                  <div className="command-deck-heading">
                    <div className="field-label">对局概况</div>
                    <div className="command-deck-subline">
                      <span className="board-id-pill" title={gameId || "未命名"}>
                        {shortGameId}
                      </span>
                      <span className="mini-chip" style={{ color: phaseMeta.color, borderColor: `${phaseMeta.color}55` }}>
                        {phaseMeta.label}
                      </span>
                      <span className="mini-chip" style={{ color: connected ? "#73d0c1" : "#f2bf6d" }}>
                        {connected ? "SSE 在线" : "SSE 等待"}
                      </span>
                    </div>
                  </div>

                  <div className="chip-row">
                    {currentSheriff && (
                      <span className="mini-chip" style={{ color: "#f2bf6d" }}>
                        警长 {currentSheriff}
                      </span>
                    )}
                    <span className="mini-chip" style={{ color: "#73d0c1" }}>
                      存活 {alivePlayers.length}/{players.length}
                    </span>
                  </div>
                </div>

                <div className="command-deck-grid">
                  <div className="seat-ring-wrap">
                    <div className="seat-ring">
                      <div className="seat-ring-core">
                        <div style={{ fontWeight: 800, fontSize: 18 }}>Round {currentRound || 0}</div>
                        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>{phaseMeta.label}</div>
                        <div className="seat-ring-core-status">
                          <span style={{ color: "#73d0c1" }}>存活 {alivePlayers.length}</span>
                          <span style={{ color: "#ff8f72" }}>出局 {deathNames.length}</span>
                        </div>
                      </div>
                      {seatOrder.map((name, index) => {
                        const player = players.find((item) => item.name === name);
                        if (!player) {
                          return null;
                        }

                        const roleMeta = player.role ? ROLE_META[player.role] : null;
                        const selected = selectedPlayer === player.name;
                        const dead = player.status === "dead";
                        const angle = (Math.PI * 2 * index) / Math.max(seatOrder.length, 1) - Math.PI / 2;
                        const radius = 196;
                        const x = Math.cos(angle) * radius;
                        const y = Math.sin(angle) * radius;

                        return (
                          <button
                            key={name}
                            className={`seat-orbit-node${selected ? " active" : ""}${dead ? " dead" : ""}`}
                            onClick={() => setSelectedPlayer(player.name)}
                            style={{
                              left: `calc(50% + ${x}px)`,
                              top: `calc(50% + ${y}px)`,
                              borderColor: selected ? roleMeta?.color || "#dfb3ff" : `${roleMeta?.color || "#ffffff"}33`,
                              background: roleMeta?.bg || "rgba(255,255,255,0.04)",
                            }}
                          >
                            {dead && <span className="seat-death-badge">出局</span>}
                            <div className="seat-orbit-index">{index + 1}</div>
                            <div className="seat-orbit-name">{player.name}</div>
                            <div className="seat-orbit-role" style={{ color: roleMeta?.color || "#c8d3cf" }}>
                              {roleMeta?.label || "未知"}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="overview-stack">
                    <div className="compact-kpi-grid">
                      <KpiCard
                        label="当前轮次"
                        value={currentRound > 0 ? `第 ${currentRound} 轮` : "未开始"}
                        detail={currentSheriff ? `警长：${currentSheriff}` : "当前暂无警长"}
                        tone="#73d0c1"
                      />
                      <KpiCard
                        label="胜负状态"
                        value={gameOver ? winnerLabel : "进行中"}
                        detail={gameOver ? "身份已揭晓，可结合时间线复盘。" : `存活 ${alivePlayers.length} / ${players.length} 人`}
                        tone={gameOver ? "#dfb3ff" : "#eef4f1"}
                      />
                      <KpiCard
                        label={replayMode ? "回放模式" : "实时连接"}
                        value={replayMode ? (gameOver ? "已结束" : "进行中") : connected ? "稳定" : "待连接"}
                        detail={replayMode ? (gameOver ? "正在查看已结束的对局复盘。" : "点击「刷新回放」按钮获取最新状态。") : connected ? "事件流正在实时推送中。" : connectionError || "如果长时间断开，请检查 SSE 服务。"}
                        tone={replayMode ? (gameOver ? "#dfb3ff" : "#73d0c1") : connected ? "#73d0c1" : "#f2bf6d"}
                      />
                      <KpiCard
                        label="淘汰情况"
                        value={deathNames.length ? `${deathNames.length} 人` : "0 人"}
                        detail={deathNames.length ? deathNames.join("、") : "暂时无人出局"}
                        tone="#ff8f72"
                      />
                    </div>

                    {replayMode && !gameOver && (
                      <div style={{ marginTop: 12 }}>
                        <button
                          className="action-secondary"
                          onClick={() => void refreshReplay()}
                          style={{ fontSize: 13, padding: "6px 16px" }}
                        >
                          刷新回放
                        </button>
                      </div>
                    )}
                    <div className="chip-row overview-role-row">
                      {roleBreakdown.map((role) => (
                        <span key={role.id} className="role-chip" style={{ color: role.color, borderColor: `${role.color}55` }}>
                          {role.label} x {role.count}
                        </span>
                      ))}
                    </div>

                    {selectedPlayerInfo && (
                      <div
                        className="focus-summary-card"
                        style={{
                          borderColor: `${selectedRoleMeta?.color || "#dfb3ff"}55`,
                          background: selectedRoleMeta?.bg || "rgba(255,255,255,0.04)",
                          opacity: selectedPlayerInfo.status === "dead" ? 0.72 : 1,
                        }}
                      >
                        <div className="field-label">当前聚焦</div>
                        <div className="split-inline" style={{ alignItems: "flex-start", marginTop: 10 }}>
                          <div>
                            <div className="focus-summary-name">{selectedPlayerInfo.name}</div>
                            <div className="focus-summary-meta">
                              座位 {seatOrder.indexOf(selectedPlayerInfo.name) + 1} · {selectedRoleMeta?.label || selectedPlayerInfo.role || "未知"}
                            </div>
                          </div>
                          <span className="mini-chip" style={{ color: selectedRoleMeta?.color || "#dbe6e2", borderColor: `${selectedRoleMeta?.color || "#dbe6e2"}44` }}>
                            {selectedPlayerInfo.status === "dead" ? "出局" : "存活"}
                          </span>
                        </div>
                        <div className="compact-info" style={{ marginTop: 12 }}>
                          {selectedPlayerInfo.personality || "暂无个性标签"}
                        </div>
                        <div className="chip-row" style={{ marginTop: 12 }}>
                          <span className="mini-chip">思考记录 {selectedThoughts.length}</span>
                          <span className="mini-chip">轮次视角 {thoughtsByPlayer[selectedPlayerInfo.name]?.length ?? 0}</span>
                          <span className="mini-chip">局内便签 {selectedAgentNotes.length}</span>
                        </div>
                        <div style={{ marginTop: 14 }}>
                          <div className="field-label">AI 局内便签</div>
                          {selectedAgentNotes.length > 0 ? (
                            <div className="note-stack" style={{ marginTop: 8 }}>
                              {selectedAgentNotes.map((note, index) => (
                                <div key={`${selectedPlayerInfo.name}-note-${index}`} className="note-entry">
                                  {note}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="compact-info" style={{ marginTop: 8 }}>
                              暂时还没有记录到这名 AI 的局内便签。
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="seat-roster-panel">
                  <div className="section-headline">
                    <div>
                      <div className="field-label">玩家速览</div>
                      <p className="section-copy">点击任意玩家，座位图与思考流会同步切换焦点。</p>
                    </div>
                  </div>

                  <div className="seat-roster-grid">
                    {seatOrder.map((name, index) => {
                      const player = players.find((item) => item.name === name);
                      if (!player) {
                        return null;
                      }

                      const roleMeta = player.role ? ROLE_META[player.role] : null;
                      const active = selectedPlayer === player.name;

                      return (
                        <button
                          key={`roster-inline-${player.name}`}
                          type="button"
                          className={`roster-card${active ? " active" : ""}`}
                          onClick={() => setSelectedPlayer(player.name)}
                          style={{
                            borderColor: active ? `${roleMeta?.color || "#dfb3ff"}77` : undefined,
                            background: active ? roleMeta?.bg || "rgba(255,255,255,0.05)" : undefined,
                            opacity: player.status === "dead" ? 0.62 : 1,
                          }}
                        >
                          <div className="split-inline" style={{ alignItems: "flex-start" }}>
                            <div>
                              <div className="field-label">座位 {index + 1}</div>
                              <div style={{ marginTop: 6, fontSize: 17, fontWeight: 800, color: "#f5f0e6" }}>{player.name}</div>
                            </div>
                            <span className="mini-chip" style={{ color: roleMeta?.color || "#dbe6e2", borderColor: `${roleMeta?.color || "#dbe6e2"}44` }}>
                              {player.status === "dead" ? "出局" : "存活"}
                            </span>
                          </div>
                          <div style={{ marginTop: 10, color: roleMeta?.color || "#dbe6e2", fontWeight: 700 }}>{roleMeta?.label || player.role || "未知"}</div>
                          <div style={{ marginTop: 6, color: "var(--text-muted)", fontSize: 12 }}>
                            {player.personality || "暂无个性标签"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="match-config-panel legacy-roster-panel">
                <div className="section-headline">
                  <div>
                    <div className="field-label">玩家速览</div>
                    <p className="section-copy">点击任意玩家，座位图与思考流会同步切换焦点。</p>
                  </div>
                </div>

                <div className="player-roster-grid" style={{ marginTop: 14 }}>
                  {seatOrder.map((name, index) => {
                    const player = players.find((item) => item.name === name);
                    if (!player) {
                      return null;
                    }

                    const roleMeta = player.role ? ROLE_META[player.role] : null;
                    const active = selectedPlayer === player.name;

                    return (
                      <button
                        key={`roster-${player.name}`}
                        type="button"
                        className={`roster-card${active ? " active" : ""}`}
                        onClick={() => setSelectedPlayer(player.name)}
                        style={{
                          borderColor: active ? `${roleMeta?.color || "#dfb3ff"}77` : undefined,
                          background: active ? roleMeta?.bg || "rgba(255,255,255,0.05)" : undefined,
                          opacity: player.status === "dead" ? 0.62 : 1,
                        }}
                      >
                        <div className="split-inline" style={{ alignItems: "flex-start" }}>
                          <div>
                            <div className="field-label">座位 {index + 1}</div>
                            <div style={{ marginTop: 6, fontSize: 17, fontWeight: 800, color: "#f5f0e6" }}>{player.name}</div>
                          </div>
                          <span className="mini-chip" style={{ color: roleMeta?.color || "#dbe6e2", borderColor: `${roleMeta?.color || "#dbe6e2"}44` }}>
                            {player.status === "dead" ? "出局" : "存活"}
                          </span>
                        </div>
                        <div style={{ marginTop: 10, color: roleMeta?.color || "#dbe6e2", fontWeight: 700 }}>{roleMeta?.label || player.role || "未知"}</div>
                        <div style={{ marginTop: 6, color: "var(--text-muted)", fontSize: 12 }}>
                          {player.personality || "暂无个性标签"}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {(showRulesPanel || showSnapshotPanel) && (
              <div className="top-info-grid" style={{ marginTop: 16 }}>
                {showRulesPanel && (
                  <div className="section-card top-info-card">
                    <div className="section-headline">
                      <div>
                        <h4 className="section-title">阵容与规则</h4>
                        <p className="section-copy">快速核对角色密度和关键房规。</p>
                      </div>
                    </div>
                    <div className="chip-row" style={{ marginTop: 16 }}>
                      {roleBreakdown.map((role) => (
                        <span key={role.id} className="role-chip" style={{ color: role.color, borderColor: `${role.color}55` }}>
                          {role.label} x {role.count}
                        </span>
                      ))}
                    </div>
                    <div className="rule-grid" style={{ marginTop: 16 }}>
                      {(rules ? describeRules(rules) : []).map((item) => (
                        <div key={item.label} className="rule-card">
                          <div className="field-label">{item.label}</div>
                          <div style={{ marginTop: 8, fontSize: 15, fontWeight: 700 }}>{item.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {showSnapshotPanel && (
                  <div className="section-card top-info-card">
                    <div className="section-headline">
                      <div>
                        <h4 className="section-title">快照摘要</h4>
                        <p className="section-copy">只保留关键局势信息，避免把信息区再次切碎。</p>
                      </div>
                    </div>
                    <div className="table-like" style={{ marginTop: 16 }}>
                      <div className="table-row">
                        <span>夜晚死亡</span>
                        <strong>{game?.night_kills?.length ? game.night_kills.join("、") : "暂无"}</strong>
                      </div>
                      <div className="table-row">
                        <span>白天放逐</span>
                        <strong>{game?.day_eliminated || "暂无"}</strong>
                      </div>
                      <div className="table-row">
                        <span>累计出局</span>
                        <strong>{deathNames.length ? deathNames.join("、") : "暂无"}</strong>
                      </div>
                      <div className="table-row">
                        <span>座位顺序</span>
                        <strong>{seatOrder.length ? seatOrder.join(" -> ") : "等待排座"}</strong>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="live-columns">
        <div className="live-column">
          <div className="scroll-column">
            <div className="section-card">
              <div className="section-headline">
                <div>
                  <h4 className="section-title">公开时间线</h4>
                  <p className="section-copy">GM 公告、发言、投票和生死事件按照真实顺序压在这里。</p>
                </div>
                <span className="mini-chip">Public Feed</span>
              </div>
            </div>

            <div ref={publicLogRef} className="timeline-list">
              {gmAnnouncement && (
                <div className="timeline-card" style={{ borderColor: "rgba(242,191,109,0.24)" }}>
                  <div className="tiny-label" style={{ color: "#f2bf6d" }}>
                    GM 公告
                  </div>
                  <div style={{ marginTop: 10, lineHeight: 1.7 }}>{gmAnnouncement}</div>
                </div>
              )}

              {gameOver && (
                <div className="timeline-card" style={{ borderColor: "rgba(223,179,255,0.28)" }}>
                  <div className="tiny-label" style={{ color: "#dfb3ff" }}>
                    结算
                  </div>
                  <div style={{ marginTop: 10, fontWeight: 800, color: "#f6ebff" }}>{winnerLabel} 获胜</div>
                  <div className="chip-row" style={{ marginTop: 12 }}>
                    {players.map((player) => {
                      const roleMeta = player.role ? ROLE_META[player.role] : null;
                      return (
                        <span key={player.name} className="role-chip" style={{ color: roleMeta?.color || "#d7dedc", borderColor: `${roleMeta?.color || "#d7dedc"}55` }}>
                          {player.name} · {roleMeta?.label || player.role || "未知"}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {events.length === 0 ? (
                <div className="empty-state">游戏还没有产生公开事件。开始后，这里会依次显示发言、公告、投票和死亡记录。</div>
              ) : (
                events.map((event, index) => renderEvent(event, index))
              )}
            </div>
          </div>
        </div>

        <div className="live-column">
          <div className="scroll-column">
            <div className="section-card">
              <div className="section-headline">
                <div>
                  <h4 className="section-title">AI 思考流</h4>
                  <p className="section-copy">当前聚焦和全体思考采用轮流切换，避免同屏重复信息。</p>
                </div>
                <div className="cluster">
                  <button
                    className="action-secondary"
                    type="button"
                    onClick={() => setThoughtMode("focus")}
                    style={thoughtMode === "focus" ? { borderColor: "rgba(115,208,193,0.35)", color: "#73d0c1" } : undefined}
                  >
                    当前聚焦
                  </button>
                  <button
                    className="action-secondary"
                    type="button"
                    onClick={() => setThoughtMode("all")}
                    style={thoughtMode === "all" ? { borderColor: "rgba(115,208,193,0.35)", color: "#73d0c1" } : undefined}
                  >
                    全体思考
                  </button>
                </div>
              </div>

              <div className="focus-strip" style={{ marginTop: 16 }}>
                {players.map((player) => {
                  const roleMeta = player.role ? ROLE_META[player.role] : null;
                  const active = selectedPlayer === player.name;
                  return (
                    <button
                      key={player.name}
                      className={`focus-pill${active ? " active" : ""}`}
                      onClick={() => setSelectedPlayer(player.name)}
                      style={{
                        borderColor: `${roleMeta?.color || "#dfb3ff"}55`,
                        background: active ? roleMeta?.color || "#dfb3ff" : undefined,
                        color: active ? "#10151a" : roleMeta?.color || "#dbe6e2",
                      }}
                    >
                      {player.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="section-card">
              <div className="section-headline">
                <div>
                  <h4 className="section-title">{thoughtMode === "focus" ? "当前聚焦" : "全员思考总流"}</h4>
                  <p className="section-copy">
                    {thoughtMode === "focus"
                      ? selectedPlayer
                        ? `正在查看 ${selectedPlayer} 的完整思考链。`
                        : "从上方选择一名玩家。"
                      : "如果你想查“谁先起了这个念头”，全员流更适合横向比对。"}
                  </p>
                </div>
              </div>

              <div className="thought-list" style={{ marginTop: 16 }}>
                {thoughtMode === "focus" ? (
                  <>
                    {!selectedPlayer && <div className="empty-state">请选择一名玩家以查看其思考记录。</div>}
                    {selectedPlayer && selectedThoughts.length === 0 && <div className="empty-state">{selectedPlayer} 目前还没有被记录到的思考内容。</div>}
                    {selectedPlayer && (
                      <AsciiAgentNotePanel
                        playerName={selectedPlayer}
                        notes={selectedAgentNotes}
                        accentColor={selectedRoleMeta?.color}
                        compact={selectedThoughts.length > 0}
                      />
                    )}
                    {selectedPlayer && selectedIsWolf && (
                      <WolfChatPanel
                        playerName={selectedPlayer}
                        items={selectedWolfChat}
                        accentColor={selectedRoleMeta?.color}
                      />
                    )}
                    {selectedThoughts.map((thought, index) => (
                      <ThoughtCard key={`${thought.speaker}-${thought.round_number}-${index}`} thought={thought} />
                    ))}
                  </>
                ) : thoughtFeed.length === 0 ? (
                  <div className="empty-state">当前还没有抓到 AI 思考记录。</div>
                ) : (
                  <div ref={thoughtLogRef} className="thought-list">
                    {thoughtFeed.map((thought, index) => (
                      <ThoughtCard key={`feed-${thought.speaker}-${thought.round_number}-${index}`} thought={thought} compact />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function KpiCard({
  label,
  value,
  detail,
  tone = "#eef4f1",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="kpi-card">
      <div className="field-label">{label}</div>
      <div className="kpi-value" style={{ color: tone }}>
        {value}
      </div>
      <div className="kpi-detail">{detail}</div>
    </div>
  );
}

function ThoughtCard({ thought, compact = false }: { thought: SpeechRecord; compact?: boolean }) {
  const phaseView = getThoughtPhaseMeta(thought.phase);

  return (
    <article className="thought-card" style={{ borderColor: `${phaseView.color}55`, padding: compact ? 16 : 18 }}>
      <div className="split-inline" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <strong style={{ color: "#f5f0e6" }}>{thought.speaker}</strong>
          <div className="chip-row" style={{ marginTop: 8 }}>
            <span className="mini-chip">第 {thought.round_number} 轮</span>
            <span className="mini-chip" style={{ color: phaseView.color, borderColor: `${phaseView.color}55` }}>
              {phaseView.label}
            </span>
          </div>
        </div>
      </div>

      <ThoughtBlock title="内心思考" tone="#d1b4ff" text={thought.inner_thought || "这条记录没有抓到有效思考。"} />
      {thought.skill_info && <ThoughtBlock title="技能信息" tone={phaseView.color} text={thought.skill_info} subtle />}
      {thought.public_speech && <ThoughtBlock title="公开发言" tone="#71d2b8" text={thought.public_speech} subtle />}
    </article>
  );
}

function WolfChatPanel({
  playerName,
  items,
  accentColor,
}: {
  playerName: string;
  items: WolfChatRecord[];
  accentColor?: string;
}) {
  return (
    <article className="focus-note-panel compact" style={{ borderColor: `${accentColor || "#ff8f72"}55` }}>
      <div className="split-inline" style={{ alignItems: "flex-start", gap: 12 }}>
        <div>
          <div className="tiny-label" style={{ color: accentColor || "#ff8f72" }}>
            Wolf Night Chat
          </div>
          <div className="focus-note-heading">{playerName} 可见的狼队夜话</div>
        </div>
        <span className="mini-chip" style={{ color: accentColor || "#ff8f72", borderColor: `${accentColor || "#ff8f72"}44` }}>
          {items.length} messages
        </span>
      </div>

      {items.length > 0 ? (
        <div className="note-stack" style={{ marginTop: 12 }}>
          {items
            .slice()
            .reverse()
            .map((item, index) => (
              <div key={`${item.speaker}-${item.round_number}-${index}`} className="note-entry">
                <div className="chip-row" style={{ marginBottom: 8 }}>
                  <span className="mini-chip">第 {item.round_number} 夜</span>
                  {item.kill_target && <span className="mini-chip">刀口 {item.kill_target}</span>}
                  <span className="mini-chip">{item.speaker}</span>
                </div>
                {item.message}
              </div>
            ))}
        </div>
      ) : (
        <div className="compact-info focus-note-empty" style={{ marginTop: 12 }}>
          这名狼人当前还没有可见的夜晚狼队私聊。刀口确定后，狼队夜话会在这里实时出现，并保留给后续上下文。
        </div>
      )}
    </article>
  );
}

function AsciiAgentNotePanel({
  playerName,
  notes,
  accentColor,
  compact = false,
}: {
  playerName: string;
  notes: string[];
  accentColor?: string;
  compact?: boolean;
}) {
  return (
    <article
      className={`focus-note-panel${compact ? " compact" : ""}`}
      style={{ borderColor: `${accentColor || "#73d0c1"}44` }}
    >
      <div className="split-inline" style={{ alignItems: "flex-start", gap: 12 }}>
        <div>
          <div className="tiny-label" style={{ color: accentColor || "#73d0c1" }}>
            AI Notes
          </div>
          <div className="focus-note-heading">{playerName}</div>
        </div>
        <span className="mini-chip" style={{ color: accentColor || "#73d0c1", borderColor: `${accentColor || "#73d0c1"}44` }}>
          {notes.length} items
        </span>
      </div>

      {notes.length > 0 ? (
        <div className="note-stack" style={{ marginTop: 12 }}>
          {notes.map((note, index) => (
            <div key={`${playerName}-ascii-note-${index}`} className="note-entry">
              {note}
            </div>
          ))}
        </div>
      ) : (
        <div className="compact-info focus-note-empty" style={{ marginTop: 12 }}>
          No cached notes yet. New notes will appear here as the AI digests each public speech and updates its own running plan.
        </div>
      )}
    </article>
  );
}

function FocusAgentNotePanel({
  playerName,
  notes,
  accentColor,
  compact = false,
}: {
  playerName: string;
  notes: string[];
  accentColor?: string;
  compact?: boolean;
}) {
  return (
    <article
      className={`focus-note-panel${compact ? " compact" : ""}`}
      style={{ borderColor: `${accentColor || "#73d0c1"}44` }}
    >
      <div className="split-inline" style={{ alignItems: "flex-start", gap: 12 }}>
        <div>
          <div className="tiny-label" style={{ color: accentColor || "#73d0c1" }}>
            AI 局内便签
          </div>
          <div className="focus-note-heading">{playerName}</div>
        </div>
        <span className="mini-chip" style={{ color: accentColor || "#73d0c1", borderColor: `${accentColor || "#73d0c1"}44` }}>
          {notes.length} 条
        </span>
      </div>

      {notes.length > 0 ? (
        <div className="note-stack" style={{ marginTop: 12 }}>
          {notes.map((note, index) => (
            <div key={`${playerName}-focus-note-${index}`} className="note-entry">
              {note}
            </div>
          ))}
        </div>
      ) : (
        <div className="compact-info focus-note-empty" style={{ marginTop: 12 }}>
          这名 AI 还没有新的局内便签。新局开始后，随着公开发言被逐条消化，这里会按时间倒序累积它自己的判断摘要和后续计划。
        </div>
      )}
    </article>
  );
}

function AgentNotePanel({
  playerName,
  notes,
  accentColor,
  compact = false,
}: {
  playerName: string;
  notes: string[];
  accentColor?: string;
  compact?: boolean;
}) {
  return (
    <article
      className={`focus-note-panel${compact ? " compact" : ""}`}
      style={{ borderColor: `${accentColor || "#73d0c1"}44` }}
    >
      <div className="split-inline" style={{ alignItems: "flex-start", gap: 12 }}>
        <div>
          <div className="tiny-label" style={{ color: accentColor || "#73d0c1" }}>
            AI 灞€鍐呬究绛?
          </div>
          <div className="focus-note-heading">{playerName}</div>
        </div>
        <span className="mini-chip" style={{ color: accentColor || "#73d0c1", borderColor: `${accentColor || "#73d0c1"}44` }}>
          {notes.length} 鏉?
        </span>
      </div>

      {notes.length > 0 ? (
        <div className="note-stack" style={{ marginTop: 12 }}>
          {notes.map((note, index) => (
            <div key={`${playerName}-focus-note-${index}`} className="note-entry">
              {note}
            </div>
          ))}
        </div>
      ) : (
        <div className="compact-info focus-note-empty" style={{ marginTop: 12 }}>
          杩欏悕 AI 杩樻病鏈夋柊鐨勫眬鍐呬究绛俱€傛柊灞€寮€濮嬪悗锛岄殢鐫€鍙戣█琚€�鏉ュ洖娑堝寲锛岃繖閲屼細鎸夋椂闂村€掑簭绉疮瀹冭嚜宸辩殑鎽樿鍜屽悗缁鍒掋€?
        </div>
      )}
    </article>
  );
}

function ThoughtBlock({
  title,
  tone,
  text,
  subtle = false,
}: {
  title: string;
  tone: string;
  text: string;
  subtle?: boolean;
}) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ color: tone, fontSize: 12, fontWeight: 800, marginBottom: 6 }}>{title}</div>
      <div
        className="compact-info"
        style={{
          background: subtle ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.045)",
          lineHeight: 1.75,
          color: "#f2eee5",
        }}
      >
        {text}
      </div>
    </div>
  );
}

function renderEvent(event: SSEEvent, index: number) {
  if (event.event === "speech") {
    const data = event.data as { speaker: string; public_speech: string; round: number; phase?: string };
    const phaseView = getThoughtPhaseMeta(data.phase ?? "discuss");
    return (
      <article key={index} className="timeline-card" style={{ borderColor: `${phaseView.color}33` }}>
        <div className="split-inline">
          <strong style={{ color: phaseView.color }}>{data.speaker}</strong>
          <span className="field-label">
            第 {data.round} 轮 · {phaseView.label}
          </span>
        </div>
        <div style={{ marginTop: 12, lineHeight: 1.75 }}>{data.public_speech}</div>
      </article>
    );
  }

  if (event.event === "gm_announcement") {
    const data = event.data as GMAnnouncementEventData;
    return (
      <article key={index} className="timeline-card" style={{ borderColor: "rgba(242,191,109,0.18)" }}>
        <div className="tiny-label" style={{ color: "#f2bf6d" }}>
          GM 公告
        </div>
        <div style={{ marginTop: 10 }}>{data.message}</div>
      </article>
    );
  }

  if (event.event === "death") {
    const data = event.data as DeathEventData;
    return (
      <article key={index} className="timeline-card" style={{ borderColor: "rgba(255,143,114,0.2)" }}>
        <div className="tiny-label" style={{ color: "#ff8f72" }}>
          出局事件
        </div>
        <div style={{ marginTop: 10 }}>{data.message || `${data.player} 已出局`}</div>
      </article>
    );
  }

  if (event.event === "vote_cast") {
    const data = event.data as VoteCastEventData;
    const isSheriffVote = data.context === "sheriff";
    return (
      <article key={index} className="timeline-card">
        <div className="tiny-label">
          {isSheriffVote ? `警长第 ${data.round ?? 1} 轮投票` : "放逐投票"}
        </div>
        <div style={{ marginTop: 10, color: "#efdfbf" }}>
          {data.voter} {"->"} {data.target}
        </div>
      </article>
    );
  }

  if (event.event === "vote_result") {
    const data = event.data as VoteResultEventData;
    return (
      <article key={index} className="timeline-card" style={{ borderColor: "rgba(235,166,95,0.2)" }}>
        <div className="tiny-label" style={{ color: "#eba65f" }}>
          投票结果
        </div>
        <div style={{ marginTop: 10 }}>{data.message}</div>
      </article>
    );
  }

  if (event.event === "phase_change") {
    const data = event.data as PhaseChangeEventData;
    const meta = PHASE_META[data.phase];
    return (
      <article key={index} className="timeline-card" style={{ borderColor: `${meta.color}33` }}>
        <div className="tiny-label" style={{ color: meta.color }}>
          {meta.label}
        </div>
        <div style={{ marginTop: 10, color: "#dde6e4" }}>{typeof data.round === "number" ? `第 ${data.round} 轮` : "阶段切换"}</div>
        {data.message && <div style={{ marginTop: 8, color: "var(--text-muted)" }}>{data.message}</div>}
      </article>
    );
  }

  if (event.event === "night_action") {
    const data = event.data as NightActionEventData;
    return (
      <article key={index} className="timeline-card" style={{ borderColor: "rgba(134,149,255,0.2)" }}>
        <div className="tiny-label" style={{ color: "#8695ff" }}>
          夜间行动
        </div>
        <div style={{ marginTop: 10 }}>{data.message}</div>
      </article>
    );
  }

  if (event.event === "sheriff_update") {
    const data = event.data as SheriffUpdateEventData;
    return (
      <article key={index} className="timeline-card" style={{ borderColor: "rgba(242,191,109,0.2)" }}>
        <div className="tiny-label" style={{ color: "#f2bf6d" }}>
          警徽流转
        </div>
        <div style={{ marginTop: 10 }}>{data.message}</div>
      </article>
    );
  }

  if (event.event === "seating") {
    const data = event.data as SeatingEventData;
    return (
      <article key={index} className="timeline-card">
        <div className="tiny-label">座位顺序</div>
        <div style={{ marginTop: 10 }}>{data.order.join(" -> ")}</div>
      </article>
    );
  }

  return null;
}
