# ⚡ NeuroSym: Neurosymbolic Grant & Feasibility Intelligence Engine

**NeuroSym** is an enterprise neurosymbolic AI platform designed for EU Horizon Europe research grants, consortium structuring, and statutory compliance. It combines **deterministic symbolic rule engines (General Annex B)**, **empirical SQL data grounding on CORDIS via DuckDB**, and **neural LLMs (Google Gemini & Groq failover)** with strict symbolic invariant enforcement.

---

## 🌟 Key Features

- **🛡️ Symbolic Supremacy & Regulatory Guardrails**: Deterministic validation against official Horizon Europe General Annex B rules (consortium size, eligible countries, coordinator constraints, duration caps). Symbolic verdicts override neural hallucinations.
- **📊 Empirical CORDIS Grounding (DuckDB)**: Live statistical benchmarking (P25, P50, P75 distributions) on real Horizon Europe projects and funding data.
- **💬 Real-Time SSE Chat & Advisory Agent**: Interactive advisor with streaming Server-Sent Events (SSE), multi-turn conversation memory, and session state isolation.
- **🔄 Multi-Provider Resilience**: Built-in support for Google Gemini and Groq (Llama 3.3 70B) with automatic exponential backoff and deterministic offline fallbacks.
- **🧪 Multi-Agent Adversarial Stress-Testing**: Integrated multi-persona stress test suite (Risk-Avoidant Investor, Skeptic Senior Engineer, Senior QA Engineer, Regulatory Auditor).

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+ installed
- [uv](https://github.com/astral-sh/uv) (recommended) or standard `pip`

### 2. Installation & Setup
Clone the repository and install dependencies:
```bash
git clone https://github.com/alde23/NeuroSym.git
cd NeuroSym

# Create virtual environment and sync dependencies
uv venv
uv pip install -e .
```

### 3. Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```
Edit `.env` and provide your API keys:
```env
# Primary LLM Key (Google Gemini)
GEMINI_API_KEY=your_gemini_api_key_here

# Secondary Failover LLM Key (Groq - Free 30 RPM at console.groq.com)
GROQ_API_KEY=your_groq_api_key_here

# DuckDB Database Location
CORDIS_DB_PATH=cordis.duckdb
PORT=8080
HOST=0.0.0.0
```

*(Note: NeuroSym also works completely offline with its deterministic fallback engine if no external API keys are configured).*

### 4. Ingest CORDIS Data (Optional / First Run)
If you have the CORDIS Horizon Europe dataset zip files:
```bash
uv run python -m neurosym.cli ingest
```

### 5. Launch the Application

#### Option A: Web Server & Interactive API
```bash
uv run python -m neurosym.cli serve --port 8080 --reload
```
- **Web UI & SSE Chat**: Visit [http://localhost:8080](http://localhost:8080)
- **Interactive Swagger Docs**: Visit [http://localhost:8080/docs](http://localhost:8080/docs)

#### Option B: Terminal Interactive Chat
```bash
uv run python -m neurosym.cli chat
```

#### Option C: Direct CLI Proposal Evaluation
```bash
uv run python -m neurosym.cli evaluate --countries DE,NL,SE --budget 4500000 --duration 36 --topic "Robotics"
```

---

## 🧪 Testing & Stress-Testing

### Run Unit Tests
```bash
uv run pytest
```

### Run Multi-Agent Adversarial Stress Suite
Runs 14 specialized adversarial tests probing prompt injections, multi-tenant state isolation, SQL injection immunity, financial boundaries, and concurrency bursts:
```bash
uv run python -m neurosym.qa.stress_test_pipeline
```

---

## 🏛️ System Architecture

```
User Inquiry / Proposal
        │
        ▼
┌──────────────────────────────┐
│  NeuroSym Chat & Intent API  │ ──► FastAPI Server (SSE Stream)
└──────────────┬───────────────┘
               │
        ┌──────┴───────────────────────────┐
        ▼                                  ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│ Symbolic Rule Engine    │      │ Empirical Engine        │
│ • General Annex B       │      │ • CORDIS DuckDB Data    │
│ • Statutory Checks      │      │ • P25-P75 Benchmarks    │
└──────────────┬──────────┘      └────────────┬────────────┘
               │                              │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │ Multi-Provider Neural LLM    │
               │ • Google Gemini (Primary)    │
               │ • Groq Llama-3.3 (Failover)  │
               │ • Deterministic Fallback     │
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │    Synthesized Verdict &     │
               │     Actionable Advisory      │
               └──────────────────────────────┘
```

---

## 📄 License
MIT License