import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api } from "../api/client";
import type { ProviderInfo } from "../types/game";

const navItems = [
  { to: "/setup", label: "新建对局", short: "J", desc: "板子库、规则编辑、玩家与模型配置。" },
  { to: "/games", label: "历史对局", short: "L", desc: "查看已结束对局的完整复盘。" },
  { to: "/agents", label: "Agent 记忆", short: "A", desc: "复盘、策略沉淀与长期画像。" },
  { to: "/settings", label: "模型设置", short: "M", desc: "Provider、模型列表与接口配置。" },
];

export default function Layout() {
  const location = useLocation();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [backendOnline, setBackendOnline] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadAppStatus() {
      try {
        const [health, providerResp] = await Promise.all([api.health(), api.listProviders()]);
        if (!active) {
          return;
        }
        setBackendOnline(health.status === "ok");
        setProviders(providerResp.providers);
      } catch {
        if (!active) {
          return;
        }
        setBackendOnline(false);
        setProviders([]);
      }
    }

    void loadAppStatus();
    return () => {
      active = false;
    };
  }, [location.pathname]);

  const readyProviders = providers.filter((provider) => provider.has_key);

  return (
    <div className="app-frame">
      <div className={`app-shell hover-rail-shell${sidebarExpanded ? " expanded" : ""}`}>
        <aside
          className={`app-sidebar hover-rail${sidebarExpanded ? " expanded" : ""}`}
          aria-label="App navigation"
          onMouseEnter={() => setSidebarExpanded(true)}
          onMouseLeave={() => setSidebarExpanded(false)}
          onFocus={() => setSidebarExpanded(true)}
          onBlur={(event) => {
            const nextTarget = event.relatedTarget;
            if (!nextTarget || !event.currentTarget.contains(nextTarget as Node)) {
              setSidebarExpanded(false);
            }
          }}
        >
          <button type="button" className="rail-trigger" aria-label="Main navigation" aria-expanded={sidebarExpanded}>
            <span className="rail-trigger-core">W</span>
          </button>

          <div className="rail-drawer">
            <div className="sidebar-brand">
              <div className="split-inline sidebar-brand-head" style={{ alignItems: "flex-start" }}>
                <div>
                  <span className="eyebrow rail-badge">
                    <span className="rail-badge-icon">W</span>
                    <span className="rail-badge-text">Werewolf Lab</span>
                  </span>
                  <h1 className="sidebar-title">AI 狼人杀控制台</h1>
                </div>
                <span className="sidebar-hint">窄栏展开</span>
              </div>
              <p className="sidebar-copy">默认只保留一个小图标，悬停命中后整列展开，不再挤占主视图。</p>
            </div>

            <div className="status-grid rail-expand-only">
              <StatusCard
                label="后端状态"
                value={backendOnline ? "在线" : "离线"}
                tone={backendOnline ? "#66d8b4" : "#ff8f72"}
                detail={backendOnline ? "API 与 SSE 服务均可用。" : "请确认 8000 端口服务已启动。"}
              />
              <StatusCard
                label="可用 Provider"
                value={`${readyProviders.length} / ${providers.length}`}
                tone={readyProviders.length > 0 ? "#f2bf6d" : "#ff8f72"}
                detail={
                  readyProviders.length > 0
                    ? `默认优先使用 ${readyProviders[0].name}`
                    : "至少配置一个带 API Key 的 Provider 才能开局。"
                }
              />
            </div>

            <nav className="nav-list rail-expand-only">
              {navItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-card${isActive ? " active" : ""}`}>
                  <div className="nav-sigil">{item.short}</div>
                  <div className="nav-title">{item.label}</div>
                  <div className="nav-desc">{item.desc}</div>
                </NavLink>
              ))}
            </nav>
          </div>
        </aside>

        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function StatusCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: string;
}) {
  return (
    <div className="status-card">
      <div className="status-head">
        <span className="status-label">{label}</span>
        <span className="status-value" style={{ color: tone }}>
          <span className="status-dot" style={{ background: tone }} />
          {value}
        </span>
      </div>
      <div className="status-detail">{detail}</div>
    </div>
  );
}
