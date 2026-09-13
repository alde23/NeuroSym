import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { BookOpenCheck, Database, Search, Table2 } from "lucide-react";

import { AppShell, PageHeader, Panel, SourceBadge, Stat } from "@/components/neurosym/shell";
import { api } from "@/lib/neurosym/api";
import type { MasterSchemaDoc, Rule, RulesCatalog } from "@/lib/neurosym/types";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/rules")({
  head: () => ({
    meta: [
      { title: "Rules & Schema — EU Horizon Europe Statutes | NeuroSym" },
      {
        name: "description",
        content:
          "Browse the Horizon Europe eligibility rule registry — General Annex B statutes, CORDIS benchmarks and internal policy — plus the CORDIS master schema.",
      },
      { property: "og:title", content: "Rules & Schema — EU Horizon Europe Statutes" },
      {
        property: "og:description",
        content:
          "Every statutory rule, benchmark and policy NeuroSym applies, alongside the queryable CORDIS entity schema.",
      },
    ],
  }),
  component: RulesPage,
});

const SEVERITY_STYLE: Record<string, string> = {
  error: "border-infeasible/40 bg-infeasible/10 text-infeasible",
  warning: "border-conditional/40 bg-conditional/10 text-conditional",
  info: "border-primary/40 bg-primary/10 text-primary",
};

const SOURCE_LABEL: Record<string, string> = {
  official: "Official statute",
  benchmark: "CORDIS benchmark",
  policy: "Internal policy",
};

