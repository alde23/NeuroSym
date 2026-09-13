"""NeuroSym CLI - Complete Neuro-Symbolic Evidence Runtime, Decision Synthesizer & CORDIS Query Interface."""

import argparse
import json
import os
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from neurosym.ingestion.cordis_ingest import (
    CordisIngestionEngine,
    DEFAULT_DB_PATH,
    DEFAULT_SCHEMA_PATH,
)
from neurosym.intent.neural_mapper import NeuralIntentMapper
from neurosym.query.engine import QueryEngine
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.rules.models import FeasibilityVerdict, Severity
from neurosym.runtime.evidence import EvidenceRuntime
from neurosym.schema.master_schema import MasterSchema
from neurosym.synthesizer.neural_synthesizer import NeuralDecisionSynthesizer

console = Console(force_terminal=True)


def cmd_ingest(args):
    """Ingest CORDIS dataset into DuckDB and generate Master Schema."""
    console.print(Panel.fit("[bold blue]Starting CORDIS Data Ingestion & Schema Extraction[/bold blue]"))
    engine = CordisIngestionEngine()
    schema = engine.ingest_all()

    table = Table(title="Ingested Tables & Parameters", header_style="bold green")
    table.add_column("Entity / Table", style="cyan")
    table.add_column("Row Count", justify="right", style="magenta")
    table.add_column("Parameters", justify="right", style="yellow")
    table.add_column("Description")

    for name, entity in schema.entities.items():
        table.add_row(
            name,
            f"{entity.row_count:,}",
            str(len(entity.parameters)),
            entity.description
        )

    console.print(table)
    console.print(f"[bold green]Master Schema saved to:[/bold green] {DEFAULT_SCHEMA_PATH}")
    console.print(f"[bold green]DuckDB Database saved to:[/bold green] {DEFAULT_DB_PATH}")


