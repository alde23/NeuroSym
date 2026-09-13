import { Link } from "@tanstack/react-router";
import {
  BarChart3,
  BookOpenCheck,
  MessagesSquare,
  ScanSearch,
  Settings2,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { FeasibilityVerdict } from "@/lib/neurosym/types";

const NAV: { to: string; label: string; caption: string; icon: LucideIcon }[] = [
  { to: "/", label: "Evaluator", caption: "Feasibility", icon: ScanSearch },
  { to: "/advisor", label: "Advisor", caption: "Live chat", icon: MessagesSquare },
  { to: "/explorer", label: "Explorer", caption: "CORDIS data", icon: BarChart3 },
  { to: "/rules", label: "Rules", caption: "Statutes & schema", icon: BookOpenCheck },
  { to: "/settings", label: "Settings", caption: "API config", icon: Settings2 },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <div className="flex items-center gap-3 border-b border-sidebar-border px-5 py-5">
          <div className="grid size-9 place-items-center rounded-lg bg-primary/15 ring-1 ring-primary/40">
            <span className="font-mono text-sm font-bold text-primary">NS</span>
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">NeuroSym</div>
            <div className="text-[11px] text-muted-foreground">Horizon Europe engine</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV.map(({ to, label, caption, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: to === "/" }}
              className="group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
              activeProps={{ className: "bg-sidebar-accent text-foreground" }}
            >
              <Icon className="size-4 shrink-0" />
              <span className="flex flex-col leading-tight">
                <span className="font-medium">{label}</span>
                <span className="text-[11px] text-muted-foreground">{caption}</span>
              </span>
            </Link>
          ))}
        </nav>

        <div className="border-t border-sidebar-border px-5 py-4 text-[11px] leading-relaxed text-muted-foreground">
          Neuro-symbolic feasibility &amp; CORDIS analytics. Every verdict is grounded in the rule
          registry and empirical benchmarks.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <nav className="flex gap-1 overflow-x-auto border-b border-border bg-sidebar px-3 py-2 md:hidden">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: to === "/" }}
              className="flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-xs text-muted-foreground"
              activeProps={{ className: "bg-sidebar-accent text-foreground" }}
            >
              <Icon className="size-3.5" />
              {label}
            </Link>
          ))}
        </nav>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="panel-grid border-b border-border px-6 py-8 md:px-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-primary">{eyebrow}</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight accent-text">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        </div>
        {actions}
      </div>
    </header>
  );
}

export function SourceBadge({ source }: { source: "live" | "demo" | null }) {
  if (!source) return null;
  const live = source === "live";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px]",
        live
          ? "border-feasible/40 bg-feasible/10 text-feasible"
          : "border-conditional/40 bg-conditional/10 text-conditional",
      )}
    >
      <span className={cn("size-1.5 rounded-full", live ? "bg-feasible" : "bg-conditional")} />
      {live ? "live backend" : "demo data"}
    </span>
  );
}

const VERDICT_STYLES: Record<FeasibilityVerdict, string> = {
  FEASIBLE: "border-feasible/40 bg-feasible/10 text-feasible",
  "CONDITIONALLY FEASIBLE": "border-conditional/40 bg-conditional/10 text-conditional",
  INFEASIBLE: "border-infeasible/40 bg-infeasible/10 text-infeasible",
  OUT_OF_DOMAIN: "border-border bg-muted text-muted-foreground",
};

export function VerdictBadge({
  verdict,
  className,
}: {
  verdict: FeasibilityVerdict;
  className?: string | undefined;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider",
        VERDICT_STYLES[verdict] ?? VERDICT_STYLES.OUT_OF_DOMAIN,
        className,
      )}
    >
      {verdict.replace(/_/g, " ")}
    </span>
  );
}

export function Panel({
  title,
  subtitle,
  icon: Icon,
  children,
  className,
}: {
  title?: string | undefined;
  subtitle?: string | undefined;
  icon?: LucideIcon | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card/70 backdrop-blur", className)}>
      {title ? (
        <div className="flex items-center gap-2.5 border-b border-border px-5 py-3.5">
          {Icon ? <Icon className="size-4 text-primary" /> : null}
          <div>
            <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
            {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
          </div>
        </div>
      ) : null}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string | undefined;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/40 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-lg text-foreground">{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
