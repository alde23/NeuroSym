import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Activity, CheckCircle2, Loader2, Save, XCircle } from "lucide-react";

import { AppShell, PageHeader, Panel, SourceBadge, Stat } from "@/components/neurosym/shell";
import {
  DEFAULT_BACKEND_URL,
  api,
  getBackendUrl,
  getMode,
  setBackendUrl,
  setMode,
  type ApiMode,
} from "@/lib/neurosym/api";
import type { HealthResponse } from "@/lib/neurosym/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "API Settings — NeuroSym Backend Configuration" },
      {
        name: "description",
        content:
          "Point the NeuroSym console at your FastAPI backend, run a live health check on DuckDB and Duckling, or switch to standalone demo data.",
      },
      { property: "og:title", content: "API Settings — NeuroSym Backend Configuration" },
      {
        property: "og:description",
        content: "Configure the backend URL, check service health and toggle standalone demo data.",
      },
    ],
  }),
  component: SettingsPage,
});

const MODES: { value: ApiMode; label: string; desc: string }[] = [
  { value: "auto", label: "Automatic", desc: "Use the backend when reachable, otherwise fall back to demo data." },
  { value: "live", label: "Live only", desc: "Always call the backend and surface errors instead of falling back." },
  { value: "demo", label: "Demo only", desc: "Never call the backend; run entirely on built-in sample data." },
];

function SettingsPage() {
  const [url, setUrl] = useState(DEFAULT_BACKEND_URL);
  const [mode, setModeState] = useState<ApiMode>("auto");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [source, setSource] = useState<"live" | "demo" | null>(null);
  const [checking, setChecking] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setUrl(getBackendUrl());
    setModeState(getMode());
    void check();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function check() {
    setChecking(true);
    try {
      const res = await api.health();
      setHealth(res.data);
      setSource(res.source);
    } catch {
      setHealth(null);
      setSource(null);
    } finally {
      setChecking(false);
    }
  }

  function save() {
    setBackendUrl(url);
    setMode(mode);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    void check();
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Configuration"
        title="API settings"
        description="Connect this console to a running NeuroSym FastAPI instance, or keep it standalone on realistic sample data."
        actions={<SourceBadge source={source} />}
      />

      <div className="grid max-w-4xl gap-6 px-6 py-8 md:px-10">
        <Panel title="Backend endpoint">
          <label className="text-xs text-muted-foreground">Base URL</label>
          <div className="mt-2 flex flex-wrap gap-3">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={DEFAULT_BACKEND_URL}
              className="min-w-64 flex-1 bg-background/60 font-mono text-sm"
            />
            <Button onClick={save}>
              <Save className="size-4" /> {saved ? "Saved" : "Save"}
            </Button>
            <Button variant="secondary" onClick={() => void check()} disabled={checking}>
              {checking ? <Loader2 className="size-4 animate-spin" /> : <Activity className="size-4" />}
              Check health
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Run the engine locally with <span className="font-mono text-foreground/80">uvicorn neurosym.api.server:app --port 8000</span>. The
            console calls /api/evaluate, /api/chat/stream, /api/sessions, /api/query, /api/rules, /api/schema and /api/health.
          </p>
        </Panel>

        <Panel title="Data source mode">
          <div className="grid gap-3 sm:grid-cols-3">
            {MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => setModeState(m.value)}
                className={cn(
                  "rounded-lg border border-border bg-background/40 p-4 text-left transition-colors hover:border-primary/40",
                  mode === m.value && "border-primary/70 bg-accent/40",
                )}
              >
                <div className="text-sm font-medium">{m.label}</div>
                <div className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{m.desc}</div>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Changes take effect after saving and are remembered in this browser.
          </p>
        </Panel>

        <Panel title="Service health" icon={Activity}>
          {health ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Status" value={health.status} />
                <Stat label="Rules loaded" value={health.rules_count} />
                <HealthFlag label="DuckDB" ok={health.duckdb_connected} />
                <HealthFlag label="Duckling NLP" ok={health.duckling_service_connected} />
              </div>
              <div className="mt-4 rounded-lg border border-border bg-background/60 px-4 py-3 font-mono text-[11px] text-muted-foreground">
                database: {health.database_path}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              {checking ? "Checking…" : "No health response. Save a reachable backend URL and check again."}
            </p>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}

function HealthFlag({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-background/40 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 flex items-center gap-2 font-mono text-sm",
          ok ? "text-feasible" : "text-infeasible",
        )}
      >
        {ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
        {ok ? "connected" : "unavailable"}
      </div>
    </div>
  );
}