function RulesPage() {
  const [catalog, setCatalog] = useState<RulesCatalog | null>(null);
  const [schema, setSchema] = useState<MasterSchemaDoc | null>(null);
  const [source, setSource] = useState<"live" | "demo" | null>(null);
  const [search, setSearch] = useState("");
  const [entity, setEntity] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([api.rules(), api.schema()]).then(([r, s]) => {
      setCatalog(r.data);
      setSchema(s.data);
      setSource(r.source === "live" && s.source === "live" ? "live" : "demo");
      setEntity(Object.keys(s.data.entities)[0] ?? null);
    });
  }, []);

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rules = (catalog?.rules ?? []).filter(
      (r) =>
        !q ||
        `${r.rule_id} ${r.name} ${r.message} ${r.reference} ${r.field}`.toLowerCase().includes(q),
    );
    return ["official", "benchmark", "policy"].map((src) => ({
      src,
      rules: rules.filter((r) => r.source === src),
    }));
  }, [catalog, search]);

  const activeEntity = entity && schema ? schema.entities[entity] : undefined;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Knowledge base"
        title="Statutory rules & data schema"
        description="The deterministic backbone of every verdict: the Horizon Europe rule registry served by /api/rules and the CORDIS master schema served by /api/schema."
        actions={<SourceBadge source={source} />}
      />

      <div className="px-6 py-8 md:px-10">
        <Tabs defaultValue="rules">
          <TabsList>
            <TabsTrigger value="rules">
              <BookOpenCheck className="mr-2 size-4" /> Rule registry
            </TabsTrigger>
            <TabsTrigger value="schema">
              <Database className="mr-2 size-4" /> Master schema
            </TabsTrigger>
          </TabsList>

          <TabsContent value="rules" className="mt-6 space-y-6">
            {catalog ? (
              <>
                <Panel>
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="max-w-xl">
                      <h2 className="text-sm font-semibold">{catalog.domain}</h2>
                      <p className="mt-1 text-xs text-muted-foreground">{catalog.description}</p>
                    </div>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search rules…"
                        className="w-64 bg-background/60 pl-9"
                      />
                    </div>
                  </div>
                </Panel>

                {grouped.map(({ src, rules }) =>
                  rules.length ? (
                    <Panel key={src} title={SOURCE_LABEL[src]} subtitle={`${rules.length} rule(s)`}>
                      <div className="space-y-3">
                        {rules.map((r) => (
                          <RuleCard key={r.rule_id} rule={r} />
                        ))}
                      </div>
                    </Panel>
                  ) : null,
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Loading rule registry…</p>
            )}
          </TabsContent>

          <TabsContent value="schema" className="mt-6 space-y-6">
            {schema ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Stat label="Schema version" value={schema.version} hint={schema.database_file} />
                  <Stat label="Entities" value={Object.keys(schema.entities).length} />
                  <Stat
                    label="Total rows"
                    value={Object.values(schema.entities)
                      .reduce((a, e) => a + (e.row_count ?? 0), 0)
                      .toLocaleString()}
                  />
                </div>

                <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
                  <div className="space-y-2">
                    {Object.values(schema.entities).map((e) => (
                      <button
                        key={e.name}
                        onClick={() => setEntity(e.name)}
                        className={cn(
                          "w-full rounded-lg border border-border bg-card/60 px-3 py-2.5 text-left transition-colors hover:border-primary/40",
                          entity === e.name && "border-primary/60 bg-accent/40",
                        )}
                      >
                        <div className="font-mono text-xs text-primary">{e.table_name}</div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                          {Object.keys(e.parameters).length} columns · {e.row_count.toLocaleString()} rows
                        </div>
                      </button>
                    ))}
                  </div>

                  {activeEntity ? (
                    <Panel
                      title={activeEntity.table_name}
                      subtitle={activeEntity.description}
                      icon={Table2}
                    >
                      <div className="scroll-slim overflow-x-auto">
                        <table className="w-full min-w-[640px] text-left text-xs">
                          <thead>
                            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-muted-foreground">
                              <th className="px-2 py-2 font-medium">Column</th>
                              <th className="px-2 py-2 font-medium">SQL type</th>
                              <th className="px-2 py-2 font-medium">Semantic</th>
                              <th className="px-2 py-2 font-medium">Description</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.values(activeEntity.parameters).map((p) => (
                              <tr key={p.name} className="border-b border-border/50 last:border-0">
                                <td className="px-2 py-2.5 font-mono text-primary">
                                  {p.name}
                                  {activeEntity.primary_key === p.name ? (
                                    <span className="ml-1.5 rounded border border-border px-1 text-[9px] text-muted-foreground">
                                      PK
                                    </span>
                                  ) : null}
                                  {activeEntity.foreign_keys[p.name] ? (
                                    <span className="ml-1.5 rounded border border-border px-1 text-[9px] text-muted-foreground">
                                      FK
                                    </span>
                                  ) : null}
                                </td>
                                <td className="px-2 py-2.5 font-mono text-muted-foreground">{p.sql_type}</td>
                                <td className="px-2 py-2.5 font-mono text-muted-foreground">
                                  {p.semantic_type}
                                  {p.unit ? ` (${p.unit})` : ""}
                                </td>
                                <td className="px-2 py-2.5 text-foreground/80">
                                  {p.description}
                                  {p.vocabulary?.length ? (
                                    <div className="mt-1 flex flex-wrap gap-1">
                                      {p.vocabulary.slice(0, 8).map((v) => (
                                        <span
                                          key={v}
                                          className="rounded bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                                        >
                                          {v}
                                        </span>
                                      ))}
                                    </div>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </Panel>
                  ) : null}
                </div>

                {schema.join_paths?.length ? (
                  <Panel title="Join paths">
                    <ul className="space-y-2">
                      {schema.join_paths.map((j, i) => (
                        <li key={i} className="font-mono text-xs text-muted-foreground">
                          <span className="text-primary">{j.from_entity}</span> →{" "}
                          <span className="text-primary">{j.to_entity}</span>
                          {j.on ? <span className="ml-2 text-foreground/70">ON {j.on}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </Panel>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Loading master schema…</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}

function RuleCard({ rule }: { rule: Rule }) {
  return (
    <div className="rounded-lg border border-border bg-background/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-primary">{rule.rule_id}</span>
        <span className="font-mono text-xs text-foreground/80">{rule.name}</span>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase",
            SEVERITY_STYLE[rule.severity],
          )}
        >
          {rule.severity}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-foreground/90">{rule.message}</p>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[11px] text-muted-foreground">
        <span>
          condition: {rule.field} {rule.op} {JSON.stringify(rule.value)}
        </span>
        {rule.applies_when ? (
          <span>
            applies when: {rule.applies_when.field} {rule.applies_when.op}{" "}
            {JSON.stringify(rule.applies_when.value)}
          </span>
        ) : null}
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">Reference: {rule.reference}</div>
      {rule.evidence ? (
        <div className="mt-1 text-[11px] text-muted-foreground">Evidence: {rule.evidence}</div>
      ) : null}
    </div>
  );
}
