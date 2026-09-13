import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  AlertTriangle,
  BookMarked,
  CheckCircle2,
  Database,
  Gavel,
  Loader2,
  ScanSearch,
  ShieldCheck,
  Wrench,
} from "lucide-react";

import { AppShell, PageHeader, Panel, SourceBadge, Stat, VerdictBadge } from "@/components/neurosym/shell";
import { BenchmarkPanel } from "@/components/neurosym/benchmarks";
import { api, formatEur } from "@/lib/neurosym/api";
import type { SynthesizedReport } from "@/lib/neurosym/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "NeuroSym — Horizon Europe Proposal Feasibility Evaluator" },
      {
        name: "description",
        content:
          "Evaluate an EU Horizon Europe proposal against General Annex B eligibility rules and CORDIS empirical benchmarks, with a grounded feasibility verdict.",
      },
      { property: "og:title", content: "NeuroSym — Horizon Europe Proposal Feasibility Evaluator" },
      {
        property: "og:description",
        content:
          "Grounded feasibility verdicts for Horizon Europe proposals: eligibility rules, CORDIS benchmarks, risks and required actions.",
      },
    ],
  }),
  component: EvaluatorPage,
});

const EXAMPLES = [
  "We plan a Horizon Europe RIA on clean hydrogen electrolysers with 7 partners from Germany, France, Spain and Norway, requesting 5 million EUR over 42 months. We would coordinate.",
  "Innovation action on battery recycling, consortium of 12 organisations across Sweden, Belgium and Poland, 18 million EUR, 48 months.",
  "A quantum computing RIA with only 2 partners from Denmark and the United States, 4 million EUR, 36 months.",
];

