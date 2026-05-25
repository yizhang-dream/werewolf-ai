import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { ROLE_LIBRARY, ROLE_META, countRoles, describeRules, formatRules, summarizeTeams } from "../../lib/gameUi";
import type { GameRules, GameTemplate, PlayerConfig, ProviderInfo, RoleId } from "../../types/game";

const DEFAULT_NAMES = ["阿尔法", "贝塔", "伽马", "德尔塔", "艾普西隆", "泽塔", "伊塔", "西塔", "约塔", "卡帕", "拉姆达", "缪"];
const PREFERRED_DEFAULT_MODEL = "glm-5.1";
const DEFAULT_PERSONALITIES = [
  "冷静理性，擅长逻辑分析。",
  "热情直接，容易快速点名。",
  "谨慎观察，发言不多但信息量高。",
  "活跃健谈，喜欢带动全场节奏。",
  "多疑细致，擅长抓矛盾。",
  "坦率直给，有想法就会表达。",
  "稳健克制，偏好先听后打。",
  "喜欢反问和试探，思路很跳脱。",
  "擅长复盘投票，喜欢抓站边变化。",
  "敢冲敢顶，也会在关键轮次强推。",
  "节奏偏慢，但结论通常很硬。",
  "喜欢做人设，偶尔会故意卖破绽。",
];

const TEMPLATE_COLORS: Record<string, string> = {
  "6p_beginner": "#78cba7",
  "8p_standard": "#54c0b3",
  "9p_hunter": "#6aa8ff",
  "12p_standard": "#e0b364",
  "12p_wolf_king_guard": "#ff8f72",
  "12p_white_wolf_guard": "#d596ff",
};

const DEFAULT_RULES: GameRules = {
  win_rule: "slaughter_side",
  witch_self_save_rule: "first_night_only",
  same_guard_save_survives: false,
  guard_can_self_protect: true,
  first_night_last_words: true,
  sheriff_enabled: true,
  sheriff_vote_multiplier: 1.5,
  white_wolf_explode_during_day: true,
  white_wolf_explode_ends_day: true,
  knight_duel_ends_discussion: true,
};

function createDefaultPlayer(index: number): PlayerConfig {
  return {
    name: DEFAULT_NAMES[index] || `玩家 ${index + 1}`,
    personality: DEFAULT_PERSONALITIES[index % DEFAULT_PERSONALITIES.length],
    llm_provider: "",
    model_name: "",
  };
}

function getDefaultModel(models: string[]) {
  return models.includes(PREFERRED_DEFAULT_MODEL) ? PREFERRED_DEFAULT_MODEL : models[0] || "";
}

function getTemplateTone(templateId: string) {
  return TEMPLATE_COLORS[templateId] || "#7ac7b8";
}

