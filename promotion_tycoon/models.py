import uuid
from typing import List, Optional, Dict, Any, Annotated, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class RoleDefinition(BaseModel):
    role_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    level: str
    industry_salary: Optional[str] = None
    focus_areas: List[str] = []
    responsibilities: List[str] = []
    success_metrics: List[str] = []
    core_competencies: List[str] = []

class Metric(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None
    improvement: Optional[str] = None

class ProjectRecord(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    quarter: Optional[str] = ""
    duration: Optional[str] = ""
    team_size: Optional[int] = None
    role: Optional[str] = ""
    context: str = ""
    actions: List[str] = []
    outcomes: List[str] = []
    metrics: List[Metric] = []
    technologies: List[str] = []
    stakeholders: List[str] = []
    related_focus_areas: List[str] = []
    skills_demonstrated: List[str] = []
    challenges_overcome: List[str] = []
    evidence_links: List[str] = []
    visibility: str = "team"
    impact_rating: int = Field(default=3, ge=1, le=5)

class ImpactReport(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    executive_summary: str
    strengths: List[str] = []
    gaps: List[str] = []
    recommendations: List[str] = []

class RoutingDecision(BaseModel):
    route: str
    intent: str
    reasoning: str

class WorkflowState(TypedDict):
    messages: Annotated[List, add_messages]
    packet_id: str
    phase: str
    route: Optional[str]
    intent: Optional[str]
    role_definition: Optional[Dict[str, Any]]
    projects: List[Dict[str, Any]]
    impact_report: Optional[Dict[str, Any]]
    mentors_found: Optional[List[Dict[str, Any]]]
    user_id: str
    waiting_for: Optional[str]
