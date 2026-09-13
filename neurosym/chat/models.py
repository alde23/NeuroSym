"""Data models for Multi-Turn Conversational Chat Agent & Session State."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from neurosym.rules.models import DomainStatistics, FeasibilityVerdict, ProposalContext
from neurosym.runtime.evidence import EvidencePacket


class ChatMessage(BaseModel):
    """A single message in the conversation thread."""
    role: str = Field(description="'user', 'assistant', or 'system'")
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatSession(BaseModel):
    """Encapsulates a user's multi-turn conversational session with accumulated proposal state."""
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: List[ChatMessage] = Field(default_factory=list)
    proposal_context: ProposalContext = Field(default_factory=lambda: ProposalContext(raw_prompt=""))
    latest_evidence: Optional[EvidencePacket] = None
    latest_verdict: FeasibilityVerdict = FeasibilityVerdict.FEASIBLE


class ChatResponse(BaseModel):
    """Rich conversational response returned to web clients & frontend UI."""
    session_id: str
    reply: str
    verdict: FeasibilityVerdict
    proposal_context: ProposalContext
    
    # Evidence & Analytics
    regulatory_evidence: List[str] = Field(default_factory=list)
    empirical_evidence: List[str] = Field(default_factory=list)
    operational_evidence: List[str] = Field(default_factory=list)
    feasibility_risks: List[str] = Field(default_factory=list)
    required_actions: List[str] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)
    
    # Statistics & Grounded Projects
    domain_statistics: Optional[DomainStatistics] = None
    comparable_projects: List[Dict[str, Any]] = Field(default_factory=list)
    
    is_grounded: bool = True