function compareTemplates(a: GameTemplate, b: GameTemplate) {
  if (a.roles.length !== b.roles.length) {
    return a.roles.length - b.roles.length;
  }
  return a.name.localeCompare(b.name, "zh-CN");
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [templates, setTemplates] = useState<GameTemplate[]>([]);
  const [players, setPlayers] = useState<PlayerConfig[]>(Array.from({ length: 6 }, (_, index) => createDefaultPlayer(index)));
  const [roles, setRoles] = useState<RoleId[]>(["werewolf", "werewolf", "seer", "witch", "villager", "villager"]);
  const [rules, setRules] = useState<GameRules>(DEFAULT_RULES);
  const [fastMode, setFastMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [storedDefault, setStoredDefault] = useState("");

  useEffect(() => {
    let active = true;

    async function loadData() {
      try {
        const [providerResp, templateList] = await Promise.all([api.listProviders(), api.listTemplates()]);
        if (!active) {
          return;
        }
        setProviders(providerResp.providers);
        setStoredDefault(providerResp.default_provider);
        setTemplates([...templateList].sort(compareTemplates));
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "加载开局数据失败");
      }
    }

    void loadData();
    return () => {
      active = false;
    };
  }, []);

  const readyProviders = providers.filter((provider) => provider.has_key);
  const defaultProvider = readyProviders.find((p) => p.name === storedDefault) || readyProviders[0] || providers[0] || null;
  const roleStats = countRoles(roles);
  const selectedTemplate = templates.find((template) => template.id === selectedTemplateId) ?? null;
  const teamSummary = summarizeTeams(roles);
  const syncState = players.length === roles.length;
  const effectiveRuleSummary = describeRules(rules);

  const roleInsights = useMemo(
    () => [
      { label: "狼队", value: teamSummary.wolf, tone: "#ff8f72" },
      { label: "神职", value: teamSummary.god, tone: "#73d0c1" },
      { label: "平民", value: teamSummary.villager, tone: "#f2bf6d" },
    ],
    [teamSummary]
  );

  function updatePlayer(index: number, field: keyof PlayerConfig, value: string) {
    setPlayers((current) => current.map((player, i) => (i === index ? { ...player, [field]: value } : player)));
  }

  function resizePlayers(nextCount: number) {
    setPlayers((current) => {
      const nextPlayers = current.slice(0, nextCount);
      while (nextPlayers.length < nextCount) {
        nextPlayers.push(createDefaultPlayer(nextPlayers.length));
      }
      return nextPlayers;
    });
  }

  function addPlayer() {
    resizePlayers(players.length + 1);
  }

  function removePlayer(index: number) {
    setPlayers((current) => current.filter((_, i) => i !== index));
  }

  function updateRole(index: number, value: RoleId) {
    setRoles((current) => current.map((role, i) => (i === index ? value : role)));
  }

  function addRole() {
    setRoles((current) => [...current, "villager"]);
  }

  function removeRole(index: number) {
    setRoles((current) => current.filter((_, i) => i !== index));
  }

  function syncPlayersToRoles() {
    resizePlayers(roles.length);
  }

  function syncRolesToPlayers() {
    setRoles((current) => {
      const nextRoles = current.slice(0, players.length);
      while (nextRoles.length < players.length) {
        nextRoles.push("villager");
      }
      return nextRoles;
    });
  }

  function applyTemplateToEditor(template: GameTemplate) {
    setSelectedTemplateId(template.id);
    setRoles(template.roles);
    setRules(template.rules);
    resizePlayers(template.roles.length);
    setError("");
  }

  function applyProviderToAll(providerName: string) {
    const provider = providers.find((item) => item.name === providerName);
    const defaultModel = provider ? getDefaultModel(provider.models) : "";
    setPlayers((current) =>
      current.map((player) => ({
        ...player,
        llm_provider: providerName,
        model_name: defaultModel,
      }))
    );
  }

  function updatePlayerProvider(index: number, providerName: string) {
    const provider = providers.find((item) => item.name === providerName);
    setPlayers((current) =>
      current.map((player, i) =>
        i === index
          ? {
              ...player,
              llm_provider: providerName,
              model_name: provider && !provider.models.includes(player.model_name) ? getDefaultModel(provider.models) : player.model_name,
            }
          : player
      )
    );
  }

  function updateRule<K extends keyof GameRules>(key: K, value: GameRules[K]) {
    setRules((current) => ({ ...current, [key]: value }));
  }

  async function quickStart(templateId: string) {
    setError("");
    if (readyProviders.length === 0) {
      setError("请先在模型设置中配置至少一个带 API Key 的 Provider。");
      return;
    }

    setLoading(true);
    try {
      const result = await api.quickStart(templateId);
      navigate(`/game/${result.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "快速开局失败");
      setLoading(false);
    }
  }

  async function startGame() {
    setError("");

    if (players.length < 4) {
      setError("至少需要 4 名玩家。");
      return;
    }
    if (players.length !== roles.length) {
      setError(`玩家数 (${players.length}) 和角色数 (${roles.length}) 必须一致。`);
      return;
    }
    if (readyProviders.length === 0) {
      setError("请先在模型设置中配置至少一个带 API Key 的 Provider。");
      return;
    }

    const fallbackProvider = readyProviders[0];
    const payloadPlayers = players.map((player) => {
      const effectiveProvider = providers.find((provider) => provider.name === player.llm_provider) || fallbackProvider;
      return {
        ...player,
        llm_provider: player.llm_provider || effectiveProvider.name,
        model_name: player.model_name || getDefaultModel(effectiveProvider.models),
      };
    });

    setLoading(true);
    try {
      const result = await api.createGame({
        players: payloadPlayers,
        roles,
        auto_advance: fastMode,
        rules,
      });
      navigate(`/game/${result.game_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建对局失败");
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <div className="eyebrow">Setup Studio</div>
          <h2>创建一局真正可跑、可调、可复盘的狼人杀</h2>
          <p>
            这里把常用板子、规则面板、玩家编排和模型分配同时展开。你可以像搭一张作战桌一样，一边看整体，一边改细节，而不是在多个页面里来回切。
          </p>
        </div>
        <div className="hero-stats">
          <StatTile label="已配 Provider" value={`${readyProviders.length}`} tone={readyProviders.length > 0 ? "#f2bf6d" : "#ff8f72"} />
          <StatTile label="可用板子" value={`${templates.length}`} tone="#73d0c1" />
          <StatTile label="当前人数" value={`${players.length}`} tone="#dcb8ff" />
        </div>
      </section>

      {error && <div className="alert-banner">{error}</div>}

      <section className="two-page-grid">
        <div className="sheet-panel section-stack">
          <div>
            <div className="eyebrow">Board Catalog</div>
            <h3 className="sheet-title">左页：板子库与开局状态</h3>
            <p className="sheet-subtitle">
              用它快速浏览常用配置，直接开局，或者载入到右侧编辑台继续微调。当前有效规则也会在这里同步展开。
            </p>
          </div>

          <div className="kpi-grid">
            <KpiCard
              label="默认 Provider"
              value={defaultProvider ? defaultProvider.name : "未配置"}
              detail={defaultProvider ? `默认模型：${getDefaultModel(defaultProvider.models) || "未填写模型"}` : "请先至少配置一个 Provider。"}
            />
            <KpiCard
              label="手动对局概览"
              value={`${players.length} 名玩家 / ${roles.length} 个身份`}
              detail={syncState ? "人数与角色数已经对齐。" : "人数与角色数不一致，开局前需要同步。"}
              tone={syncState ? "#73d0c1" : "#ff8f72"}
            />
            <KpiCard
              label="当前选中板子"
              value={selectedTemplate ? `已载入 ${selectedTemplate.name}` : "未载入模板"}
              detail={selectedTemplate ? formatRules(selectedTemplate.rules) : "你可以从下方板子库载入一个基础配置。"}
              tone={selectedTemplate ? getTemplateTone(selectedTemplate.id) : "#eef4f1"}
            />
          </div>

          <div className="section-card">
            <div className="section-headline">
              <div>
                <h4 className="section-title">快速开局</h4>
                <p className="section-copy">适合直接压测流程；如果你想改角色或规则，可以先把模板载入右页再继续编排。</p>
              </div>
              <Link to="/settings" className="action-secondary" style={{ textDecoration: "none" }}>
                前往模型设置
              </Link>
            </div>

            <div className="template-grid" style={{ marginTop: 16 }}>
              {templates.map((template) => {
                const tone = getTemplateTone(template.id);
                const isSelected = template.id === selectedTemplateId;

                return (
                  <article
                    key={template.id}
                    className={`template-card${isSelected ? " active" : ""}`}
                    style={{
                      borderColor: isSelected ? `${tone}88` : undefined,
                      boxShadow: isSelected ? `0 18px 42px ${tone}22` : undefined,
                    }}
                  >
                    <div className="split-inline" style={{ alignItems: "flex-start" }}>
                      <div>
                        <span className="mini-chip" style={{ color: tone, borderColor: `${tone}66`, background: `${tone}16` }}>
                          {template.roles.length} 人局
                        </span>
                        <h4 style={{ margin: "12px 0 6px", fontSize: 20 }}>{template.name}</h4>
                        <div className="muted-copy" style={{ fontSize: 14 }}>
                          {template.description}
                        </div>
                      </div>
                    </div>

                    <div className="muted-copy" style={{ fontSize: 13 }}>
                      {formatRules(template.rules)}
                    </div>

                    <div className="chip-row">
                      {countRoles(template.roles).map((role) => (
                        <span key={`${template.id}-${role.id}`} className="role-chip" style={{ color: role.color, borderColor: `${role.color}55` }}>
                          {role.label} x {role.count}
                        </span>
                      ))}
                    </div>

                    <div className="template-actions">
                      <button
                        onClick={() => void quickStart(template.id)}
                        disabled={loading || readyProviders.length === 0}
                        className="action-primary"
                        style={{ background: `linear-gradient(135deg, ${tone}, #f7d994)` }}
                      >
                        直接开局
                      </button>
                      <button onClick={() => applyTemplateToEditor(template)} className="action-secondary">
                        载入编辑器
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          <div className="section-card">
            <div className="section-headline">
              <div>
                <h4 className="section-title">规则总览</h4>
                <p className="section-copy">规则不再藏在后端默认值里。当前右页即将创建的这局，会按下面这套规则执行。</p>
              </div>
            </div>
            <div className="rule-grid" style={{ marginTop: 16 }}>
              {effectiveRuleSummary.map((item) => (
                <div key={item.label} className="rule-card">
                  <div className="field-label">{item.label}</div>
                  <div style={{ marginTop: 8, fontSize: 17, fontWeight: 700 }}>{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="sheet-panel section-stack">
          <div>
            <div className="eyebrow">Draft Board</div>
            <h3 className="sheet-title">右页：手动编排与规则编辑</h3>
            <p className="sheet-subtitle">
              玩家、角色、规则和摘要同时显示。你可以把它理解为“开局前控制台”，所有关键设置都尽量摊开在一个视图里。
            </p>
          </div>

          <div className="builder-grid">
            <div className="section-stack">
              <div className="section-card">
                <div className="section-headline">
                  <div>
                    <h4 className="section-title">玩家列表</h4>
                    <p className="section-copy">为每个 AI 指定人格、Provider 和模型，方便你做风格与效果对比。</p>
                  </div>
                  <div className="cluster">
                    <button onClick={syncPlayersToRoles} className="action-secondary">
                      按角色数同步玩家
                    </button>
                    <select
                      value={players[0]?.llm_provider || defaultProvider?.name || ""}
                      onChange={(e) => applyProviderToAll(e.target.value)}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 8,
                        border: "1px solid var(--border-subtle)",
                        background: "var(--surface-card)",
                        color: "var(--text-primary)",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                        maxWidth: 180,
                      }}
                    >
                      <option value="">选择 API...</option>
                      {readyProviders.map((p) => (
                        <option key={p.name} value={p.name}>{p.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="player-card-grid" style={{ marginTop: 16 }}>
                  {players.map((player, index) => {
                    const provider = providers.find((item) => item.name === player.llm_provider) || defaultProvider;
                    const modelOptions = provider?.models || [];

                    return (
                      <div key={`${player.name}-${index}`} className="player-card">
                        <div className="split-inline" style={{ marginBottom: 16, alignItems: "flex-start" }}>
                          <div>
                            <span className="mini-chip">玩家 {index + 1}</span>
                            <div style={{ marginTop: 10, fontSize: 18, fontWeight: 700 }}>{player.name || `玩家 ${index + 1}`}</div>
                          </div>
                          <button onClick={() => removePlayer(index)} className="action-secondary">
                            删除
                          </button>
                        </div>

                        <div className="player-grid">
                          <label className="field">
                            <span className="field-label">名字</span>
                            <input value={player.name} onChange={(event) => updatePlayer(index, "name", event.target.value)} placeholder="玩家名称" />
                          </label>

                          <label className="field">
                            <span className="field-label">Provider</span>
                            <select value={player.llm_provider} onChange={(event) => updatePlayerProvider(index, event.target.value)}>
                              <option value="">使用默认 Provider</option>
                              {providers.map((providerOption) => (
                                <option key={providerOption.name} value={providerOption.name}>
                                  {providerOption.name}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label className="field" style={{ gridColumn: "1 / -1" }}>
                            <span className="field-label">性格设定</span>
                            <input
                              value={player.personality}
                              onChange={(event) => updatePlayer(index, "personality", event.target.value)}
                              placeholder="例如：沉稳、重视逻辑、愿意强势带队"
                            />
                          </label>

                          <label className="field">
                            <span className="field-label">模型</span>
                            <select value={player.model_name} onChange={(event) => updatePlayer(index, "model_name", event.target.value)}>
                              <option value="">{provider ? `使用 ${provider.name} 默认模型` : "请先选择 Provider"}</option>
                              {modelOptions.map((model) => (
                                <option key={`${player.name}-${model}`} value={model}>
                                  {model}
                                </option>
                              ))}
                            </select>
                          </label>

                          <div className="compact-info">
                            <div className="field-label">当前将使用</div>
                            <div style={{ marginTop: 6, fontWeight: 700 }}>{player.llm_provider || defaultProvider?.name || "未配置 Provider"}</div>
                            <div style={{ marginTop: 4, color: "var(--text-muted)", fontSize: 12 }}>
                              {player.model_name || (provider ? getDefaultModel(provider.models) : "") || "未选择模型"}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <button onClick={addPlayer} className="action-ghost" style={{ width: "100%", marginTop: 14 }}>
                  + 添加玩家
                </button>
              </div>

              <div className="section-card">
                <div className="section-headline">
                  <div>
                    <h4 className="section-title">角色配置</h4>
                    <p className="section-copy">支持从模板载入后微调，也支持从零搭一套测试板子。</p>
                  </div>
                  <button onClick={syncRolesToPlayers} className="action-secondary">
                    按玩家数同步角色
                  </button>
                </div>

                <div className="stack" style={{ marginTop: 16 }}>
                  {roles.map((role, index) => {
                    const info = ROLE_META[role];
                    return (
                      <div key={`${role}-${index}`} className="role-row">
                        <div className="split-inline" style={{ alignItems: "center" }}>
                          <div style={{ minWidth: 124 }}>
                            <div className="field-label">位置 {index + 1}</div>
                            <div style={{ marginTop: 6, color: info.color, fontWeight: 700 }}>{info.label}</div>
                          </div>
                          <select value={role} onChange={(event) => updateRole(index, event.target.value as RoleId)} style={{ flex: 1 }}>
                            {ROLE_LIBRARY.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.label} - {item.desc}
                              </option>
                            ))}
                          </select>
                          <button onClick={() => removeRole(index)} className="action-secondary">
                            删除
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <button onClick={addRole} className="action-ghost" style={{ width: "100%", marginTop: 14 }}>
                  + 添加角色
                </button>
              </div>
            </div>

            <div className="section-stack">
              <div className="section-card">
                <div className="section-headline">
                  <div>
                    <h4 className="section-title">对局摘要</h4>
                    <p className="section-copy">从阵营构成到板子密度，右侧这块会实时反馈你现在到底搭了什么。</p>
                  </div>
                </div>

                <div className="kpi-grid" style={{ marginTop: 16 }}>
                  <KpiCard label="玩家人数" value={`${players.length}`} detail="当前将创建的 AI 数量。" />
                  <KpiCard label="角色人数" value={`${roles.length}`} detail="需要与玩家人数保持一致。" />
                  <KpiCard label="模式" value={fastMode ? "快速推进" : "标准节奏"} detail="快速模式会跳过发言间隔。" tone={fastMode ? "#dcb8ff" : "#73d0c1"} />
                </div>

                <div className="team-bars" style={{ marginTop: 16 }}>
                  {roleInsights.map((team) => (
                    <div key={team.label} className="team-bar">
                      <div className="split-inline">
                        <span style={{ color: team.tone }}>{team.label}</span>
                        <strong>{team.value}</strong>
                      </div>
                      <div className="team-bar-track">
                        <div
                          className="team-bar-fill"
                          style={{
                            width: `${roles.length > 0 ? (team.value / roles.length) * 100 : 0}%`,
                            background: `linear-gradient(90deg, ${team.tone}, transparent)`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="chip-row" style={{ marginTop: 16 }}>
                  {roleStats.map((item) => (
                    <span key={`summary-${item.id}`} className="role-chip" style={{ color: item.color, borderColor: `${item.color}55` }}>
                      {item.label} x {item.count}
                    </span>
                  ))}
                </div>
              </div>

              <div className="section-card">
                <div className="section-headline">
                  <div>
                    <h4 className="section-title">规则编辑</h4>
                    <p className="section-copy">把对局真正关键的规则显式化，避免“板子对了但房规不对”的问题。</p>
                  </div>
                </div>

                <div className="stack" style={{ marginTop: 16 }}>
                  <label className="field">
                    <span className="field-label">胜利规则</span>
                    <select value={rules.win_rule} onChange={(event) => updateRule("win_rule", event.target.value as GameRules["win_rule"])}>
                      <option value="slaughter_side">屠边</option>
                      <option value="total_elimination">屠城</option>
                      <option value="parity">人狼平票即狼胜</option>
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">女巫自救</span>
                    <select
                      value={rules.witch_self_save_rule}
                      onChange={(event) => updateRule("witch_self_save_rule", event.target.value as GameRules["witch_self_save_rule"])}
                    >
                      <option value="never">不可自救</option>
                      <option value="first_night_only">仅首夜可自救</option>
                      <option value="always">始终可自救</option>
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">警长票权倍率</span>
                    <select
                      value={String(rules.sheriff_vote_multiplier)}
                      onChange={(event) => updateRule("sheriff_vote_multiplier", Number(event.target.value))}
                    >
                      <option value="1">1.0</option>
                      <option value="1.5">1.5</option>
                      <option value="2">2.0</option>
                    </select>
                  </label>
                </div>

                <div className="switch-grid" style={{ marginTop: 16 }}>
                  <SwitchRow checked={rules.same_guard_save_survives} onChange={(checked) => updateRule("same_guard_save_survives", checked)} title="同守同救存活" desc="关闭时，同守同救仍会死亡。" />
                  <SwitchRow checked={rules.guard_can_self_protect} onChange={(checked) => updateRule("guard_can_self_protect", checked)} title="守卫可以自守" desc="关闭后守卫不能连续守自己或任何自己夜。" />
                  <SwitchRow checked={rules.first_night_last_words} onChange={(checked) => updateRule("first_night_last_words", checked)} title="首夜遗言" desc="首夜倒牌后是否保留遗言环节。" />
                  <SwitchRow checked={rules.sheriff_enabled} onChange={(checked) => updateRule("sheriff_enabled", checked)} title="启用警长系统" desc="关闭后不会进行警长竞选，也没有归票加成。" />
                  <SwitchRow checked={rules.white_wolf_explode_during_day} onChange={(checked) => updateRule("white_wolf_explode_during_day", checked)} title="白狼王白天可自爆" desc="影响白狼王能否在发言阶段直接带人。" />
                  <SwitchRow checked={rules.white_wolf_explode_ends_day} onChange={(checked) => updateRule("white_wolf_explode_ends_day", checked)} title="白狼王自爆后结束白天" desc="用于区分不同板子对白狼王节奏的处理。" />
                  <SwitchRow checked={rules.knight_duel_ends_discussion} onChange={(checked) => updateRule("knight_duel_ends_discussion", checked)} title="骑士决斗后结束讨论" desc="关闭时决斗结算后仍继续剩余发言流程。" />
                </div>
              </div>

              <div className="section-card">
                <div className="section-headline">
                  <div>
                    <h4 className="section-title">开局选项</h4>
                    <p className="section-copy">最后一步只保留少量高频动作，避免误点。</p>
                  </div>
                </div>

                <label className="toggle-row" style={{ marginTop: 16 }}>
                  <input type="checkbox" checked={fastMode} onChange={(event) => setFastMode(event.target.checked)} />
                  <span>
                    <strong>快速模式</strong>
                    <span className="muted-copy" style={{ display: "block", marginTop: 4, fontSize: 13 }}>
                      跳过发言间隔，适合批量跑局和观察 Agent 行为。
                    </span>
                  </span>
                </label>

                <button className="action-primary" style={{ marginTop: 18, width: "100%" }} onClick={() => void startGame()} disabled={loading}>
                  {loading ? "创建中..." : "开始游戏"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function StatTile({ label, value, tone = "#eef4f1" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="stat-tile">
      <div className="field-label">{label}</div>
      <div style={{ marginTop: 8, fontWeight: 800, fontSize: 22, color: tone }}>{value}</div>
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

function SwitchRow({
  checked,
  onChange,
  title,
  desc,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
  desc: string;
}) {
  return (
    <label className="toggle-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>
        <strong>{title}</strong>
        <span className="muted-copy" style={{ display: "block", marginTop: 4, fontSize: 13 }}>
          {desc}
        </span>
      </span>
    </label>
  );
}
