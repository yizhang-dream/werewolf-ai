import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { ProviderInfo } from "../../types/game";

interface EditingProvider {
  name: string;
  provider_type: string;
  api_key: string;
  base_url: string;
  models: string;
}

const EMPTY_PROVIDER: EditingProvider = {
  name: "",
  provider_type: "openai_compatible",
  api_key: "",
  base_url: "",
  models: "",
};

export default function SettingsPanel() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [defaultProvider, setDefaultProvider] = useState("");
  const [editing, setEditing] = useState<EditingProvider | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void loadProviders();
  }, []);

  async function loadProviders() {
    try {
      const resp = await api.listProviders();
      setProviders(resp.providers);
      setDefaultProvider(resp.default_provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Provider 失败");
    }
  }

  async function handleSetDefault(name: string) {
    try {
      await api.setDefaultProvider(name);
      setDefaultProvider(name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置默认 Provider 失败");
    }
  }

  function startAdd(type: "openai_compatible" | "claude" = "openai_compatible") {
    setEditing({
      ...EMPTY_PROVIDER,
      provider_type: type,
    });
    setError("");
  }

  function startEdit(provider: ProviderInfo) {
    setEditing({
      name: provider.name,
      provider_type: provider.provider_type,
      api_key: "",
      base_url: provider.base_url,
      models: provider.models.join(", "),
    });
    setError("");
  }

  async function saveProvider() {
    if (!editing) {
      return;
    }

    const name = editing.name.trim();
    const models = editing.models
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    if (!name) {
      setError("Provider 名称不能为空。");
      return;
    }

    if (models.length === 0) {
      setError("请至少填写一个模型名称。");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await api.saveProvider({
        name,
        provider_type: editing.provider_type,
        api_key: editing.api_key || undefined,
        base_url: editing.base_url.trim() || undefined,
        models,
      });
      setEditing(null);
      await loadProviders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存 Provider 失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeProvider(name: string) {
    setError("");
    try {
      await api.deleteProvider(name);
      await loadProviders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除 Provider 失败");
    }
  }

  async function importFromCcSwitch() {
    setError("");
    try {
      const result = await api.importCcSwitch();
      window.alert(result.imported > 0 ? `成功导入 ${result.imported} 个 Provider` : "没有发现新的可导入 Provider");
      await loadProviders();
    } catch (err) {
      window.alert(err instanceof Error ? `导入失败：${err.message}` : "导入失败");
    }
  }

  const providerCount = providers.length;
  const readyCount = providers.filter((provider) => provider.has_key).length;

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <section style={styles.hero}>
        <div>
          <div style={styles.eyebrow}>Provider Hub</div>
          <h2 style={{ margin: "10px 0 10px", fontSize: 34, lineHeight: 1.06 }}>模型设置不该只是填几行表单</h2>
          <p style={{ margin: 0, color: "#9eb0ac", maxWidth: 680 }}>
            这里把 Provider、兼容接口和模型列表集中管理。配对正确后，开局页会自动吃到默认模型，快速开局也不会再拿空配置去跑。
          </p>
        </div>

        <div style={styles.stats}>
          <StatTile label="已配置 Provider" value={`${providerCount}`} />
          <StatTile label="带 Key 的 Provider" value={`${readyCount}`} tone="#e5c780" />
        </div>
      </section>

      {error && <div style={styles.errorBanner}>{error}</div>}

      <section style={styles.panel}>
        <div style={styles.panelHeader}>
          <div>
            <div style={styles.panelTitle}>常用入口</div>
            <div style={styles.panelDesc}>新建时可以直接从常见协议模板起步，减少字段搭错的概率。</div>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button style={styles.secondaryButton} onClick={() => startAdd("openai_compatible")}>
              + 新建 OpenAI Compatible
            </button>
            <button style={styles.secondaryButton} onClick={() => startAdd("claude")}>
              + 新建 Claude Compatible
            </button>
            <button style={styles.secondaryButton} onClick={() => void importFromCcSwitch()}>
              从 CC Switch 导入
            </button>
          </div>
        </div>

        <div style={styles.guideGrid}>
          <GuideCard
            title="OpenAI Compatible"
            desc="适用于 OpenAI、Ollama 和大多数 `/v1/chat/completions` 兼容接口。"
            tone="#6fcfb4"
          />
          <GuideCard
            title="Claude Compatible"
            desc="适用于 Anthropic 官方接口，以及像智谱 Anthropic 兼容地址这样的 Claude 风格接口。"
            tone="#f0bf78"
          />
        </div>
      </section>

      <section style={styles.contentGrid}>
        <div style={{ display: "grid", gap: 16 }}>
          <div style={styles.panel}>
            <div style={styles.panelTitle}>已配置 Provider</div>
            <div style={styles.panelDesc}>开局页默认会优先使用列表中的第一个可用 Provider。</div>

            <div style={{ display: "grid", gap: 14, marginTop: 18 }}>
              {providers.length === 0 && (
                <div style={styles.emptyState}>
                  还没有 Provider。建议先添加一个带 API Key 的模型服务，再去创建对局。
                </div>
              )}

              {providers.map((provider, index) => (
                <article key={provider.name} style={styles.providerCard}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                    <div>
                      <div style={styles.providerMetaRow}>
                        <span style={styles.providerName}>{provider.name}</span>
                        <span style={styles.protocolTag}>{provider.provider_type === "claude" ? "Claude Compatible" : "OpenAI Compatible"}</span>
                        {provider.name === defaultProvider ? (
                          <span style={styles.defaultTag}>默认</span>
                        ) : provider.has_key ? (
                          <button style={{ ...styles.miniButton, fontSize: 11, padding: "2px 8px" }} onClick={() => void handleSetDefault(provider.name)}>
                            设为默认
                          </button>
                        ) : null}
                      </div>
                      <div style={{ marginTop: 10, color: "#97aaa5", fontSize: 13 }}>
                        {provider.base_url || "使用官方默认地址"}
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8 }}>
                      <button style={styles.miniButton} onClick={() => startEdit(provider)}>
                        编辑
                      </button>
                      <button style={{ ...styles.miniButton, color: "#ffc0b0" }} onClick={() => void removeProvider(provider.name)}>
                        删除
                      </button>
                    </div>
                  </div>

                  <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ ...styles.statusChip, color: provider.has_key ? "#71d7a5" : "#ff9d84" }}>
                      {provider.has_key ? "API Key 已配置" : "未配置 API Key"}
                    </span>
                    {provider.models.map((model) => (
                      <span key={`${provider.name}-${model}`} style={styles.modelChip}>
                        {model}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>

        <aside style={{ display: "grid", gap: 16, alignSelf: "start", position: "sticky", top: 16 }}>
          <div style={styles.panel}>
            <div style={styles.panelTitle}>{editing ? "编辑 Provider" : "使用说明"}</div>

            {editing ? (
              <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
                <label style={styles.field}>
                  <span style={styles.fieldLabel}>名称</span>
                  <input
                    style={styles.input}
                    value={editing.name}
                    onChange={(event) => setEditing({ ...editing, name: event.target.value })}
                    placeholder="例如：Zhipu GLM / OpenAI / Ollama"
                  />
                </label>

                <label style={styles.field}>
                  <span style={styles.fieldLabel}>协议类型</span>
                  <select
                    style={styles.input}
                    value={editing.provider_type}
                    onChange={(event) => setEditing({ ...editing, provider_type: event.target.value })}
                  >
                    <option value="openai_compatible">OpenAI Compatible</option>
                    <option value="claude">Claude Compatible</option>
                  </select>
                </label>

                <label style={styles.field}>
                  <span style={styles.fieldLabel}>API Key</span>
                  <input
                    style={styles.input}
                    type="password"
                    value={editing.api_key}
                    onChange={(event) => setEditing({ ...editing, api_key: event.target.value })}
                    placeholder="留空则保留已有值或保存为空"
                  />
                </label>

                <label style={styles.field}>
                  <span style={styles.fieldLabel}>Base URL</span>
                  <input
                    style={styles.input}
                    value={editing.base_url}
                    onChange={(event) => setEditing({ ...editing, base_url: event.target.value })}
                    placeholder={editing.provider_type === "claude" ? "例如：https://open.bigmodel.cn/api/anthropic" : "例如：http://localhost:11434/v1"}
                  />
                </label>

                <label style={styles.field}>
                  <span style={styles.fieldLabel}>模型列表</span>
                  <input
                    style={styles.input}
                    value={editing.models}
                    onChange={(event) => setEditing({ ...editing, models: event.target.value })}
                    placeholder="用逗号分隔，例如：glm-4.7, glm-5.1"
                  />
                </label>

                <div style={styles.helperBox}>
                  {editing.provider_type === "claude"
                    ? "Claude Compatible 会走 Anthropic 风格接口，并且会正确使用你填写的自定义 Base URL。"
                    : "OpenAI Compatible 适合绝大多数兼容 Chat Completions 的模型网关。"}
                </div>

                <div style={{ display: "flex", gap: 10 }}>
                  <button style={{ ...styles.primaryButton, flex: 1 }} onClick={() => void saveProvider()} disabled={saving}>
                    {saving ? "保存中..." : "保存 Provider"}
                  </button>
                  <button style={styles.secondaryButton} onClick={() => setEditing(null)} disabled={saving}>
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ marginTop: 16, display: "grid", gap: 12, color: "#9fb0ab", fontSize: 14 }}>
                <div style={styles.helperBox}>
                  Claude 类型现在已经支持自定义 `base_url`，所以像智谱 Anthropic 兼容地址也可以直接配置。
                </div>
                <div style={styles.helperBox}>
                  开局页会默认取“列表中的第一个可用 Provider”作为兜底模型来源。
                </div>
                <div style={styles.helperBox}>
                  如果你想减少切换成本，建议把最常用的 Provider 放在列表最前面。
                </div>
              </div>
            )}
          </div>
        </aside>
      </section>
    </div>
  );
}

function StatTile({ label, value, tone = "#71d7a5" }: { label: string; value: string; tone?: string }) {
  return (
    <div style={styles.statTile}>
      <div style={{ fontSize: 12, color: "#8ea19d" }}>{label}</div>
      <div style={{ marginTop: 6, fontWeight: 700, fontSize: 22, color: tone }}>{value}</div>
    </div>
  );
}

function GuideCard({ title, desc, tone }: { title: string; desc: string; tone: string }) {
  return (
    <div style={{ ...styles.guideCard, borderColor: `${tone}40` }}>
      <div style={{ color: tone, fontWeight: 700 }}>{title}</div>
      <div style={{ marginTop: 8, color: "#9eb0ac", fontSize: 13 }}>{desc}</div>
    </div>
  );
}

const styles = {
  hero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "flex-end",
    flexWrap: "wrap" as const,
    borderRadius: 28,
    padding: 24,
    background: "linear-gradient(135deg, rgba(68, 173, 147, 0.12), rgba(228, 181, 109, 0.08) 55%, rgba(255,255,255,0.03))",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  eyebrow: {
    display: "inline-flex",
    padding: "6px 10px",
    borderRadius: 999,
    background: "rgba(111, 207, 180, 0.15)",
    color: "#9fe4d0",
    fontSize: 12,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
  },
  stats: {
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
  panel: {
    borderRadius: 26,
    padding: 22,
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "flex-start",
    flexWrap: "wrap" as const,
  },
  panelTitle: {
    fontSize: 22,
    fontWeight: 700,
  },
  panelDesc: {
    marginTop: 6,
    color: "#92a5a0",
    fontSize: 14,
  },
  guideGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
    gap: 12,
    marginTop: 18,
  },
  guideCard: {
    borderRadius: 20,
    padding: 16,
    background: "rgba(11, 18, 20, 0.3)",
    border: "1px solid rgba(255,255,255,0.06)",
  },
  contentGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 360px",
    gap: 24,
    alignItems: "start",
  },
  emptyState: {
    padding: 20,
    borderRadius: 18,
    background: "rgba(11, 18, 20, 0.28)",
    border: "1px dashed rgba(255,255,255,0.14)",
    color: "#97aaa5",
  },
  providerCard: {
    borderRadius: 22,
    padding: 18,
    background: "rgba(11, 18, 20, 0.28)",
    border: "1px solid rgba(255,255,255,0.06)",
  },
  providerMetaRow: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap" as const,
  },
  providerName: {
    fontSize: 18,
    fontWeight: 700,
  },
  protocolTag: {
    padding: "5px 10px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
    fontSize: 12,
    color: "#d4ddd9",
  },
  defaultTag: {
    padding: "5px 10px",
    borderRadius: 999,
    background: "rgba(229, 199, 128, 0.14)",
    color: "#eed9a8",
    fontSize: 12,
  },
  statusChip: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    fontSize: 12,
  },
  modelChip: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "rgba(79, 132, 161, 0.12)",
    border: "1px solid rgba(111, 177, 214, 0.18)",
    color: "#b7d9ea",
    fontSize: 12,
  },
  miniButton: {
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 12,
    padding: "8px 12px",
    background: "rgba(255,255,255,0.03)",
    color: "#f4efe5",
    cursor: "pointer",
  },
  field: {
    display: "grid",
    gap: 6,
  },
  fieldLabel: {
    color: "#8da09b",
    fontSize: 12,
  },
  input: {
    width: "100%",
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(4, 8, 12, 0.35)",
    color: "#f4efe5",
    padding: "12px 14px",
    outline: "none",
  },
  helperBox: {
    borderRadius: 16,
    padding: "12px 14px",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    color: "#a6b6b2",
    fontSize: 13,
  },
  primaryButton: {
    border: "none",
    borderRadius: 16,
    padding: "12px 16px",
    background: "#e3ba70",
    color: "#1c1912",
    fontWeight: 700,
    cursor: "pointer",
  },
  secondaryButton: {
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 16,
    padding: "11px 16px",
    background: "rgba(255,255,255,0.03)",
    color: "#f3eee3",
    cursor: "pointer",
  },
};