function EvaluatorPage() {
  const [prompt, setPrompt] = useState("");
  const [report, setReport] = useState<SynthesizedReport | null>(null);
  const [source, setSource] = useState<"live" | "demo" | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function evaluate(text: string) {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.evaluate(text.trim());
      setReport(res.data);
      setSource(res.source);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const ctx = report?.proposal_context;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Proposal feasibility"
        title="Evaluate a Horizon Europe proposal"
        description="Describe the planned action in plain language. NeuroSym extracts the consortium parameters, checks them against the statutory rule registry and benchmarks them against funded CORDIS projects."
        actions={<SourceBadge source={source} />}
      />

      <div className="space-y-6 px-6 py-8 md:px-10">
        <Panel title="Proposal description" icon={ScanSearch}>
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
            placeholder="e.g. A Horizon Europe RIA on clean hydrogen with 7 partners from DE, FR, ES and NO, requesting 5 million EUR over 42 months…"
            className="resize-none bg-background/60 font-[inherit] text-sm"
          />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => void evaluate(prompt)} disabled={loading || !prompt.trim()}>
              {loading ? <Loader2 className="size-4 animate-spin" /> : <ScanSearch className="size-4" />}
              Run feasibility evaluation
            </Button>
            {report ? (
              <Button
                variant="ghost"
                onClick={() => {
                  setReport(null);
                  setPrompt("");
                  setSource(null);
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>

          <div className="mt-5 space-y-2">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Try an example</div>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => {
                    setPrompt(ex);
                    void evaluate(ex);
                  }}
                  className="max-w-md truncate rounded-full border border-border bg-background/50 px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        {error ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-5 py-4 text-sm text-destructive">
            Could not reach the NeuroSym backend: {error}
          </div>
        ) : null}

        {report ? (
          <>
            <Panel className="overflow-hidden">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-3xl">
                  <VerdictBadge verdict={report.verdict} />
                  <p className="mt-4 text-sm leading-relaxed text-foreground">{report.verdict_rationale}</p>
                </div>
                <div className="w-40 shrink-0">
                  <Stat label="Confidence" value={`${Math.round(report.confidence_score * 100)}%`} />
                </div>
              </div>

              {ctx ? (
                <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Stat label="Scheme" value={ctx.funding_scheme ?? "—"} />
                  <Stat
                    label="Partners"
                    value={ctx.partner_count ?? "—"}
                    hint={`${ctx.member_state_count} MS · ${ctx.associated_country_count} AC · ${ctx.third_country_count} third`}
                  />
                  <Stat
                    label="Requested budget"
                    value={formatEur(ctx.requested_budget_eur)}
                    hint={ctx.requested_duration_months ? `${ctx.requested_duration_months} months` : undefined}
                  />
                  <Stat label="Our role" value={ctx.our_role ?? "—"} hint={ctx.domain_topic ?? undefined} />
                </div>
              ) : null}

              {ctx?.countries.length ? (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {ctx.countries.map((c) => (
                    <span
                      key={c}
                      className="rounded border border-border bg-background/60 px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              ) : null}
            </Panel>

            <div className="grid gap-6 lg:grid-cols-3">
              <EvidenceList title="Regulatory" icon={Gavel} items={report.regulatory_evidence} />
              <EvidenceList title="Empirical" icon={Database} items={report.empirical_evidence} />
              <EvidenceList title="Operational" icon={Wrench} items={report.operational_evidence} />
            </div>

            {report.feasibility_risks.length || report.required_actions_for_feasibility.length ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <Panel title="Feasibility risks" icon={AlertTriangle}>
                  <BulletList items={report.feasibility_risks} tone="risk" empty="No risks detected." />
                </Panel>
                <Panel title="Required actions" icon={CheckCircle2}>
                  <BulletList
                    items={report.required_actions_for_feasibility}
                    tone="action"
                    empty="No corrective actions required."
                  />
                </Panel>
              </div>
            ) : null}

            {report.domain_statistics ? (
              <BenchmarkPanel
                stats={report.domain_statistics}
                requestedBudget={ctx?.requested_budget_eur}
                partnerCount={ctx?.partner_count}
                durationMonths={ctx?.requested_duration_months}
              />
            ) : null}

            <div className="grid gap-6 lg:grid-cols-2">
              <Panel title="Grounded citations" icon={BookMarked}>
                <BulletList items={report.grounded_citations} tone="muted" empty="No citations." />
              </Panel>
              <Panel title="Grounding audit" icon={ShieldCheck}>
                <div className="mb-3 flex items-center gap-2 text-xs">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] ${
                      report.is_grounded
                        ? "border-feasible/40 bg-feasible/10 text-feasible"
                        : "border-infeasible/40 bg-infeasible/10 text-infeasible"
                    }`}
                  >
                    {report.is_grounded ? "grounded" : "ungrounded claims detected"}
                  </span>
                </div>
                <BulletList
                  items={report.grounding_audit_notes}
                  tone="muted"
                  empty="Validator returned no notes."
                />
                {Object.keys(report.evidence_summary).length ? (
                  <pre className="scroll-slim mt-4 overflow-x-auto rounded-lg border border-border bg-background/60 p-3 font-mono text-[11px] text-muted-foreground">
                    {JSON.stringify(report.evidence_summary, null, 2)}
                  </pre>
                ) : null}
              </Panel>
            </div>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function EvidenceList({
  title,
  icon,
  items,
}: {
  title: string;
  icon: typeof Gavel;
  items: string[];
}) {
  return (
    <Panel title={`${title} evidence`} subtitle={`${items.length} finding(s)`} icon={icon}>
      <BulletList items={items} tone="muted" empty="No evidence in this dimension." />
    </Panel>
  );
}

export function BulletList({
  items,
  tone = "muted",
  empty,
}: {
  items: string[];
  tone?: "muted" | "risk" | "action";
  empty: string;
}) {
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  const dot =
    tone === "risk" ? "bg-infeasible" : tone === "action" ? "bg-primary" : "bg-muted-foreground/60";
  return (
    <ul className="space-y-2.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-3 text-sm leading-relaxed text-foreground/90">
          <span className={`mt-2 size-1.5 shrink-0 rounded-full ${dot}`} />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}
