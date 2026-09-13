"""FastAPI Backend Server providing RESTful & Conversational APIs for Horizon Europe Feasibility Engine."""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from neurosym.chat.agent import NeuroSymChatAgent
from neurosym.chat.models import ChatResponse, ChatSession
from neurosym.duckling.client import DucklingClient
from neurosym.ingestion.cordis_ingest import DEFAULT_DB_PATH, DEFAULT_SCHEMA_PATH
from neurosym.query.engine import QueryEngine, QueryResult
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.runtime.evidence import EvidenceRuntime
from neurosym.schema.master_schema import MasterSchema
from neurosym.synthesizer.engine import SynthesizedReport
from neurosym.synthesizer.neural_synthesizer import NeuralDecisionSynthesizer

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent.parent / "web"

# Initialize FastAPI App
app = FastAPI(
    title="NeuroSym Horizon Europe Advisory API",
    description="Neuro-Symbolic Conversational & Feasibility Engine for EU Horizon Europe Proposals and CORDIS Analytics.",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Vite, React, Next.js, etc.)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton components
chat_agent = NeuroSymChatAgent()
evidence_runtime = EvidenceRuntime()
synthesizer = NeuralDecisionSynthesizer()
rule_evaluator = RuleEvaluator()
query_engine = QueryEngine()


# Request / Response Schemas
class ChatRequest(BaseModel):
    message: str = Field(..., description="User's natural language proposal inquiry or follow-up question")
    session_id: Optional[str] = Field(None, description="Optional existing session ID for multi-turn history")


class EvaluateRequest(BaseModel):
    prompt: str = Field(..., description="Full text description of the planned Horizon Europe proposal")


class QueryRequest(BaseModel):
    prompt: str = Field(..., description="Natural language search query over CORDIS data")


class HealthResponse(BaseModel):
    status: str
    duckdb_connected: bool
    duckling_service_connected: bool
    database_path: str
    rules_count: int


# API Routes

@app.get("/api/meta", tags=["General"])
def api_metadata():
    """API metadata and documentation pointer."""
    return {
        "service": "NeuroSym Horizon Europe Feasibility & Advisory API",
        "version": "1.0.0",
        "documentation": "/docs",
        "endpoints": {
            "chat": "POST /api/chat",
            "evaluate": "POST /api/evaluate",
            "query": "POST /api/query",
            "rules": "GET /api/rules",
            "schema": "GET /api/schema",
            "health": "GET /api/health"
        }
    }


@app.get("/api/health", response_model=HealthResponse, tags=["General"])
def health_check():
    """Health check for DuckDB, Duckling, and domain components."""
    duckdb_ok = DEFAULT_DB_PATH.exists()
    
    # Check duckling
    duckling_ok = False
    try:
        duckling = DucklingClient()
        test_res = duckling.extract_entities("2 million EUR")
        duckling_ok = len(test_res) > 0
    except Exception:
        duckling_ok = False

    rules = rule_evaluator.get_rules_catalog()

    return HealthResponse(
        status="healthy" if duckdb_ok else "degraded",
        duckdb_connected=duckdb_ok,
        duckling_service_connected=duckling_ok,
        database_path=str(DEFAULT_DB_PATH),
        rules_count=len(rules)
    )


@app.get("/api/sessions", tags=["Conversational Chatbot"])
def list_chat_sessions():
    """
    Returns list of all active chat sessions for the frontend sidebar.
    Includes session ID, snippet/title, message count, created timestamp, latest verdict, and extracted proposal specs.
    """
    sessions_list = []
    for sid, sess in sorted(chat_agent.sessions.items(), key=lambda x: x[1].updated_at, reverse=True):
        title = "New Consultation"
        if sess.messages:
            first_user_msg = next((m.content for m in sess.messages if m.role == "user"), None)
            if first_user_msg:
                title = first_user_msg[:50] + ("..." if len(first_user_msg) > 50 else "")
        
        ctx = sess.proposal_context
        specs_parts = []
        if ctx.partner_count:
            specs_parts.append(f"{ctx.partner_count} partners")
        if ctx.requested_duration_months:
            specs_parts.append(f"{ctx.requested_duration_months}mo")
        if ctx.requested_budget_eur:
            specs_parts.append(f"€{ctx.requested_budget_eur/1e6:.1f}M")
        if ctx.countries:
            specs_parts.append(", ".join(ctx.countries[:3]) + ("+" if len(ctx.countries) > 3 else ""))

        sessions_list.append({
            "session_id": sid,
            "title": title,
            "created_at": sess.created_at,
            "updated_at": sess.updated_at,
            "message_count": len(sess.messages),
            "verdict": sess.latest_verdict.value if sess.latest_verdict else "FEASIBLE",
            "topic": ctx.domain_topic or "Horizon Europe",
            "specs_summary": " • ".join(specs_parts) if specs_parts else None,
            "proposal_context": ctx.model_dump() if ctx else None
        })
    return {"sessions": sessions_list}


