import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Loader2, MessageSquarePlus, Send, Sparkle, Trash2 } from "lucide-react";

import { AppShell, PageHeader, Panel, SourceBadge, Stat, VerdictBadge } from "@/components/neurosym/shell";
import { BudgetDistribution } from "@/components/neurosym/benchmarks";
import { api, formatEur, streamChat } from "@/lib/neurosym/api";
import type { ChatResponse, FeasibilityVerdict, SessionSummary } from "@/lib/neurosym/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/advisor")({
  head: () => ({
    meta: [
      { title: "Grant Advisor — Real-Time Horizon Europe Consultation | NeuroSym" },
      {
        name: "description",
        content:
          "Multi-turn streaming advisor for EU Horizon Europe proposals: live feasibility verdicts, evidence, benchmarks and comparable funded projects.",
      },
      { property: "og:title", content: "Grant Advisor — Real-Time Horizon Europe Consultation" },
      {
        property: "og:description",
        content:
          "Ask about consortium eligibility, budgets and call fit, and get grounded answers streamed turn by turn.",
      },
    ],
  }),
  component: AdvisorPage,
});

interface Turn {
  role: "user" | "assistant";
  content: string;
  payload?: ChatResponse;
}

const STARTERS = [
  "Is a 3-partner RIA consortium from DE, FR and ES eligible?",
  "We want 12 million EUR for an innovation action on battery recycling over 48 months — is that realistic?",
  "What is the median budget for Horizon Europe CSA projects?",
];

function AdvisorPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [source, setSource] = useState<"live" | "demo" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void api.sessions().then((r) => {
      setSessions(r.data.sessions);
      setSource(r.source);
    });
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const latest = [...turns].reverse().find((t) => t.payload)?.payload;

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;
    setInput("");
    setError(null);
    setStreaming(true);
    setTurns((t) => [...t, { role: "user", content: message }, { role: "assistant", content: "" }]);

    const used = await streamChat(message, activeId, latest?.proposal_context, {
      onChunk: (delta) =>
        setTurns((t) => {
          const next = [...t];
          const last = next[next.length - 1]!;
          next[next.length - 1] = { ...last, content: last.content + delta };
          return next;
        }),
      onComplete: (payload) => {
        setTurns((t) => {
          const next = [...t];
          const last = next[next.length - 1]!;
          next[next.length - 1] = { ...last, content: payload.reply, payload };
          return next;
        });
        setActiveId(payload.session_id);
        setSessions((s) => {
          const title = message.slice(0, 45) + (message.length > 45 ? "..." : "");
          const existing = s.find((x) => x.session_id === payload.session_id);
          const now = new Date().toISOString();
          if (existing) {
            return s.map((x) =>
              x.session_id === payload.session_id
                ? { ...x, updated_at: now, message_count: x.message_count + 2, verdict: payload.verdict }
                : x,
            );
          }
          return [
            {
              session_id: payload.session_id,
              title,
              created_at: now,
              updated_at: now,
              message_count: 2,
              verdict: payload.verdict,
              topic: payload.proposal_context.domain_topic ?? "Horizon Europe",
            },
            ...s,
          ];
        });
      },
      onError: (msg) => setError(msg),
    });
    setSource(used);
    setStreaming(false);
  }

  function newSession() {
    setActiveId(null);
    setTurns([]);
    setError(null);
  }

  async function removeSession(id: string) {
    await api.deleteSession(id);
    setSessions((s) => s.filter((x) => x.session_id !== id));
    if (activeId === id) newSession();
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Conversational advisor"
        title="Real-time grant advisor"
        description="Multi-turn consultation over /api/chat/stream. Proposal state accumulates across turns and every reply carries a live feasibility verdict with its evidence."
        actions={<SourceBadge source={source} />}
      />

      <div className="grid gap-6 px-6 py-8 md:px-10 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        {/* Sessions */}
        <aside className="space-y-3">
          <Button variant="secondary" className="w-full justify-start" onClick={newSession}>
            <MessageSquarePlus className="size-4" /> New consultation
          </Button>
          <div className="space-y-2">
            {sessions.map((s) => (
              <div
                key={s.session_id}
                className={cn(
                  "group rounded-lg border border-border bg-card/60 p-3 transition-colors hover:border-primary/40",
                  activeId === s.session_id && "border-primary/60 bg-accent/40",
                )}
              >
                <button className="w-full text-left" onClick={() => setActiveId(s.session_id)}>
                  <div className="truncate text-xs font-medium">{s.title}</div>
                  <div className="mt-1.5 flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-[10px] text-muted-foreground">{s.topic}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{s.message_count} msg</span>
                  </div>
                  <VerdictBadge verdict={s.verdict as FeasibilityVerdict} className="mt-2 text-[10px]" />
                </button>
                <button
                  onClick={() => void removeSession(s.session_id)}
                  className="mt-2 inline-flex items-center gap-1 text-[10px] text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                >
                  <Trash2 className="size-3" /> reset session
                </button>
              </div>
            ))}
            {sessions.length === 0 ? (
              <p className="text-xs text-muted-foreground">No consultations yet.</p>
            ) : null}
          </div>
        </aside>

        {/* Conversation */}
        <section className="flex min-h-[560px] flex-col rounded-xl border border-border bg-card/60">
          <div ref={scrollRef} className="scroll-slim flex-1 space-y-5 overflow-y-auto p-5">
            {turns.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
                <div className="grid size-12 place-items-center rounded-xl bg-primary/15 ring-1 ring-primary/40">
                  <Sparkle className="size-5 text-primary" />
                </div>
                <div className="max-w-sm text-sm text-muted-foreground">
                  Ask about consortium eligibility, budget realism, call fit or coordinator duties. Answers are
                  grounded in the rule registry and CORDIS benchmarks.
                </div>
                <div className="flex flex-wrap justify-center gap-2">
                  {STARTERS.map((q) => (
                    <button
                      key={q}
                      onClick={() => void send(q)}
                      className="max-w-xs truncate rounded-full border border-border bg-background/50 px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                    {t.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="space-y-3">
                  {t.payload ? <VerdictBadge verdict={t.payload.verdict} /> : null}
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                    {t.content}
                    {streaming && i === turns.length - 1 ? (
                      <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-middle" />
                    ) : null}
                  </div>
                  {t.payload?.suggested_followups.length ? (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {t.payload.suggested_followups.map((f) => (
                        <button
                          key={f}
                          onClick={() => void send(f)}
                          className="rounded-full border border-border bg-background/50 px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground"
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ),
            )}

            {error ? <div className="text-sm text-destructive">Stream error: {error}</div> : null}
          </div>

          <div className="border-t border-border p-4">
            <div className="flex items-end gap-3">
              <Textarea
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(input);
                  }
                }}
                placeholder="Describe your proposal or ask a follow-up…"
                className="resize-none bg-background/60 text-sm"
              />
              <Button size="icon" onClick={() => void send(input)} disabled={streaming || !input.trim()}>
                {streaming ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
              </Button>
            </div>
          </div>
        </section>

        {/* Evidence drawer */}
        <aside className="space-y-4">
          {latest ? (
            <>
              <Panel title="Live proposal state">
                <div className="grid gap-2">
                  <Stat label="Scheme" value={latest.proposal_context.funding_scheme ?? "—"} />
                  <Stat
                    label="Partners"
                    value={latest.proposal_context.partner_count ?? "—"}
                    hint={latest.proposal_context.countries.join(", ") || undefined}
                  />
                  <Stat label="Budget" value={formatEur(latest.proposal_context.requested_budget_eur)} />
                </div>
              </Panel>

              {latest.domain_statistics ? (
                <Panel title="Benchmark" subtitle={`${latest.domain_statistics.comparable_project_count.toLocaleString()} projects`}>
                  <BudgetDistribution
                    stats={latest.domain_statistics}
                    requested={latest.proposal_context.requested_budget_eur}
                  />
                </Panel>
              ) : null}

              <Panel title="Evidence this turn">
                <EvidenceGroup label="Regulatory" items={latest.regulatory_evidence} />
                <EvidenceGroup label="Empirical" items={latest.empirical_evidence} />
                <EvidenceGroup label="Operational" items={latest.operational_evidence} />
                <EvidenceGroup label="Risks" items={latest.feasibility_risks} />
                <EvidenceGroup label="Required actions" items={latest.required_actions} />
              </Panel>

              {latest.comparable_projects.length ? (
                <Panel title="Comparable funded projects">
                  <ul className="space-y-3">
                    {latest.comparable_projects.map((p, i) => {
                      const rec = p as { acronym?: string; title?: string; ecMaxContribution?: number };
                      return (
                        <li key={i} className="border-b border-border pb-2.5 last:border-0 last:pb-0">
                          <div className="font-mono text-xs text-primary">{rec.acronym ?? "project"}</div>
                          <div className="text-xs text-muted-foreground">{rec.title}</div>
                          <div className="mt-1 font-mono text-[11px] text-foreground/70">
                            {formatEur(rec.ecMaxContribution ?? null)}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </Panel>
              ) : null}
            </>
          ) : (
            <Panel title="Evidence">
              <p className="text-xs text-muted-foreground">
                Evidence, statistics and comparable projects appear here once the advisor replies.
              </p>
            </Panel>
          )}
        </aside>
      </div>
    </AppShell>
  );
}

function EvidenceGroup({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mb-4 last:mb-0">
      <div className="mb-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="text-[11px] leading-relaxed text-foreground/80">
            • {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
