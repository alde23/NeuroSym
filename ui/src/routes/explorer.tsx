import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ChevronDown, Database, Loader2, Search, Terminal } from "lucide-react";

import { AppShell, PageHeader, Panel, SourceBadge, Stat } from "@/components/neurosym/shell";
import { BenchmarkPanel } from "@/components/neurosym/benchmarks";
import { api, formatEur } from "@/lib/neurosym/api";
import type { QueryResult } from "@/lib/neurosym/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/explorer")({
  head: () => ({
    meta: [
      { title: "CORDIS Explorer — Horizon Europe Data Analytics | NeuroSym" },
      {
        name: "description",
        content:
          "Query the CORDIS Horizon Europe dataset in natural language, inspect the generated SQL and benchmark budgets, consortium sizes and durations.",
      },
      { property: "og:title", content: "CORDIS Explorer — Horizon Europe Data Analytics" },
      {
        property: "og:description",
        content:
          "Natural-language search over funded Horizon Europe projects with generated SQL and statistical benchmarking.",
      },
    ],
  }),
  component: ExplorerPage,
});

const EXAMPLES = [
  "Innovation actions on hydrogen above 5 million EUR",
  "Quantum computing research projects coordinated in Denmark",
  "CSA projects on climate neutrality",
  "Battery recycling projects with Swedish partners",
];

function ExplorerPage() {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [source, setSource] = useState<"live" | "demo" | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function run(text: string) {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.query(text.trim());
      setResult(res.data);
      setSource(res.source);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="CORDIS analytics"
        title="Explore funded Horizon Europe projects"
        description="Natural language is mapped to an intent schema, compiled to parameterised DuckDB SQL and executed against the CORDIS dataset. The generated SQL is always shown."
        actions={<SourceBadge source={source} />}
      />

      <div className="space-y-6 px-6 py-8 md:px-10">
        <Panel title="Query" icon={Search}>
          <div className="flex flex-wrap gap-3">
            <Input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void run(prompt)}
              placeholder="e.g. innovation actions on hydrogen above 5 million EUR"
              className="min-w-64 flex-1 bg-background/60"
            />
            <Button onClick={() => void run(prompt)} disabled={loading || !prompt.trim()}>
              {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              Run query
            </Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setPrompt(ex);
                  void run(ex);
                }}
                className="rounded-full border border-border bg-background/50 px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </Panel>

        {error ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-5 py-4 text-sm text-destructive">
            Query failed: {error}
          </div>
        ) : null}

        {result ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <Stat label="Matches" value={result.total_matches} hint={`entity: ${result.target_entity}`} />
              <Stat label="Execution" value={`${result.execution_time_ms} ms`} hint="DuckDB" />
              <Stat
                label="Total EU contribution"
                value={formatEur(
                  result.records.reduce((sum, r) => sum + (Number(r["ecMaxContribution"]) || 0), 0),
                )}
                hint="across returned rows"
              />
            </div>

            <Panel title="Generated SQL" icon={Terminal}>
              <pre className="scroll-slim overflow-x-auto rounded-lg border border-border bg-background/60 p-4 font-mono text-xs leading-relaxed text-foreground/85">
                {result.generated_sql}
              </pre>
            </Panel>

            <Panel title="Results" subtitle={`${result.records.length} row(s)`} icon={Database}>
              <div className="scroll-slim overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="px-2 py-2 font-medium">Acronym</th>
                      <th className="px-2 py-2 font-medium">Title</th>
                      <th className="px-2 py-2 font-medium">Scheme</th>
                      <th className="px-2 py-2 text-right font-medium">EU grant</th>
                      <th className="px-2 py-2 font-medium">Period</th>
                      <th className="px-2 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {result.records.map((r, i) => {
                      const id = String(r["id"] ?? i);
                      const expanded = open === id;
                      return (
                        <tr key={id} className="border-b border-border/60 align-top last:border-0">
                          <td colSpan={6} className="p-0">
                            <div
                              className="grid cursor-pointer grid-cols-[110px_minmax(0,1fr)_130px_110px_150px_32px] items-center gap-2 px-2 py-3 transition-colors hover:bg-accent/30"
                              onClick={() => setOpen(expanded ? null : id)}
                            >
                              <span className="font-mono text-xs text-primary">{String(r["acronym"] ?? "—")}</span>
                              <span className="truncate text-xs text-foreground/85">{String(r["title"] ?? "")}</span>
                              <span className="font-mono text-[11px] text-muted-foreground">
                                {String(r["fundingScheme"] ?? "—")}
                              </span>
                              <span className="text-right font-mono text-xs">
                                {formatEur(Number(r["ecMaxContribution"]) || null)}
                              </span>
                              <span className="font-mono text-[11px] text-muted-foreground">
                                {String(r["startDate"] ?? "?").slice(0, 7)} → {String(r["endDate"] ?? "?").slice(0, 7)}
                              </span>
                              <ChevronDown
                                className={cn(
                                  "size-4 text-muted-foreground transition-transform",
                                  expanded && "rotate-180",
                                )}
                              />
                            </div>

                            {expanded ? (
                              <div className="grid gap-5 border-t border-border/60 bg-background/40 px-4 py-4 md:grid-cols-2">
                                <div>
                                  <div className="mb-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                                    Top organisations
                                  </div>
                                  <ul className="space-y-2">
                                    {(r.top_organizations ?? []).map((o, oi) => (
                                      <li key={oi} className="flex items-center justify-between gap-3 text-xs">
                                        <span className="truncate">
                                          <span className="font-mono text-[11px] text-muted-foreground">
                                            {o.country}
                                          </span>{" "}
                                          {o.name}
                                          {o.role === "coordinator" ? (
                                            <span className="ml-2 rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                                              coordinator
                                            </span>
                                          ) : null}
                                          {o.SME ? (
                                            <span className="ml-1.5 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                                              SME
                                            </span>
                                          ) : null}
                                        </span>
                                        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                                          {formatEur(o.ecContribution ?? null)}
                                        </span>
                                      </li>
                                    ))}
                                    {!(r.top_organizations ?? []).length ? (
                                      <li className="text-xs text-muted-foreground">No organisation rows returned.</li>
                                    ) : null}
                                  </ul>
                                </div>
                                <div>
                                  <div className="mb-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                                    EuroSciVoc topics
                                  </div>
                                  <div className="flex flex-wrap gap-1.5">
                                    {(r.euroSciVoc_topics ?? []).map((t) => (
                                      <span
                                        key={t}
                                        className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground"
                                      >
                                        {t}
                                      </span>
                                    ))}
                                  </div>
                                  <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
                                    <div>
                                      Grant ID <span className="font-mono text-foreground/80">{String(r["id"])}</span>
                                    </div>
                                    <div>
                                      Status <span className="font-mono text-foreground/80">{String(r["status"] ?? "—")}</span>
                                    </div>
                                    <div>
                                      Total cost{" "}
                                      <span className="font-mono text-foreground/80">
                                        {formatEur(Number(r["totalCost"]) || null)}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>

            {result.statistics ? <BenchmarkPanel stats={result.statistics} /> : null}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