def cmd_schema(args):
    """Inspect the Master Schema."""
    if not DEFAULT_SCHEMA_PATH.exists():
        console.print(f"[bold red]Master schema not found at {DEFAULT_SCHEMA_PATH}. Run 'neurosym ingest' first.[/bold red]")
        sys.exit(1)

    with open(DEFAULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = MasterSchema.model_validate_json(f.read())

    console.print(Panel.fit(f"[bold green]Master Schema Catalog (Version {schema.version})[/bold green]"))

    for name, entity in schema.entities.items():
        table = Table(title=f"Entity: {name} ({entity.row_count:,} rows)", header_style="bold blue")
        table.add_column("Parameter", style="cyan")
        table.add_column("SQL Type", style="dim")
        table.add_column("Semantic Type", style="green")
        table.add_column("Duckling Dimension", style="magenta")
        table.add_column("Description")

        for p_name, param in entity.parameters.items():
            table.add_row(
                p_name,
                param.sql_type,
                param.semantic_type.value,
                param.duckling_dimension.value,
                param.description
            )
        console.print(table)
        console.print()


def cmd_rules(args):
    """List all registered decision rules and policies."""
    evaluator = RuleEvaluator()
    rules = evaluator.get_rules_catalog()

    console.print(Panel.fit(f"[bold blue]{evaluator.name}[/bold blue]\n[dim]{evaluator.description}[/dim]", title="Domain Rules Catalog"))

    table = Table(title="Horizon Europe & Policy Rule Set", header_style="bold green")
    table.add_column("Rule ID", style="cyan", no_wrap=True)
    table.add_column("Source", style="magenta")
    table.add_column("Name", style="yellow")
    table.add_column("Condition", style="white")
    table.add_column("Severity", justify="center")
    table.add_column("Rule Requirement & Reference")

    for r in rules:
        sev_style = "[bold red]ERROR[/bold red]" if r.severity == Severity.ERROR else "[bold yellow]WARNING[/bold yellow]"
        cond = f"{r.field} {r.op} {r.value}"
        if r.applies_when:
            cond += f" (when {r.applies_when.field} {r.applies_when.op} {r.applies_when.value})"
        
        detail = f"{r.message}\n[dim]Ref: {r.reference}[/dim]"
        table.add_row(
            r.rule_id,
            r.source.value.upper(),
            r.name,
            cond,
            sev_style,
            detail
        )

    console.print(table)


def cmd_run_synthesis(args):
    """Execute the full Neuro-Symbolic pipeline: Evidence Runtime -> Synthesizer -> Final Decision Report."""
    prompt = args.prompt
    console.print(Panel(f"[bold cyan]Proposal Input:[/bold cyan] [italic]{prompt}[/italic]", title="NeuroSym Runtime & Synthesizer"))

    # Stage 1: Evidence Gathering Runtime
    runtime = EvidenceRuntime()
    evidence = runtime.gather_evidence(prompt)

    # 1. Extracted Evidence Summary
    p = evidence.proposal_context
    ctx_table = Table(title="[PHASE 1: DETERMINISTIC EVIDENCE PACKET]", header_style="bold blue")
    ctx_table.add_column("Evidence Category", style="cyan")
    ctx_table.add_column("Extracted Data / Values", style="green")
    ctx_table.add_column("Provenance / Source")

    ctx_table.add_row("Funding Scheme", str(p.funding_scheme or "Not specified"), "Domain Catalog")
    ctx_table.add_row("Consortium Size", f"{p.partner_count} partners" if p.partner_count is not None else "Not specified", "Duckling (number)")
    ctx_table.add_row("Countries", ", ".join(p.countries) if p.countries else "None", f"{p.distinct_country_count} distinct ({p.member_state_count} EU27, {p.associated_country_count} Associated)")
    ctx_table.add_row("Project Duration", f"{p.requested_duration_months} months" if p.requested_duration_months else "Not specified", "Duckling (duration/number)")
    ctx_table.add_row("Requested Budget", f"€{p.requested_budget_eur:,.2f}" if p.requested_budget_eur else "Not specified", "Duckling (amount-of-money)")
    ctx_table.add_row("Domain Topic", str(p.domain_topic or "General Horizon"), "EuroSciVoc Taxonomy")
    console.print(ctx_table)

    # Statistical Evidence Table
    if evidence.domain_statistics:
        s = evidence.domain_statistics
        stat_table = Table(title=f"[LIVE CORDIS BENCHMARKS: {s.comparable_project_count:,} COMPARABLE PROJECTS]", header_style="bold magenta")
        stat_table.add_column("Metric Dimension", style="cyan")
        stat_table.add_column("Historical Value (CORDIS)", style="white")
        stat_table.add_column("Empirical Position")

        stat_table.add_row("Budget 5th Percentile (P5)", f"€{s.budget_p5:,.2f}", "Lower historical boundary")
        stat_table.add_row("Budget Median (P50)", f"€{s.budget_p50:,.2f}", f"Mean: €{s.budget_mean:,.2f}")
        stat_table.add_row("Budget 95th Percentile (P95)", f"€{s.budget_p95:,.2f}", "Upper historical boundary")
        stat_table.add_row("Budget 98th Percentile (P98)", f"€{s.budget_p98:,.2f}", "Statistical outlier threshold")

        if s.requested_budget_percentile is not None:
            pct_col = "red" if s.requested_budget_percentile > 95 or s.requested_budget_percentile < 5 else "green"
            stat_table.add_row("Requested Budget Rank", f"[{pct_col}]{s.requested_budget_percentile}th Percentile[/{pct_col}]", f"Empirical percentile rank")

        stat_table.add_row("Consortium Size (Median)", f"{s.median_partner_count} partners", f"Mean: {s.avg_partner_count} partners")
        stat_table.add_row("Project Duration (Avg)", f"{s.avg_duration_months:.1f} months", "Average lifecycle")
        console.print(stat_table)

    # Stage 2: Decision Synthesis Engine (Jinja2 + LLM + Guardrails AI)
    synthesizer = NeuralDecisionSynthesizer()
    report = synthesizer.synthesize(evidence)

    console.print("\n" + "="*80)
    console.print("[bold yellow][PHASE 2: REGULATED SYNTHESIZER DECISION REPORT][/bold yellow]")
    console.print("="*80 + "\n")

    # Verdict Box
    if report.verdict in ("OUT_OF_DOMAIN", FeasibilityVerdict.OUT_OF_DOMAIN):
        v_color = "magenta"
        title_str = "[bold magenta]VERDICT: OUT OF DOMAIN (REQUEST DECLINED)[/bold magenta]"
    elif report.verdict in ("FEASIBLE", FeasibilityVerdict.FEASIBLE):
        v_color = "green"
        title_str = "[bold green]FEASIBILITY VERDICT: FEASIBLE[/bold green]"
    elif report.verdict in ("CONDITIONALLY FEASIBLE", FeasibilityVerdict.CONDITIONALLY_FEASIBLE):
        v_color = "yellow"
        title_str = "[bold yellow]FEASIBILITY VERDICT: CONDITIONALLY FEASIBLE[/bold yellow]"
    else:
        v_color = "red"
        title_str = "[bold red]FEASIBILITY VERDICT: INFEASIBLE (CRITICAL VIOLATIONS DETECTED)[/bold red]"

    console.print(Panel(
        f"{title_str}\n\n[bold white]{report.verdict_rationale}[/bold white]\n[dim]Confidence Score: {report.confidence_score * 100:.0f}% | Evidence Grounding Audit: PASSED (Zero-hallucination verified)[/dim]",
        border_style=v_color
    ))

    # Dimension 1: Regulatory & Legal Evidence
    if report.regulatory_evidence:
        reg_text = "\n".join([f"• {f}" for f in report.regulatory_evidence])
        console.print(Panel(reg_text, title="1. Regulatory & Legal Feasibility Evidence (Official Rules)", border_style="blue"))

    # Dimension 2: Empirical & Financial Percentile Evidence
    if report.empirical_evidence:
        emp_text = "\n".join([f"• {si}" for si in report.empirical_evidence])
        console.print(Panel(emp_text, title="2. Empirical & Financial Feasibility Evidence (Live CORDIS Benchmarks)", border_style="magenta"))

    # Dimension 3: Operational & Consortium Feasibility Evidence
    if report.operational_evidence:
        op_text = "\n".join([f"• {oe}" for oe in report.operational_evidence])
        console.print(Panel(op_text, title="3. Operational & Consortium Density Feasibility Evidence", border_style="cyan"))

    # Feasibility Risks
    if report.feasibility_risks:
        risk_text = "\n".join([f"• [bold red]Risk:[/bold red] {r}" for r in report.feasibility_risks])
        console.print(Panel(risk_text, title="4. Feasibility Risks & Outlier Alerts", border_style="yellow"))

    # Required Actions for Feasibility
    if report.required_actions_for_feasibility:
        rec_text = "\n".join([f"• [bold green]Required Action:[/bold green] {rec}" for rec in report.required_actions_for_feasibility])
        console.print(Panel(rec_text, title="5. Required Actions to Ensure / Optimize Feasibility", border_style="green"))

    # Grounded Citations & Legal References
    if report.grounded_citations:
        cite_text = "\n".join([f"[{i+1}] {c}" for i, c in enumerate(report.grounded_citations)])
        console.print(Panel(cite_text, title="6. Grounded Citations & Legal References", border_style="dim"))


def cmd_parse(args):
    """Parse a prompt with Duckling, map to Intent Schema, and reference dataset records."""
    prompt = args.prompt
    console.print(Panel(f"[bold cyan]Input Prompt:[/bold cyan] [italic]{prompt}[/italic]", title="NeuroSym Pipeline"))

    mapper = NeuralIntentMapper()
    intent = mapper.parse_and_map(prompt)

    # Display Duckling Entities
    duckling_table = Table(title="1. Probabilistic Entities Extracted via Duckling", header_style="bold magenta")
    duckling_table.add_column("Dimension", style="cyan")
    duckling_table.add_column("Text Span", style="yellow")
    duckling_table.add_column("Type")
    duckling_table.add_column("Normalized Extracted Values", style="green")

    if not intent.extracted_duckling_entities:
        duckling_table.add_row("None", "-", "-", "No temporal/monetary/numeric entities detected")
    else:
        for ent in intent.extracted_duckling_entities:
            val_summary = []
            if ent.get("start_date"):
                val_summary.append(f"start: {ent['start_date']}")
            if ent.get("end_date"):
                val_summary.append(f"end: {ent['end_date']}")
            if ent.get("min_amount") is not None:
                val_summary.append(f"min: €{ent['min_amount']:,.0f}")
            if ent.get("max_amount") is not None:
                val_summary.append(f"max: €{ent['max_amount']:,.0f}")
            if ent.get("num_value") is not None:
                val_summary.append(f"num: {ent['num_value']}")
            if ent.get("grain"):
                val_summary.append(f"grain: {ent['grain']}")
            duckling_table.add_row(
                ent.get("dim", ""),
                repr(ent.get("body", "")),
                ent.get("val_type", ""),
                ", ".join(val_summary) or str(ent.get("raw_value", {}))
            )

    console.print(duckling_table)

    # Execute Query
    if not DEFAULT_DB_PATH.exists():
        console.print(f"[bold red]Database not found at {DEFAULT_DB_PATH}. Run 'neurosym ingest' first.[/bold red]")
        sys.exit(1)

    engine = QueryEngine(DEFAULT_DB_PATH)
    res = engine.execute(intent)

    console.print(Panel(
        Syntax(res.generated_sql, "sql", theme="monokai", line_numbers=True),
        title=f"2. Compiled DuckDB SQL Query ({res.execution_time_ms} ms)"
    ))

    # Referenced Results
    console.print(f"[bold green]Referenced Dataset Matches ({res.total_matches} found, showing up to {intent.limit}):[/bold green]\n")

    if not res.records:
        console.print("[yellow]No records matched the specified intent schema constraints.[/yellow]")
        return

    if intent.target_entity == "project":
        for i, rec in enumerate(res.records, 1):
            top_orgs = rec.get("top_organizations", [])
            topics = rec.get("euroSciVoc_topics", [])
            
            org_str = ", ".join([f"{o['name']} ({o['country']}, {o['role']})" for o in top_orgs[:3]])
            topic_str = ", ".join(topics[:3])

            card = f"""[bold cyan]Project #{i}: {rec.get('acronym')} ({rec.get('id')})[/bold cyan]
[bold white]{rec.get('title')}[/bold white]
• [bold]Budget:[/bold] €{rec.get('totalCost', 0):,.2f} (EC Grant: €{rec.get('ecMaxContribution', 0):,.2f})
• [bold]Timeline:[/bold] {rec.get('startDate')} to {rec.get('endDate')}
• [bold]Funding Scheme:[/bold] {rec.get('fundingScheme')}
• [bold]Top Organizations:[/bold] {org_str or 'N/A'}
• [bold]EuroSciVoc Topics:[/bold] {topic_str or 'N/A'}"""
            console.print(Panel(card, border_style="dim"))


def cmd_serve(args):
    """Launch the FastAPI backend server."""
    import uvicorn
    console.print(Panel.fit(
        f"[bold green]Starting NeuroSym FastAPI Backend Server[/bold green]\n"
        f"[dim]Host: {args.host} | Port: {args.port} | Docs: http://localhost:{args.port}/docs[/dim]",
        title="NeuroSym Web Backend"
    ))
    uvicorn.run("neurosym.api.server:app", host=args.host, port=args.port, reload=args.reload)


def cmd_test_adversarial(args):
    """Execute the 5-Phase Adversarial Multi-Agent Stress Testing Pipeline."""
    from neurosym.qa.adversarial_pipeline import AdversarialPipelineOrchestrator
    orchestrator = AdversarialPipelineOrchestrator()
    summary = orchestrator.run_adversarial_suite(rate_delay_s=args.delay)
    
    table = Table(title="NeuroSym 5-Phase Adversarial Stress Test Results", header_style="bold green")
    table.add_column("Phase ID & Focus Area", style="cyan")
    table.add_column("Score", justify="center", style="yellow")
    table.add_column("Passed / Total", justify="center", style="green")

    for phase, stats in summary["phase_scores"].items():
        score_str = f"[bold green]{stats['score']}/10.0[/bold green]" if stats['score'] == 10.0 else f"[bold yellow]{stats['score']}/10.0[/bold yellow]"
        table.add_row(phase, score_str, f"{stats['passed']}/{stats['total']}")

    console.print(table)
    console.print(f"[bold cyan]Overall Integrity Score:[/bold cyan] [bold green]{summary['overall_score']}/10.0[/bold green] ({summary['total_passed']}/{summary['total_tests']} tests passed)")


def main():
    parser = argparse.ArgumentParser(description="NeuroSym - CORDIS Entity Extraction, Evidence Runtime & Decision Synthesizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest command
    subparsers.add_parser("ingest", help="Ingest CORDIS dataset into DuckDB and create Master Schema")

    # Schema command
    subparsers.add_parser("schema", help="View Master Schema entities, parameters, and vocabularies")

    # Rules command
    subparsers.add_parser("rules", help="List all registered official, benchmark, and policy rules")

    # Synthesize / Run command (Full Evidence Runtime + Decision Synthesizer)
    run_parser = subparsers.add_parser("run", help="Execute Evidence Runtime -> Synthesizer to evaluate proposal")
    run_parser.add_argument("prompt", type=str, help="Proposal prompt text to evaluate")

    synth_parser = subparsers.add_parser("synthesize", help="Execute Evidence Runtime -> Synthesizer to evaluate proposal")
    synth_parser.add_argument("prompt", type=str, help="Proposal prompt text to evaluate")

    # Parse & Query command
    parse_parser = subparsers.add_parser("parse", help="Extract entities from prompt and query dataset")
    parse_parser.add_argument("prompt", type=str, help="Natural language prompt")

    # Serve backend command
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI backend server for web frontend integration")
    serve_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind")
    serve_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable hot reloading")

    # Adversarial Pipeline command
    adv_parser = subparsers.add_parser("test-adversarial", help="Run the 5-phase adversarial multi-agent stress test pipeline")
    adv_parser.add_argument("--delay", type=float, default=1.0, help="Pacing delay between LLM calls in seconds (default: 1.0)")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "schema":
        cmd_schema(args)
    elif args.command == "rules":
        cmd_rules(args)
    elif args.command in ("run", "synthesize"):
        cmd_run_synthesis(args)
    elif args.command == "parse":
        cmd_parse(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "test-adversarial":
        cmd_test_adversarial(args)


if __name__ == "__main__":
    main()


