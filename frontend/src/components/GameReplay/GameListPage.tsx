import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { getWinnerLabel } from "../../lib/gameUi";

interface GameSummary {
  game_id: string;
  winner: string | null;
  finished_at: string | null;
  created_at: string | null;
  player_count: number;
  round_number: number;
}

export default function GameListPage() {
  const navigate = useNavigate();
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const data = await api.listGames();
        if (!active) return;
        setGames(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  const s = {
    page: {
      maxWidth: 1000,
      margin: "0 auto",
      padding: "32px 24px",
    } as React.CSSProperties,
    header: {
      fontSize: 22,
      fontWeight: 700,
      color: "var(--text-primary)",
      marginBottom: 4,
    } as React.CSSProperties,
    subtitle: {
      fontSize: 13,
      color: "var(--text-muted)",
      marginBottom: 24,
    } as React.CSSProperties,
    card: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "16px 20px",
      borderRadius: 12,
      background: "var(--surface-card)",
      border: "1px solid var(--border-subtle)",
      marginBottom: 10,
    } as React.CSSProperties,
    left: {
      display: "flex",
      flexDirection: "column",
      gap: 4,
    } as React.CSSProperties,
    gameId: {
      fontSize: 13,
      fontFamily: "monospace",
      color: "var(--text-secondary)",
    } as React.CSSProperties,
    meta: {
      fontSize: 12,
      color: "var(--text-muted)",
    } as React.CSSProperties,
    winnerBadge: (tone: string) =>
      ({
        fontSize: 13,
        fontWeight: 700,
        color: tone,
        marginRight: 16,
      }) as React.CSSProperties,
    button: {
      padding: "8px 18px",
      borderRadius: 8,
      border: "none",
      fontSize: 13,
      fontWeight: 600,
      cursor: "pointer",
      background: "var(--accent)",
      color: "#fff",
    } as React.CSSProperties,
    empty: {
      textAlign: "center",
      color: "var(--text-muted)",
      padding: 48,
      fontSize: 14,
    } as React.CSSProperties,
  };

  if (loading) return <div style={s.page}><div style={s.empty}>加载中...</div></div>;
  if (error) return <div style={s.page}><div style={s.empty}>{error}</div></div>;

  return (
    <div style={s.page}>
      <div style={s.header}>历史对局</div>
      <div style={s.subtitle}>共 {games.length} 局已完成的对局，点击「复盘」查看完整回放</div>

      {games.length === 0 ? (
        <div style={s.empty}>暂无已完成的对局</div>
      ) : (
        games.map((g) => {
          const winnerLabel = getWinnerLabel(g.winner as "village" | "werewolf" | null);
          const isWolfWin = g.winner === "werewolf";
          const dateStr = g.created_at
            ? new Date(g.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
            : g.finished_at
              ? new Date(g.finished_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
              : "—";

          return (
            <div key={g.game_id} style={s.card}>
              <div style={s.left}>
                <div style={s.gameId}>{g.game_id}</div>
                <div style={s.meta}>
                  {dateStr} &middot; {g.player_count}人 &middot; {g.round_number}轮
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <span style={s.winnerBadge(isWolfWin ? "#ff8f72" : "#73d0c1")}>{winnerLabel}</span>
                <button style={s.button} onClick={() => navigate(`/replay/${g.game_id}`)}>复盘</button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
