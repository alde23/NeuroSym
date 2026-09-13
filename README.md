# ⚡ NeuroSym: Neurosymbolic Grant & Feasibility Intelligence Engine

**NeuroSym** is an enterprise neurosymbolic AI platform designed for EU Horizon Europe research grants, consortium structuring, and statutory compliance. It combines **deterministic symbolic rule engines (General Annex B)**, **empirical SQL data grounding on CORDIS via DuckDB**, and **neural LLMs (Google Gemini, Groq, OpenRouter)** with strict symbolic invariant enforcement.

---

## 🌟 Key Features

- **🛡️ Symbolic Supremacy & Regulatory Guardrails**: Deterministic validation against official Horizon Europe General Annex B rules (consortium size, eligible countries, coordinator constraints, duration caps). Symbolic verdicts strictly override neural hallucinations.
- **📊 Empirical CORDIS Grounding (DuckDB)**: Live statistical benchmarking (P25, P50, P75 distributions) on thousands of historical Horizon Europe projects.
- **🦆 Native Duckling & Regex Entity Normalization**: Parses complex amounts (e.g. `€4.5M`, `2 million euros`), durations (`36 months`), and dates into structured types via Rasa Duckling.
- **💬 Real-Time SSE Chat & Advisory Agent**: Interactive advisor with streaming Server-Sent Events (SSE), multi-turn conversation memory, and session state isolation.
- **🔄 Zero-Wait Multi-Key Pool & Multi-Provider Failover**: Built-in support for multiple Gemini and Groq keys with automatic rate-limit cooldown tracking and offline fallbacks.

---

## 🐳 Docker & Quickstart Options

### Option 1: One-Click Docker Compose (Recommended)
Spawns both the **Rasa Duckling entity parser** (port 8005) and **NeuroSym API** (port 8080):

```bash
# 1. Clone repo and copy environment template
git clone https://github.com/alde23/NeuroSym.git
cd NeuroSym
cp .env.example .env

# 2. Launch all services
docker compose up -d
```
- **Web UI & Chatbot**: [http://localhost:8080](http://localhost:8080)
- **Interactive Swagger Docs**: [http://localhost:8080/docs](http://localhost:8080/docs)

---

### Option 2: Local Python Setup (with uv)

#### 1. Install Dependencies
```bash
git clone https://github.com/alde23/NeuroSym.git
cd NeuroSym

# Create virtual environment and sync dependencies
uv venv
uv pip install -e .
```

#### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Provide your API keys in `.env` (supports single keys or comma-separated lists for round-robin rotation):
```env
# Gemini Keys (Single or comma-separated for rotation)
GEMINI_API_KEYS=key1,key2

# Fast Free Failover (Groq - console.groq.com)
GROQ_API_KEY=your_groq_key

# Database location (auto-extracted from data/cordis.duckdb.zip on first run)
CORDIS_DB_PATH=cordis.duckdb
PORT=8080
HOST=0.0.0.0
```

#### 3. Run Duckling Parser (Optional Docker Container)
Duckling extracts financial and temporal entities. Run it via Docker:
```bash
docker run -p 8005:8000 rasa/duckling
```
*(Note: If Duckling is not running, NeuroSym automatically uses its built-in offline regex entity extractor without errors).*

#### 4. Launch the Web Server
```bash
uv run python -m neurosym.cli serve --port 8080 --reload
```

---

## 📦 CORDIS Dataset Auto-Seeding

NeuroSym comes with a pre-packaged, compressed historical Horizon Europe dataset in [`data/cordis.duckdb.zip`](data/cordis.duckdb.zip). 
- When the server or query engine starts for the first time, it automatically extracts `cordis.duckdb` in seconds.
- No manual CSV downloads or database setup are required to run the project.

---

## 💻 CLI Commands

- **Start Interactive Terminal Chat**:
  ```bash
  uv run python -m neurosym.cli chat
  ```
- **Direct Proposal Feasibility Evaluation**:
  ```bash
  uv run python -m neurosym.cli evaluate --countries DE,NL,SE --budget 4500000 --duration 36 --topic "Robotics"
  ```
- **Execute Natural Query against CORDIS**:
  ```bash
  uv run python -m neurosym.cli query "Show top robotics projects in Germany"
  ```

---

## 🏛️ Architecture

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