@app.post("/api/chat", response_model=ChatResponse, tags=["Conversational Chatbot"])
def chat(req: ChatRequest):
    """
    Multi-turn conversational chat endpoint.
    Maintains proposal state across turns, gathers fresh evidence, and returns
    an authoritative, grounded conversational response with live feasibility verdict.
    """
    if not req.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")
    
    try:
        response = chat_agent.process_message(
            user_message=req.message,
            session_id=req.session_id
        )
        return response
    except Exception as e:
        logger.exception("Error processing chat message")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/chat/stream", tags=["Conversational Chatbot"])
async def chat_stream(req: ChatRequest):
    """
    Server-Sent Events (SSE) streaming chat endpoint for real-time typewriter UI effects.
    Streams words progressively and finishes with the full grounded metadata payload.
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    if not req.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")

    async def event_generator():
        try:
            # Process response
            response = chat_agent.process_message(
                user_message=req.message,
                session_id=req.session_id
            )

            # Stream words with slight delay for realistic typewriter effect
            words = response.reply.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                data = json.dumps({"type": "chunk", "delta": chunk})
                yield f"data: {data}\n\n"
                await asyncio.sleep(0.015)

            # Send complete structured payload at the end
            done_payload = json.dumps({
                "type": "complete",
                "data": response.model_dump()
            })
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            err_data = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {err_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/chat/{session_id}", response_model=ChatSession, tags=["Conversational Chatbot"])
def get_chat_session(session_id: str):
    """Retrieves session message history and accumulated proposal context."""
    if session_id not in chat_agent.sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return chat_agent.sessions[session_id]


@app.delete("/api/chat/{session_id}", tags=["Conversational Chatbot"])
def reset_chat_session(session_id: str):
    """Resets the conversation and proposal state for a session."""
    chat_agent.reset_session(session_id)
    return {"status": "success", "message": f"Session {session_id} has been reset."}


@app.post("/api/evaluate", response_model=SynthesizedReport, tags=["Feasibility Evaluation"])
def evaluate_proposal(req: EvaluateRequest):
    """
    Single-shot proposal evaluation pipeline:
    Extracts entities -> Gathers deterministic evidence -> Validates grounding -> Synthesizes Feasibility Report.
    """
    if not req.prompt.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt cannot be empty.")

    try:
        evidence = evidence_runtime.gather_evidence(req.prompt)
        report = synthesizer.synthesize(evidence)
        return report
    except Exception as e:
        logger.exception("Error evaluating proposal")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/api/query", response_model=QueryResult, tags=["CORDIS Data Analytics"])
def query_cordis(req: QueryRequest):
    """
    Natural Language to SQL Query Engine:
    Uses Duckling and Master Schema to parse entities and execute parameterized SQL against CORDIS.
    """
    if not req.prompt.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt cannot be empty.")

    try:
        from neurosym.intent.mapper import IntentMapper
        mapper = IntentMapper()
        intent = mapper.parse_and_map(req.prompt)
        result = query_engine.execute(intent)
        return result
    except Exception as e:
        logger.exception("Error querying CORDIS")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/rules", tags=["Domain Rules"])
def list_rules():
    """Returns the registered official Horizon Europe rules and company policies."""
    return {
        "domain": rule_evaluator.name,
        "description": rule_evaluator.description,
        "rules": [r.model_dump() for r in rule_evaluator.get_rules_catalog()]
    }


@app.get("/api/schema", tags=["Master Schema"])
def get_master_schema():
    """Returns the Master Schema catalog containing all parameters and Duckling mappings."""
    if not DEFAULT_SCHEMA_PATH.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Master schema file not found.")
    
    with open(DEFAULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = MasterSchema.model_validate_json(f.read())
    return schema


# Mount Web Chat Frontend (serves index.html, styles.css, app.js, theme.css)
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")

