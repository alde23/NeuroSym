# NeuroSym — Horizon Europe Intelligence Console

A full web interface for the NeuroSym engine from your upload. It talks to your Python backend when one is reachable, and falls back to realistic built-in sample data so every screen works standalone.

## Screens

**1. Feasibility Evaluator (home, `/`)**
Large prompt box for describing a planned proposal. Results show:
- Verdict banner (Feasible / Conditionally Feasible / Infeasible / Out of Domain) with confidence score
- Extracted proposal context chips: partners, countries, scheme, budget, duration, role, topic
- Three evidence columns: regulatory, empirical, operational
- Risks and required actions lists
- Grounded citations and an audit note strip

**2. Grant Advisor Chat (`/advisor`)**
- Session sidebar listing past consultations with title, topic, verdict and message count
- Streaming replies rendered word-by-word as they arrive
- Live verdict badge that updates each turn
- Side drawer with the turn's evidence, statistics and comparable projects
- Suggested follow-up questions as one-click chips; reset/delete a session

**3. CORDIS Explorer (`/explorer`)**
- Natural-language query box; shows generated SQL, execution time, match count
- Results table with expandable rows revealing top organisations and science topics
- Benchmark panel: budget percentile distribution bar chart (p5–p98) with the requested budget marked, partner-count and duration comparisons, country split

**4. Rules & Schema (`/rules`)**
- Searchable rule catalogue grouped by source (official / benchmark / policy) with severity, condition, message and reference
- Schema browser: entity list, column details (type, semantic type, unit, description), join paths, row counts

**5. Settings (`/settings`)**
- Backend URL field with live health check: DuckDB status, Duckling status, database path, rule count
- Toggle between live backend and demo data; choice saved in the browser

## Look

Dark "Horizon" console reusing the palette from your existing theme: near-black indigo background, cobalt/cyan accent gradient, glass cards, mono type for SQL and identifiers. Verdict colours: emerald / amber / red. Persistent left nav rail across all screens.

## Technical notes

- TanStack Start routes: `index`, `advisor`, `explorer`, `rules`, `settings`; shared shell in `__root`.
- `src/lib/api.ts`: typed client mirroring the FastAPI contracts (`/api/evaluate`, `/api/chat/stream` SSE, `/api/sessions`, `/api/chat/{id}`, `/api/query`, `/api/rules`, `/api/schema`, `/api/health`). Base URL from localStorage, default `http://localhost:8000`.
- `src/lib/mock/*`: fixtures matching `SynthesizedReport`, `ChatResponse`, `QueryResult`, rules catalogue and master schema shapes; used automatically when the backend is unreachable or demo mode is on.
- Types mirrored from the Pydantic models (`FeasibilityVerdict`, `ProposalContext`, `DomainStatistics`, `RuleEvaluation`, `EntitySchema`).
- Streaming chat parses the SSE `chunk` / `complete` / `error` events; mock mode simulates the same stream.
- Charts drawn with lightweight SVG/CSS, no chart dependency. Colours come from design tokens in `src/styles.css`.
- Per-route head metadata for titles and descriptions.
