import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { AgentDetail, AgentInfo, AgentLesson, RoleMemorySummary } from "../../types/game";

const ROLE_LABELS: Record<string, string> = {
  werewolf: "狼人",
  wolf_beauty: "狼美人",
  white_wolf: "白狼王",
  hidden_wolf: "隐狼",
  wolf_king: "狼王",
  evil_spirit_knight: "恶灵骑士",
  stone_gargoyle: "石像鬼",
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
  knight: "骑士",
  idiot: "白痴",
  silencer: "禁言长老",
  gravekeeper: "守墓人",
  villager: "平民",
};

export default function MemoryViewer() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [activeRole, setActiveRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadAgents();
  }, []);

  async function loadAgents(options: { keepSelection?: boolean } = {}) {
    const isInitialLoad = agents.length === 0;
    if (isInitialLoad) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError("");
    try {
      const nextAgents = await api.listAgents();
      setAgents(nextAgents);

      if (options.keepSelection && expanded) {
        const nextDetail = await api.getAgent(expanded);
        setDetail(nextDetail);
        setActiveRole((currentRole) =>
          currentRole && nextDetail.role_summaries[currentRole] ? currentRole : pickDefaultRole(nextDetail)
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Agent 记忆失败");
    } finally {
      if (isInitialLoad) {
        setLoading(false);
      }
      setRefreshing(false);
    }
  }

  async function openAgent(name: string) {
    if (expanded === name) {
      setExpanded(null);
      setDetail(null);
      setActiveRole(null);
      return;
    }

    try {
      const result = await api.getAgent(name);
      const defaultRole = pickDefaultRole(result);
      setDetail(result);
      setExpanded(name);
      setActiveRole(defaultRole);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Agent 详情失败");
    }
  }

  async function resetAgent(name: string) {
    try {
      await api.resetAgent(name);
      setAgents((current) => current.filter((agent) => agent.name !== name));
      setExpanded(null);
      setDetail(null);
      setActiveRole(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置 Agent 记忆失败");
    }
  }

  const totalGames = useMemo(() => agents.reduce((sum, agent) => sum + agent.total_games, 0), [agents]);
  const totalLessons = useMemo(() => agents.reduce((sum, agent) => sum + agent.lesson_count, 0), [agents]);

  if (loading) {
    return <div style={{ color: "#94a59f" }}>正在加载 Agent 记忆...</div>;
  }

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <section style={styles.hero}>
        <div>
          <div style={styles.eyebrow}>Memory Archive</div>
          <h2 style={{ margin: "10px 0 10px", fontSize: 34, lineHeight: 1.06 }}>Agent 进化档案馆</h2>
          <p style={{ margin: 0, maxWidth: 720, color: "#9fb0ab", lineHeight: 1.8 }}>
            这里不再只是“打过几局”的列表，而是每个玩家的长期画像、角色习惯、跨局沉淀和旧局证据。
            你可以直接检查某个 Agent 是否真的在变强，以及它到底学会了什么。
          </p>
        </div>

        <div style={styles.heroStats}>
          <StatTile label="Agent 数量" value={`${agents.length}`} />
          <StatTile label="累计对局" value={`${totalGames}`} tone="#e5c780" />
          <StatTile label="经验条目" value={`${totalLessons}`} tone="#7ad1b8" />
          <button
            style={{ ...styles.secondaryButton, alignSelf: "stretch" }}
            onClick={() => void loadAgents({ keepSelection: true })}
            disabled={refreshing}
          >
            {refreshing ? "刷新中..." : "刷新复盘"}
          </button>
        </div>
      </section>

      {error && <div style={styles.errorBanner}>{error}</div>}

      {agents.length === 0 ? (
        <div style={styles.emptyState}>
          还没有可展示的 Agent 记忆。先跑几局游戏，等 AI 产生复盘和策略沉淀后，这里会逐渐变成你的实验档案库。
        </div>
      ) : (
        <section style={styles.agentGrid}>
          {agents.map((agent) => {
            const winRate = agent.total_games > 0 ? Math.round((agent.wins / agent.total_games) * 100) : 0;
            const opened = expanded === agent.name && detail;

            return (
              <article key={agent.name} style={styles.agentCard}>
                <div style={styles.agentHeader}>
                  <div>
                    <div style={styles.agentName}>{agent.name}</div>
                    <div style={styles.agentMeta}>
                      共 {agent.total_games} 局 · 胜 {agent.wins} / 负 {agent.losses} · 胜率 {winRate}%
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={styles.secondaryButton} onClick={() => void openAgent(agent.name)}>
                      {opened ? "收起" : "展开"}
                    </button>
                    <button
                      style={{ ...styles.secondaryButton, color: "#ffc0b0" }}
                      onClick={(event) => {
                        event.stopPropagation();
                        void resetAgent(agent.name);
                      }}
                    >
                      重置
                    </button>
                  </div>
                </div>

                <div style={styles.metricRow}>
                  <MetricPill label="经验条目" value={`${agent.lesson_count}`} />
                  <MetricPill label="策略条数" value={`${agent.strategies.length}`} />
                </div>

                {agent.last_game_id ? (
                  <div style={styles.latestLesson}>
                    <div style={styles.sectionEyebrow}>最后复盘</div>
                    <div style={styles.latestLessonMeta}>
                      {agent.last_game_id} · {roleLabel(agent.last_role || "")} ·{" "}
                      {agent.last_won ? "胜利" : "失败"} · {agent.last_rounds_played || 0} 轮
                    </div>
                    {agent.last_reflection && (
                      <div style={styles.latestLessonText}>{agent.last_reflection}</div>
                    )}
                  </div>
                ) : (
                  <div style={styles.latestLesson}>
                    <div style={styles.sectionEyebrow}>最后复盘</div>
                    <div style={styles.latestLessonMeta}>暂无复盘记录</div>
                  </div>
                )}

                {opened && detail && (
                  <AgentDetailPanel
                    detail={detail}
                    activeRole={activeRole}
                    onSelectRole={setActiveRole}
                  />
                )}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}

function AgentDetailPanel({
  detail,
  activeRole,
  onSelectRole,
}: {
  detail: AgentDetail;
  activeRole: string | null;
  onSelectRole: (role: string | null) => void;
}) {
  const roleEntries = useMemo(
    () =>
      Object.entries(detail.role_summaries).sort(
        ([, left], [, right]) => right.total_games - left.total_games || right.wins - left.wins
      ),
    [detail.role_summaries]
  );

  const selectedRole = activeRole && detail.role_summaries[activeRole] ? activeRole : roleEntries[0]?.[0] ?? null;
  const selectedSummary = selectedRole ? detail.role_summaries[selectedRole] : null;
  const selectedLessons = useMemo(
    () =>
      selectedRole
        ? detail.lessons
            .filter((lesson) => lesson.role === selectedRole)
            .sort((left, right) => right.game_id.localeCompare(left.game_id))
        : [],
    [detail.lessons, selectedRole]
  );

  const portableTakeaways = useMemo(() => {
    const takeaways = selectedLessons.flatMap((lesson) => lesson.useful_takeaways);
    return unique(takeaways).slice(0, 8);
  }, [selectedLessons]);

  return (
    <div style={styles.detailBlock}>
      <section style={styles.summaryGrid}>
        <div style={styles.storyCard}>
          <div style={styles.sectionEyebrow}>全局策略沉淀</div>
          {detail.strategies.length > 0 ? (
            <div style={styles.tagGrid}>
              {detail.strategies.map((strategy, index) => (
                <div key={`${strategy}-${index}`} style={styles.strategyItem}>
                  {strategy}
                </div>
              ))}
            </div>
          ) : (
            <div style={styles.emptyMini}>这个 Agent 还没有形成足够稳定的全局策略。</div>
          )}
          <div style={styles.storyFooter}>记忆版本 v{detail.memory_version}</div>
        </div>
      </section>

      <section style={styles.roleSection}>
        <div style={styles.roleSectionHeader}>
          <div>
            <div style={styles.detailTitle}>角色长期记忆</div>
            <div style={styles.sectionHint}>切换不同身份，查看这个 Agent 在各类板子里的成长轨迹。</div>
          </div>
        </div>

        {roleEntries.length > 0 ? (
          <>
            <div style={styles.roleTabs}>
              {roleEntries.map(([role, summary]) => (
                <button
                  key={role}
                  style={{
                    ...styles.roleTab,
                    ...(selectedRole === role ? styles.roleTabActive : {}),
                  }}
                  onClick={() => onSelectRole(role)}
                >
                  <span>{roleLabel(role)}</span>
                  <span style={styles.roleTabMeta}>{summary.total_games} 局</span>
                </button>
              ))}
            </div>

            {selectedRole && selectedSummary && (
              <RoleSummaryPanel
                role={selectedRole}
                summary={selectedSummary}
                lessons={selectedLessons}
                takeaways={portableTakeaways}
              />
            )}
          </>
        ) : (
          <div style={styles.emptyMini}>这个 Agent 还没有形成角色级总结。需要再跑几局才能看出习惯。</div>
        )}
      </section>

      <section style={styles.detailSection}>
        <div style={styles.detailTitle}>最近复盘</div>
        <div style={styles.sectionHint}>按时间倒序展示最新局的反思，方便观察它最近在学什么。</div>
        {detail.lessons.length > 0 ? (
          <div style={styles.lessonGrid}>
            {[...detail.lessons]
              .sort((left, right) => right.game_id.localeCompare(left.game_id))
              .slice(0, 6)
              .map((lesson, index) => (
                <LessonCard key={`${lesson.game_id}-${index}`} lesson={lesson} compact />
              ))}
          </div>
        ) : (
          <div style={styles.emptyMini}>还没有赛后复盘。</div>
        )}
      </section>
    </div>
  );
}

function RoleSummaryPanel({
  role,
  summary,
  lessons,
  takeaways,
}: {
  role: string;
  summary: RoleMemorySummary;
  lessons: AgentLesson[];
  takeaways: string[];
}) {
  const winRate = summary.total_games > 0 ? Math.round((summary.wins / summary.total_games) * 100) : 0;

  return (
    <div style={styles.rolePanel}>
      <div style={styles.roleHero}>
        <div>
          <div style={styles.sectionEyebrow}>当前角色</div>
          <div style={styles.roleHeading}>{roleLabel(role)}</div>
          <div style={styles.roleMeta}>
            {summary.total_games} 局 · 胜 {summary.wins} / 负 {summary.losses} · 胜率 {winRate}%
          </div>
        </div>

        <div style={styles.roleStatStrip}>
          <MetricPill label="最后更新" value={summary.last_updated_game_id || "暂无"} />
          <MetricPill label="近期样本" value={`${lessons.length}`} />
        </div>
      </div>

      <div style={styles.memoryColumns}>
        <MemoryBlock title="这个角色常打好的点" items={summary.strengths} tone="#8fe0bf" />
        <MemoryBlock title="反复踩过的坑" items={summary.pitfalls} tone="#f0c082" />
        <MemoryBlock title="需要盯的信号" items={summary.signals_to_watch} tone="#8fc4e8" />
        <MemoryBlock title="可执行的打法建议" items={summary.role_tips} tone="#f0a7a0" />
      </div>

      <div style={styles.detailSection}>
        <div style={styles.detailTitle}>可迁移经验</div>
        {takeaways.length > 0 ? (
          <div style={styles.tagGrid}>
            {takeaways.map((item, index) => (
              <div key={`${item}-${index}`} style={styles.takeawayChip}>
                {item}
              </div>
            ))}
          </div>
        ) : (
          <div style={styles.emptyMini}>这个角色暂时还没有抽象出足够稳定的跨局经验。</div>
        )}
      </div>

      <div style={styles.detailSection}>
        <div style={styles.detailTitle}>相似旧局引用</div>
        <div style={styles.sectionHint}>这些是同角色下的历史样本，便于观察它如何把旧经验迁移到新局里。</div>
        {lessons.length > 0 ? (
          <div style={styles.lessonGrid}>
            {lessons.slice(0, 4).map((lesson, index) => (
              <LessonCard key={`${lesson.game_id}-${index}`} lesson={lesson} />
            ))}
          </div>
        ) : (
          <div style={styles.emptyMini}>这个角色还没有历史局样本。</div>
        )}
      </div>
    </div>
  );
}

function LessonCard({ lesson, compact = false }: { lesson: AgentLesson; compact?: boolean }) {
  return (
    <article style={{ ...styles.lessonCard, ...(compact ? styles.lessonCardCompact : {}) }}>
      <div style={styles.lessonMeta}>
        <span>{roleLabel(lesson.role)}</span>
        <span>{lesson.won ? "胜利" : "失败"}</span>
        <span>{lesson.player_count} 人局</span>
        <span>{lesson.rounds_played} 轮</span>
      </div>
      <div style={styles.lessonSubMeta}>
        <span>{lesson.role_config || "未知板型"}</span>
        <span>{lesson.survived_to_end ? "存活到终局" : "中途出局"}</span>
      </div>
      <div style={styles.lessonReflection}>{lesson.reflection}</div>
      {lesson.useful_takeaways.length > 0 && (
        <div style={styles.inlineChipRow}>
          {lesson.useful_takeaways.map((item, index) => (
            <span key={`${lesson.game_id}-takeaway-${index}`} style={styles.smallChip}>
              {item}
            </span>
          ))}
        </div>
      )}
      {lesson.key_moments.length > 0 && (
        <div style={styles.momentList}>
          {lesson.key_moments.map((moment, index) => (
            <div key={`${lesson.game_id}-${index}`} style={styles.momentItem}>
              {moment}
            </div>
          ))}
        </div>
      )}
      <div style={styles.storyFooter}>{lesson.game_id}</div>
    </article>
  );
}

function MemoryBlock({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <section style={styles.memoryBlock}>
      <div style={{ ...styles.memoryBlockTitle, color: tone }}>{title}</div>
      {items.length > 0 ? (
        <div style={styles.memoryBlockList}>
          {items.map((item, index) => (
            <div key={`${title}-${index}`} style={styles.memoryBullet}>
              {item}
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.emptyMini}>暂时没有稳定结论。</div>
      )}
    </section>
  );
}

function StatTile({ label, value, tone = "#f4efe5" }: { label: string; value: string; tone?: string }) {
  return (
    <div style={styles.statTile}>
      <div style={{ fontSize: 12, color: "#8ea19d" }}>{label}</div>
      <div style={{ marginTop: 6, fontWeight: 700, fontSize: 22, color: tone }}>{value}</div>
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.metricPill}>
      <span style={{ color: "#8ea19d", fontSize: 12 }}>{label}</span>
      <strong style={{ color: "#f4efe5" }}>{value}</strong>
    </div>
  );
}

function roleLabel(role: string) {
  return ROLE_LABELS[role] ?? role;
}

function unique(items: string[]) {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function pickDefaultRole(detail: AgentDetail) {
  const roleEntries = Object.entries(detail.role_summaries).sort(
    ([, left], [, right]) => right.total_games - left.total_games || right.wins - left.wins
  );
  return roleEntries[0]?.[0] ?? detail.lessons[detail.lessons.length - 1]?.role ?? null;
}

const styles = {
  hero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "flex-end",
    flexWrap: "wrap" as const,
    borderRadius: 30,
    padding: 24,
    background:
      "linear-gradient(140deg, rgba(199, 92, 51, 0.14), rgba(226, 186, 106, 0.12) 42%, rgba(91, 156, 132, 0.1) 80%)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  eyebrow: {
    display: "inline-flex",
    padding: "6px 10px",
    borderRadius: 999,
    background: "rgba(230, 176, 86, 0.16)",
    color: "#f0d59d",
    fontSize: 12,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
  },
  heroStats: {
    display: "flex",
    gap: 12,
    flexWrap: "wrap" as const,
  },
  statTile: {
    minWidth: 132,
    borderRadius: 20,
    padding: "14px 16px",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  errorBanner: {
    borderRadius: 18,
    padding: "14px 16px",
    background: "rgba(153, 55, 40, 0.24)",
    border: "1px solid rgba(255, 129, 98, 0.26)",
    color: "#ffc7b8",
  },
  emptyState: {
    borderRadius: 24,
    padding: 22,
    background: "rgba(255,255,255,0.03)",
    border: "1px dashed rgba(255,255,255,0.14)",
    color: "#97aaa5",
  },
  agentGrid: {
    display: "grid",
    gap: 14,
  },
  agentCard: {
    borderRadius: 26,
    padding: 22,
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  agentHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 14,
    alignItems: "flex-start",
    flexWrap: "wrap" as const,
  },
  agentName: {
    fontSize: 22,
    fontWeight: 700,
  },
  agentMeta: {
    marginTop: 8,
    color: "#94a59f",
    fontSize: 13,
  },
  metricRow: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap" as const,
    marginTop: 16,
  },
  latestLesson: {
    display: "grid",
    gap: 8,
    marginTop: 14,
    borderRadius: 18,
    padding: "13px 14px",
    background: "rgba(229, 199, 128, 0.07)",
    border: "1px solid rgba(229, 199, 128, 0.13)",
  },
  latestLessonMeta: {
    color: "#f0e4ca",
    fontSize: 13,
    lineHeight: 1.6,
  },
  latestLessonText: {
    color: "#aebfba",
    fontSize: 13,
    lineHeight: 1.65,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical" as const,
    overflow: "hidden",
  },
  metricPill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  secondaryButton: {
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 14,
    padding: "10px 14px",
    background: "rgba(255,255,255,0.03)",
    color: "#f3eee3",
    cursor: "pointer",
  },
  detailBlock: {
    display: "grid",
    gap: 18,
    marginTop: 18,
    paddingTop: 18,
    borderTop: "1px solid rgba(255,255,255,0.08)",
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 16,
  },
  storyCard: {
    display: "grid",
    gap: 12,
    borderRadius: 24,
    padding: 20,
    background: "linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.025))",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  sectionEyebrow: {
    fontSize: 12,
    color: "#93a8a2",
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
  },
  storyFooter: {
    color: "#8fa39e",
    fontSize: 12,
  },
  detailSection: {
    display: "grid",
    gap: 10,
  },
  detailTitle: {
    fontSize: 18,
    fontWeight: 700,
    color: "#f0e4ca",
  },
  sectionHint: {
    color: "#92a7a1",
    fontSize: 13,
    lineHeight: 1.6,
  },
  tagGrid: {
    display: "grid",
    gap: 10,
  },
  strategyItem: {
    borderRadius: 16,
    padding: "12px 14px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    color: "#eef1e8",
  },
  roleSection: {
    display: "grid",
    gap: 14,
  },
  roleSectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-end",
    flexWrap: "wrap" as const,
  },
  roleTabs: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap" as const,
  },
  roleTab: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    borderRadius: 999,
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(255,255,255,0.03)",
    color: "#f4efe5",
    padding: "10px 14px",
    cursor: "pointer",
  },
  roleTabActive: {
    background: "linear-gradient(135deg, rgba(229, 186, 104, 0.22), rgba(105, 177, 149, 0.18))",
    border: "1px solid rgba(229, 186, 104, 0.34)",
  },
  roleTabMeta: {
    color: "#9cb0ab",
    fontSize: 12,
  },
  rolePanel: {
    display: "grid",
    gap: 18,
    borderRadius: 26,
    padding: 20,
    background: "rgba(8, 14, 17, 0.28)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  roleHero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-end",
    flexWrap: "wrap" as const,
  },
  roleHeading: {
    fontSize: 26,
    fontWeight: 700,
    color: "#fff1d6",
  },
  roleMeta: {
    marginTop: 8,
    color: "#94a8a2",
    fontSize: 14,
  },
  roleStatStrip: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap" as const,
  },
  memoryColumns: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 14,
  },
  memoryBlock: {
    display: "grid",
    gap: 10,
    borderRadius: 20,
    padding: 16,
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
  },
  memoryBlockTitle: {
    fontWeight: 700,
    fontSize: 14,
  },
  memoryBlockList: {
    display: "grid",
    gap: 8,
  },
  memoryBullet: {
    borderRadius: 14,
    padding: "10px 12px",
    background: "rgba(255,255,255,0.03)",
    color: "#edf2ed",
    lineHeight: 1.6,
  },
  emptyMini: {
    borderRadius: 16,
    padding: "12px 14px",
    background: "rgba(255,255,255,0.025)",
    border: "1px dashed rgba(255,255,255,0.09)",
    color: "#93a7a2",
  },
  takeawayChip: {
    display: "inline-flex",
    alignItems: "center",
    borderRadius: 999,
    padding: "8px 12px",
    background: "rgba(111, 207, 180, 0.1)",
    border: "1px solid rgba(111, 207, 180, 0.16)",
    color: "#d8f3ea",
  },
  lessonGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: 12,
  },
  lessonCard: {
    borderRadius: 20,
    padding: 16,
    background: "rgba(12, 18, 22, 0.32)",
    border: "1px solid rgba(255,255,255,0.06)",
    display: "grid",
    gap: 10,
  },
  lessonCardCompact: {
    background: "rgba(255,255,255,0.025)",
  },
  lessonMeta: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 10,
    color: "#dccba7",
    fontSize: 12,
  },
  lessonSubMeta: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 10,
    color: "#8ea19d",
    fontSize: 12,
  },
  lessonReflection: {
    color: "#f3efe4",
    lineHeight: 1.75,
  },
  inlineChipRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap" as const,
  },
  smallChip: {
    display: "inline-flex",
    borderRadius: 999,
    padding: "6px 10px",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    color: "#cfe0dc",
    fontSize: 12,
  },
  momentList: {
    display: "grid",
    gap: 6,
  },
  momentItem: {
    borderRadius: 12,
    padding: "10px 12px",
    background: "rgba(255,255,255,0.03)",
    color: "#bfcfcb",
    fontSize: 13,
    lineHeight: 1.6,
  },
};
