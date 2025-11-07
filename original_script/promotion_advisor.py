"""
Promotion Advisor - Multi-Agent System with LangGraph + MongoDB
Complete implementation with rich project data extraction and interrupt handling
"""

import os
import json
import time
import uuid
import asyncio  # Add asyncio for timeout
from datetime import datetime, timezone
from typing import TypedDict, Annotated, List, Optional, Dict, Any
from typing_extensions import TypedDict as ExtendedTypedDict
from pathlib import Path

import gradio as gr
from pydantic import BaseModel, Field
from pymongo import MongoClient

# LangChain & LangGraph
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

# MCP Support (we'll import MultiServerMCPClient in the MCP setup section)

# ============================================================================
# CONFIGURATION
# ============================================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MONGODB_URI = "mongodb+srv://replace-with-your-connection-string"
DATABASE_NAME = "promotion_advisor"

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class RoleDefinition(BaseModel):
    """Target role definition"""
    role_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    level: str
    industry_salary: Optional[str] = None  # Use None instead of ""
    focus_areas: List[str] = []
    responsibilities: List[str] = []
    success_metrics: List[str] = []
    core_competencies: List[str] = []

class Metric(BaseModel):
    """Individual metric/measurement"""
    name: str
    value: str
    unit: Optional[str] = None
    improvement: Optional[str] = None  # e.g., "+25%", "3x faster"

class ProjectRecord(BaseModel):
    """Rich project record with detailed metrics and evidence"""
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    quarter: Optional[str] = ""
    duration: Optional[str] = ""  # e.g., "6 months", "Q1-Q3 2023"
    team_size: Optional[int] = None
    role: Optional[str] = ""  # User's specific role in the project
    context: str = ""  # Problem/opportunity addressed
    actions: List[str] = []  # Specific things the user did
    outcomes: List[str] = []  # Results achieved
    metrics: List[Metric] = []  # Quantifiable measurements
    technologies: List[str] = []  # Technologies/tools used
    stakeholders: List[str] = []  # Who was impacted/involved
    related_focus_areas: List[str] = []  # Maps to target role focus areas
    skills_demonstrated: List[str] = []  # Specific skills shown
    challenges_overcome: List[str] = []  # Problems solved
    evidence_links: List[str] = []  # URLs, docs, references
    visibility: str = "team"  # team/department/company/industry
    impact_rating: int = Field(default=3, ge=1, le=5)  # 1-5 scale

class ImpactReport(BaseModel):
    """Impact analysis report"""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    executive_summary: str
    strengths: List[str] = []
    gaps: List[str] = []
    recommendations: List[str] = []

class RoutingDecision(BaseModel):
    """Supervisor routing decision"""
    route: str
    intent: str
    reasoning: str

# ============================================================================
# LANGGRAPH STATE
# ============================================================================

class WorkflowState(TypedDict):
    """State for the promotion advisor workflow"""
    messages: Annotated[List, add_messages]
    packet_id: str
    phase: str  # "setup", "projects", "impact", "iteration", "complete"
    route: Optional[str]
    intent: Optional[str]
    role_definition: Optional[Dict]
    projects: List[Dict]
    impact_report: Optional[Dict]
    mentors_found: Optional[List[Dict]]  # Add this to persist mentors
    user_id: str
    waiting_for: Optional[str]  # Track what we're waiting for from user

# ============================================================================
# TRACING UTILITIES
# ============================================================================

TRACE_BUFFER: List[dict] = []

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

def log_trace(msg: str, **kv):
    entry = {"timestamp": _ts(), "level": "INFO", "message": msg, "ctx": kv}
    TRACE_BUFFER.append(entry)
    print(f"[{entry['timestamp']}] 🟢 {msg} {json.dumps(kv) if kv else ''}")

def log_error(label: str, exc: Exception, **kv):
    entry = {
        "timestamp": _ts(),
        "level": "ERROR",
        "label": label,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "ctx": kv,
    }
    TRACE_BUFFER.append(entry)
    print(f"[{entry['timestamp']}] 🔴 {label} ERROR: {entry['error_type']} {entry['error']}")

def format_trace_for_ui() -> str:
    html = [
        """<div style="font-family:'Fira Code',monospace;background-color:#0f1117;
        color:#f1f1f1;padding:10px 12px;border-radius:10px;line-height:1.4em;
        font-size:13px;overflow-y:auto;max-height:520px;">"""
    ]
    for e in TRACE_BUFFER[-400:]:
        ts = e.get("timestamp", "")
        lvl = e.get("level", "INFO")
        msg = e.get("message", "")
        ctx = e.get("ctx", {})
        
        color = "#ff6b6b" if lvl == "ERROR" else "#8be9fd"
        icon = "🔴" if lvl == "ERROR" else "🟢"
        
        html.append(f"""
            <div style="margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #2a2d36;">
                <span style="color:#888;">[{ts}]</span>
                <span style="color:{color};">{icon} {msg}</span>
        """)
        if ctx:
            pretty_ctx = json.dumps(ctx, indent=2).replace(" ", "&nbsp;").replace("\n", "<br>")
            html.append(f"<div style='margin-top:4px;color:#aaa;font-size:12px;'><pre>{pretty_ctx}</pre></div>")
        html.append("</div>")
    html.append("</div>")
    return "".join(html)

# ============================================================================
# MONGODB SETUP
# ============================================================================

log_trace("🔌 Initializing MongoDB connections")

# In-memory storage fallback
IN_MEMORY_STORAGE = {
    "packets": {},
    "roles": {},
    "projects": {},
    "reports": {}
}

try:
    pymongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    # Test connection
    pymongo_client.server_info()
    db = pymongo_client[DATABASE_NAME]
    checkpointer = MongoDBSaver(pymongo_client)
    USE_MONGODB = True
    log_trace("✅ MongoDB connected", database=DATABASE_NAME)
except Exception as e:
    log_error("MongoDB Connection", e)
    # Fallback to in-memory storage
    checkpointer = MemorySaver()
    db = None
    USE_MONGODB = False
    log_trace("⚠️ Using in-memory storage (MongoDB unavailable)")

# ============================================================================
# MCP SERVER SETUP
# ============================================================================

log_trace("🔧 Initializing MCP Servers")

# Initialize MCP client for external tools (not MongoDB)
MCP_CLIENT = None
MCP_TOOLS = []

try:
    # Set up MCP for external data sources
    from langchain_mcp_adapters.client import MultiServerMCPClient
    
    # Get Tavily API key from environment
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    
    if TAVILY_API_KEY:
        MCP_CLIENT = MultiServerMCPClient({
            "tavily": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "tavily-mcp@0.2.4"],
                "env": {
                    "TAVILY_API_KEY": TAVILY_API_KEY
                }
            }
        })
        log_trace("✅ Tavily MCP configured")
    else:
        log_trace("⚠️ Tavily API key not found - web search disabled")
        
except Exception as e:
    log_error("MCP Client Setup", e)
    MCP_CLIENT = None
    log_trace("⚠️ MCP unavailable")

# Function to get MCP tools
async def get_mcp_tools():
    """Get available MCP tools"""
    if not MCP_CLIENT:
        return []
    
    try:
        tools = await MCP_CLIENT.get_tools()
        log_trace("🔧 MCP tools loaded", count=len(tools) if tools else 0)
        return tools
    except Exception as e:
        log_error("Get MCP Tools", e)
        return []

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def create_packet(user_id: str, current_role: str = "", target_role: str = "") -> str:
    """Create a new promotion packet"""
    packet_id = str(uuid.uuid4())
    log_trace("🚀 Create Packet started")
    
    packet_data = {
        "_id": packet_id,
        "packet_id": packet_id,
        "user_id": user_id,
        "current_role": current_role,
        "target_role": target_role,
        "created_at": datetime.now(timezone.utc),
        "phase": "setup"
    }
    
    if USE_MONGODB:
        try:
            db.packets.insert_one(packet_data)
        except Exception as e:
            log_error("Create Packet DB", e)
    else:
        IN_MEMORY_STORAGE["packets"][packet_id] = packet_data
    
    log_trace("💾 Packet created", packet_id=packet_id)
    return packet_id

def upsert_role(packet_id: str, role_def: RoleDefinition):
    """Write role definition to MongoDB"""
    log_trace("🚀 Upsert Role started")
    
    role_data = {**role_def.model_dump(), "packet_id": packet_id}
    
    if USE_MONGODB:
        try:
            db.roles.update_one(
                {"packet_id": packet_id},
                {"$set": role_data},
                upsert=True
            )
        except Exception as e:
            log_error("Upsert Role DB", e)
    else:
        IN_MEMORY_STORAGE["roles"][packet_id] = role_data
    
    log_trace("🎯 Role upserted", title=role_def.title)

def insert_projects(packet_id: str, projects: List[ProjectRecord]):
    """Insert project records"""
    log_trace("🚀 Insert Projects started")
    
    if USE_MONGODB:
        try:
            for proj in projects:
                db.projects.insert_one({
                    **proj.model_dump(),
                    "packet_id": packet_id
                })
        except Exception as e:
            log_error("Insert Projects DB", e)
    else:
        if packet_id not in IN_MEMORY_STORAGE["projects"]:
            IN_MEMORY_STORAGE["projects"][packet_id] = []
        for proj in projects:
            IN_MEMORY_STORAGE["projects"][packet_id].append({
                **proj.model_dump(),
                "packet_id": packet_id
            })
    
    log_trace("📁 Projects inserted", count=len(projects))

def upsert_report(packet_id: str, report: ImpactReport):
    """Write impact report to MongoDB"""
    log_trace("🚀 Upsert Report started")
    
    report_data = {**report.model_dump(), "packet_id": packet_id}
    
    if USE_MONGODB:
        try:
            db.reports.update_one(
                {"packet_id": packet_id},
                {"$set": report_data},
                upsert=True
            )
        except Exception as e:
            log_error("Upsert Report DB", e)
    else:
        IN_MEMORY_STORAGE["reports"][packet_id] = report_data
    
    log_trace("📊 Report upserted")

def get_role_direct(packet_id: str) -> Optional[Dict]:
    """Direct MongoDB read for role definition (fallback)"""
    if USE_MONGODB:
        try:
            return db.roles.find_one({"packet_id": packet_id})
        except Exception as e:
            log_error("Get Role DB", e)
            return None
    else:
        return IN_MEMORY_STORAGE["roles"].get(packet_id)

def get_role(packet_id: str) -> Optional[Dict]:
    """Get role definition from MongoDB"""
    return get_role_direct(packet_id)

def get_projects(packet_id: str) -> List[Dict]:
    """Get all projects for a packet"""
    if USE_MONGODB:
        try:
            return list(db.projects.find({"packet_id": packet_id}))
        except Exception as e:
            log_error("Get Projects DB", e)
            return []
    else:
        return IN_MEMORY_STORAGE["projects"].get(packet_id, [])

def get_report(packet_id: str) -> Optional[Dict]:
    """Get impact report from MongoDB"""
    if USE_MONGODB:
        try:
            return db.reports.find_one({"packet_id": packet_id})
        except Exception as e:
            log_error("Get Report DB", e)
            return None
    else:
        return IN_MEMORY_STORAGE["reports"].get(packet_id)

# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SUPERVISOR_PROMPT = """You are a routing supervisor for a promotion preparation system.

Current context:
- Phase: {phase}
- Has Target Role: {has_role}
- Projects Count: {projects_count}
- Has Report: {has_report}

User message: {user_message}

Route to the appropriate agent:
- "target_builder": User wants to set/define their target promotion role (e.g., "I want to become...", "My goal is...", "I'm targeting...")
- "project_curator": User is sharing project information to add to their portfolio
- "impact_analyzer": User wants to generate or update their impact report
- "mentor_finder": User wants to find similar professionals on LinkedIn (e.g., "find mentors", "similar people", "professionals in this role")
- "guidance_agent": User needs help, clarification, or is making small talk
- "iteration": User wants to add more projects after seeing the report
- "end": User is done and satisfied

Special rules:
- If user mentions wanting to become a specific role (VP, Director, Manager, etc.), route to "target_builder"
- If user says "done", "finished", "that's all", route to "end"
- If user provides project details after having a role, route to "project_curator"
- If user asks about finding mentors or similar professionals, route to "mentor_finder"

Respond with JSON containing: route, intent, and reasoning."""

TARGET_BUILDER_PROMPT = """You are a career coach helping someone define their target promotion role.

Parse the user's message and extract:
1. The target role title (e.g., Staff Software Engineer, Senior Data Scientist, Engineering Manager)
2. The level (e.g., Staff, Senior Staff, Principal, Director)
3. Key focus areas for this role (3-5 items)
4. Main responsibilities (4-6 items)
5. Success metrics (3-5 measurable outcomes)
6. Core competencies needed (4-6 skills/abilities)

Be thorough and realistic. If the user provides limited information, make reasonable 
inferences based on industry standards for that role level.

Generate a complete RoleDefinition with all fields populated."""

PROJECT_CURATOR_PROMPT = """You are an expert project analyzer. Extract comprehensive project information from the user's text.

For each project mentioned, extract as much detail as possible:

**Core Information:**
- Project name/title (be specific)
- Duration/quarter (when it happened)
- Team size (if mentioned)
- User's specific role (leader, contributor, etc.)

**Project Details:**
- Context: The problem, opportunity, or business need addressed
- Actions: Specific actions the user took (use action verbs)
- Outcomes: Tangible results and business impact

**Metrics & Evidence:**
- Quantifiable metrics with values and units (e.g., "reduced latency: 200ms → 50ms")
- Percentage improvements (e.g., "+40% efficiency")
- Scale indicators (users impacted, revenue, cost savings)

**Technical & Skills:**
- Technologies/tools used (programming languages, frameworks, platforms)
- Skills demonstrated (leadership, technical, analytical, communication)
- Challenges overcome (technical, organizational, resource constraints)

**Strategic Alignment:**
- Which VP/executive focus areas this relates to (strategy, innovation, operations, etc.)
- Stakeholders impacted (customers, teams, executives, partners)
- Visibility level (team/department/company/industry-wide impact)

**Evidence:**
- Any mentioned documentation, links, or references

**Impact Rating:**
Rate 1-5 based on:
- 5: Transformational/strategic initiative with company-wide impact
- 4: Significant project with department/multiple team impact  
- 3: Important project with team-level impact
- 2: Meaningful contribution to ongoing work
- 1: Learning/support role

If information is not explicitly stated, make reasonable inferences based on context.
If multiple projects are described, create separate detailed ProjectRecord objects for each.

Return a list of ProjectRecord objects with all available fields populated."""

IMPACT_ANALYZER_PROMPT = """You are a strategic impact analyst evaluating promotion readiness.

**Target Role:** {role_title}
**Level:** {role_level}
**Focus Areas:** {focus_areas}
**Key Responsibilities:** {responsibilities}

**Industry Research from Web Search:**
{industry_insights}

MANDATORY REQUIREMENTS FOR YOUR ANALYSIS:
1. You MUST mention specific salary ranges found in the industry research above (look for $ amounts)
2. You MUST cite at least one source URL from the research
3. In the "Gaps" section, compare candidate to industry standards, not generic assumptions
4. If no salary data is found above, explicitly state "No salary data available from industry research"

**Projects Portfolio Analysis:**
Total Projects: {project_count}
{projects_detail}

**Analyze the following:**

1. **Quantitative Impact Assessment:**
   - Review metrics and KPIs achieved across projects
   - Calculate cumulative business value delivered
   - Assess scale of impact (team → company → industry)

2. **Strategic Alignment:**
   - Map projects to target role focus areas
   - Evaluate coverage of key responsibilities
   - Identify demonstrated competencies vs. requirements

3. **Leadership & Scope Progression:**
   - Analyze evolution of project complexity and team size
   - Evaluate progression in visibility and stakeholder level
   - Assess strategic vs. tactical work ratio

4. **Technical & Innovation Excellence:**
   - Evaluate technical depth and breadth
   - Assess innovation and transformation initiatives
   - Review adoption of emerging technologies

5. **Gaps Analysis:**
   - Identify missing experiences for target role
   - Highlight areas needing additional evidence
   - Specify metrics or outcomes that need strengthening

Generate an ImpactReport with:

**Executive Summary** (2-3 sentences):
- Overall readiness assessment with specific evidence
- Key differentiators backed by metrics

**Strengths** (4-5 specific, evidence-backed points):
- Reference specific projects, metrics, and outcomes
- Highlight patterns across multiple projects
- Emphasize unique value propositions

**Gaps** (3-4 specific areas):
- Be precise about what's missing
- Suggest specific experience types needed
- Note missing stakeholder levels or scale

**Recommendations** (4-5 actionable items):
- Prioritize by impact
- Include specific project types to pursue
- Suggest metrics to capture
- Recommend stakeholder relationships to build

Use specific project names, metrics, and evidence throughout.
Make the analysis data-driven and executive-ready."""

# ============================================================================
# LANGGRAPH AGENT NODES
# ============================================================================

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def supervisor_node(state: WorkflowState) -> Dict:
    """Route to appropriate agent based on user message"""
    log_trace("🚦 Supervisor deciding", 
              phase=state["phase"],
              preview=state["messages"][-1].content[:50] if state["messages"] else "",
              waiting_for=state.get("waiting_for"))
    
    # Get current context using direct reads (supervisor doesn't need MCP)
    role = get_role(state["packet_id"])
    projects = get_projects(state["packet_id"])
    report = get_report(state["packet_id"])
    
    # Check what we're waiting for and if we have a human response
    waiting_for = state.get("waiting_for")
    last_msg = state["messages"][-1] if state["messages"] else None
    is_human_msg = isinstance(last_msg, HumanMessage)
    
    # Handle interrupts based on what we're waiting for
    if waiting_for == "projects" and not is_human_msg:
        # Still waiting for projects input
        return {"route": "wait_for_input", "intent": "waiting_for_projects"}
    
    if waiting_for == "report_confirmation" and not is_human_msg:
        # Waiting for user to confirm report generation
        return {"route": "wait_for_input", "intent": "waiting_for_report_confirmation"}
    
    if waiting_for == "post_report_decision" and not is_human_msg:
        # Waiting for user decision after report
        return {"route": "wait_for_input", "intent": "waiting_for_post_report_decision"}
    
    if waiting_for == "mentor_search_confirmation" and not is_human_msg:
        # Waiting for user to confirm mentor search
        return {"route": "wait_for_input", "intent": "waiting_for_mentor_confirmation"}
    
    if waiting_for == "next_action" and not is_human_msg:
        # Waiting for user's next action after mentors shown
        return {"route": "wait_for_input", "intent": "waiting_for_next_action"}
    
    # Now handle routing based on user input
    # Let the LLM supervisor decide everything based on context
        
        # Check for role definition intent
        if not role and any(keyword in msg_content for keyword in ['want to become', 'want to be', 'targeting', 'promotion to']):
            return {"route": "target_builder", "intent": "define_target_role"}
    
    # Default routing through original supervisor logic
    prompt = SUPERVISOR_PROMPT.format(
        phase=state["phase"],
        has_role="Yes" if role else "No",
        projects_count=len(projects),
        has_report="Yes" if report else "No",
        user_message=last_msg.content if last_msg else ""
    )
    
    try:
        structured_model = model.with_structured_output(RoutingDecision)
        messages = state["messages"][-5:] if state["messages"] else []
        decision = await structured_model.ainvoke([
            SystemMessage(content=prompt),
            *messages
        ])
        
        log_trace("🤖 Routing Decision",
                  route=decision.route,
                  intent=decision.intent,
                  reasoning=decision.reasoning[:100])
        
        return {
            "route": decision.route,
            "intent": decision.intent
        }
    except Exception as e:
        log_error("Supervisor Decision", e)
        return {
            "route": "guidance_agent",
            "intent": "error_recovery"
        }

async def wait_for_input_node(state: WorkflowState) -> Dict:
    """Node that interrupts workflow to wait for user input"""
    log_trace("⏸️ Interrupting for user input", waiting_for=state.get("waiting_for"))
    
    # Use LangGraph's interrupt to pause execution
    # This will pause the graph and wait for user to provide input
    what_we_need = state.get("waiting_for", "input")
    
    if what_we_need == "projects":
        prompt = "Please provide your project information. Include specific details about what you worked on."
    else:
        prompt = "Please provide additional information."
    
    # This actually pauses the graph execution
    user_input = interrupt(prompt)
    
    # When resumed, this will be a HumanMessage with the user's input
    return {"messages": [user_input]}

async def target_builder_node(state: WorkflowState) -> Dict:
    """Build target role definition with industry research"""
    log_trace("🎯 Target Builder activated")
    
    # Extract basic role info from user message
    user_message = state["messages"][-1].content
    
    # First, research the role using Tavily MCP
    industry_insights = None
    if MCP_CLIENT:
        try:
            log_trace("🔍 Researching target role via Tavily")
            tools = await get_mcp_tools()
            
            if tools:
                # Find Tavily search tool
                search_tool = None
                for tool in tools:
                    if 'tavily' in tool.name.lower() or 'search' in tool.name.lower():
                        search_tool = tool
                        break
                
                if search_tool:
                    # Research the role mentioned by user
                    search_query = f"{user_message} requirements responsibilities salary skills qualifications 2024 2025"
                    log_trace("🔎 Searching for role insights", query=search_query)
                    
                    # Invoke the search tool
                    search_result = await search_tool.ainvoke({"query": search_query})
                    
                    # DEBUG: Log the full response structure
                    log_trace("📋 Raw Tavily response type", type=type(search_result).__name__)
                    log_trace("📋 Raw Tavily response", full_response=str(search_result)[:1000])  # First 1000 chars
                    
                    if search_result:
                        # Extract content
                        if isinstance(search_result, str):
                            industry_insights = search_result
                        else:
                            industry_insights = str(search_result)
                        
                        log_trace("✅ Role research completed", length=len(industry_insights) if industry_insights else 0)
                else:
                    log_trace("⚠️ Tavily search tool not found")
        except Exception as e:
            log_trace("⚠️ Tavily search failed", error=str(e))
    
    # Build enhanced prompt with industry research
    if industry_insights:
        enhanced_prompt = f"""
**MANDATORY: Use the following industry research data:**

{industry_insights[:2000]}

{TARGET_BUILDER_PROMPT}

REQUIREMENTS:
1. You MUST extract and include the salary range mentioned in the research above
2. You MUST base focus_areas on actual requirements found in the research
3. You MUST use specific responsibilities mentioned in job postings above
4. Add a field 'industry_salary' with the exact salary found
5. If research mentions "10+ years experience", include that in requirements
"""
    else:
        enhanced_prompt = TARGET_BUILDER_PROMPT
    
    try:
        structured_model = model.with_structured_output(RoleDefinition)
        role_def = await structured_model.ainvoke([
            SystemMessage(content=enhanced_prompt),
            HumanMessage(content=user_message)
        ])
        
        # Save to MongoDB
        upsert_role(state["packet_id"], role_def)
        
        response = f"✅ **Target role defined: {role_def.title}**\n\n"
        response += f"**Level:** {role_def.level}\n\n"
        
        # Show industry salary if found
        if role_def.industry_salary:
            response += f"**💰 Industry Salary:** {role_def.industry_salary}\n\n"
        elif industry_insights and "$" in industry_insights:
            # Fallback: extract from insights if not in model
            import re
            salary_matches = re.findall(r'\$[\d,]+(?:\s*to\s*\$[\d,]+)?', industry_insights)
            if salary_matches:
                response += f"**💰 Industry Salary Range:** {', '.join(salary_matches[:2])}\n\n"
        
        if role_def.focus_areas:
            response += "**Focus Areas (based on industry research):**\n"
            for area in role_def.focus_areas[:3]:
                response += f"• {area}\n"
            response += "\n"
        
        if role_def.responsibilities:
            response += "**Key Responsibilities:**\n"
            for resp in role_def.responsibilities[:3]:
                response += f"• {resp}\n"
            response += "\n"
        
        response += "Great! Now, please share your projects. You can:\n"
        response += "• Paste project descriptions or your resume\n"
        response += "• Describe multiple projects at once\n"
        response += "• Include context, actions, and outcomes for each project"
        
        log_trace("✅ Target Builder completed", title=role_def.title, used_tavily=bool(industry_insights))
        
        return {
            "role_definition": role_def.model_dump(),
            "phase": "projects",
            "waiting_for": "projects",  # Set flag that we're waiting for projects
            "messages": [AIMessage(content=response)]
        }
    except Exception as e:
        log_error("Target Builder", e)
        return {
            "messages": [AIMessage(content="❌ I had trouble parsing that role. Please try describing it again with more detail.")]
        }

async def project_curator_node(state: WorkflowState) -> Dict:
    """Parse and store projects"""
    log_trace("📁 Project Curator activated")
    
    # Only process if the last message is from a human
    last_msg = state["messages"][-1]
    if not isinstance(last_msg, HumanMessage):
        log_trace("⚠️ No human message to process")
        return {
            "messages": [AIMessage(content="Please provide your project information.")],
            "waiting_for": "projects"
        }
    
    try:
        class ProjectList(BaseModel):
            projects: List[ProjectRecord]
        
        structured_model = model.with_structured_output(ProjectList)
        result = await structured_model.ainvoke([
            SystemMessage(content=PROJECT_CURATOR_PROMPT),
            last_msg  # Only use the human message
        ])
        
        # Save to MongoDB
        insert_projects(state["packet_id"], result.projects)
        
        response = f"✅ **Added {len(result.projects)} project(s)**\n\n"
        for i, proj in enumerate(result.projects, 1):
            response += f"**{i}. {proj.name}**\n"
            if proj.context:
                response += f"   *{proj.context[:100]}{'...' if len(proj.context) > 100 else ''}*\n"
        
        response += "\n**Your projects have been saved!**\n\n"
        response += "**Options:**\n"
        response += "• Type 'generate report' to create your impact analysis\n"
        response += "• Type 'add more' to add additional projects\n"
        response += "• Type 'review' to see your current projects\n\n"
        response += "*What would you like to do?*"
        
        log_trace("✅ Project Curator completed", count=len(result.projects))
        
        # Set waiting flag for user decision
        return {
            "projects": state["projects"] + [p.model_dump() for p in result.projects],
            "phase": "projects_review",
            "waiting_for": "report_confirmation",  # Wait for user to decide about report
            "messages": [AIMessage(content=response)]
        }
    except Exception as e:
        log_error("Project Curator", e)
        return {
            "messages": [AIMessage(content="❌ I had trouble parsing those projects. Please try describing them one at a time with clear structure.")]
        }

async def impact_analyzer_node(state: WorkflowState) -> Dict:
    """Generate impact report with Tavily research on role requirements"""
    log_trace("📊 Impact Analyzer activated")
    
    # Get role and projects from MongoDB (direct reads)
    role = get_role(state["packet_id"])
    projects = get_projects(state["packet_id"])
    
    if not role:
        return {
            "messages": [AIMessage(content="⚠️ Please define your target role first before I can analyze your impact.")]
        }
    
    if not projects:
        return {
            "messages": [AIMessage(content="⚠️ Please add some projects first so I can analyze your impact.")]
        }
    
    # Research role requirements using Tavily MCP
    industry_insights = None
    if MCP_CLIENT:
        try:
            log_trace("🔍 Researching role requirements via Tavily")
            tools = await get_mcp_tools()
            
            if tools:
                # Find Tavily search tool
                search_tool = None
                for tool in tools:
                    if 'tavily' in tool.name.lower() or 'search' in tool.name.lower():
                        search_tool = tool
                        break
                
                if search_tool:
                    # Research the role
                    search_query = f"{role.get('title', '')} {role.get('level', '')} requirements responsibilities salary 2024"
                    log_trace("🔎 Searching for role insights", query=search_query)
                    
                    # Invoke the search tool
                    search_result = await search_tool.ainvoke({"query": search_query})
                    
                    # DEBUG: Log the full response structure
                    log_trace("📋 Raw Tavily response type", type=type(search_result).__name__)
                    log_trace("📋 Raw Tavily response", full_response=str(search_result)[:1000])  # First 1000 chars
                    
                    if search_result:
                        # Try different ways to extract content
                        if hasattr(search_result, 'content'):
                            industry_insights = search_result.content
                            log_trace("📋 Using .content attribute", preview=str(industry_insights)[:200])
                        elif isinstance(search_result, dict):
                            log_trace("📋 Response is dict with keys", keys=list(search_result.keys()))
                            if 'content' in search_result:
                                industry_insights = search_result['content']
                            elif 'results' in search_result:
                                industry_insights = json.dumps(search_result['results'], indent=2)
                            else:
                                industry_insights = json.dumps(search_result, indent=2)
                            log_trace("📋 Extracted from dict", preview=str(industry_insights)[:200])
                        elif isinstance(search_result, str):
                            industry_insights = search_result
                            log_trace("📋 Response is string", preview=industry_insights[:200])
                        else:
                            industry_insights = str(search_result)
                            log_trace("📋 Converted to string", preview=industry_insights[:200])
                        
                        # Parse the string response into structured format for better model usage
                        if industry_insights and isinstance(industry_insights, str):
                            # Extract key information into bullet points
                            parsed_insights = "**Industry Research Findings:**\n\n"
                            
                            # Extract salary information
                            import re
                            salary_matches = re.findall(r'\$[\d,]+(?:\s*to\s*\$[\d,]+)?(?:\s*per\s*year)?', industry_insights)
                            if salary_matches:
                                parsed_insights += "**Salary Ranges Found:**\n"
                                for salary in salary_matches[:5]:  # Top 5 salary mentions
                                    parsed_insights += f"• {salary}\n"
                                parsed_insights += "\n"
                            
                            # Extract key requirements/skills if mentioned
                            if "requirements" in industry_insights.lower() or "skills" in industry_insights.lower():
                                parsed_insights += "**Key Requirements Mentioned:**\n"
                                # Add the content that mentions requirements
                                lines = industry_insights.split('\n')
                                for line in lines:
                                    if any(word in line.lower() for word in ['require', 'skill', 'experience', 'qualification']):
                                        parsed_insights += f"• {line.strip()[:150]}\n"
                                parsed_insights += "\n"
                            
                            # Add source URLs for credibility
                            urls = re.findall(r'https?://[^\s\n]+', industry_insights)
                            if urls:
                                parsed_insights += "**Sources:**\n"
                                for url in urls[:3]:
                                    parsed_insights += f"• {url}\n"
                            
                            # Use parsed version if we extracted useful info, otherwise use raw
                            if len(parsed_insights) > 100:
                                industry_insights = parsed_insights
                                log_trace("📊 Parsed Tavily data into structured format", length=len(parsed_insights))
                            
                        # Log final format being passed to prompt
                        log_trace("✅ Role research completed via Tavily", 
                                 final_length=len(str(industry_insights)) if industry_insights else 0)
                    else:
                        log_trace("⚠️ No search results found")
                else:
                    log_trace("⚠️ Tavily search tool not found")
        except Exception as e:
            log_trace("⚠️ Tavily search failed, continuing without", error=str(e))
    
    try:
        # Build detailed project summary with all rich data
        projects_detail = ""
        for i, p in enumerate(projects, 1):
            projects_detail += f"\n**Project {i}: {p.get('name', 'Unnamed')}**\n"
            projects_detail += f"- Role: {p.get('role', 'Not specified')}\n"
            projects_detail += f"- Duration: {p.get('duration', p.get('quarter', 'Not specified'))}\n"
            projects_detail += f"- Team Size: {p.get('team_size', 'Not specified')}\n"
            projects_detail += f"- Context: {p.get('context', 'No context')}\n"
            
            if p.get('metrics'):
                projects_detail += f"- Metrics:\n"
                for m in p.get('metrics', []):
                    improvement = f" ({m.get('improvement')})" if m.get('improvement') else ""
                    unit = f" {m.get('unit')}" if m.get('unit') else ""
                    projects_detail += f"  • {m.get('name')}: {m.get('value')}{unit}{improvement}\n"
            
            if p.get('technologies'):
                projects_detail += f"- Technologies: {', '.join(p.get('technologies', []))}\n"
            
            if p.get('stakeholders'):
                projects_detail += f"- Stakeholders: {', '.join(p.get('stakeholders', []))}\n"
            
            projects_detail += f"- Visibility: {p.get('visibility', 'team')}-level impact\n"
            projects_detail += f"- Impact Rating: {p.get('impact_rating', 0)}/5\n"
        
        prompt = IMPACT_ANALYZER_PROMPT.format(
            role_title=role.get("title", "Unknown"),
            role_level=role.get("level", ""),
            focus_areas=", ".join(role.get("focus_areas", [])),
            responsibilities=", ".join(role.get("responsibilities", [])[:3]),
            industry_insights=industry_insights if industry_insights else "No external research available",
            project_count=len(projects),
            projects_detail=projects_detail
        )
        
        structured_model = model.with_structured_output(ImpactReport)
        report = await structured_model.ainvoke([
            SystemMessage(content=prompt)
        ])
        
        # Save to MongoDB
        upsert_report(state["packet_id"], report)
        
        response = f"## 📊 Impact Report Generated\n\n"
        response += f"**Executive Summary:**\n{report.executive_summary}\n\n"
        
        if report.strengths:
            response += f"### ✅ Key Strengths\n"
            for strength in report.strengths:
                response += f"• {strength}\n"
            response += "\n"
        
        if report.gaps:
            response += f"### ⚠️ Gaps to Address\n"
            for gap in report.gaps:
                response += f"• {gap}\n"
            response += "\n"
        
        if report.recommendations:
            response += f"### 💡 Recommendations\n"
            for rec in report.recommendations:
                response += f"• {rec}\n"
            response += "\n"
        
        response += "---\n\n"
        response += "**What would you like to do next?**\n"
        response += "• Type 'find mentors' to discover similar professionals on LinkedIn\n"
        response += "• Type 'add projects' to strengthen your case\n"
        response += "• Type 'download' for your promotion packet\n"
        response += "• Type 'done' if you're satisfied\n\n"
        response += "*Waiting for your decision...*"
        
        log_trace("✅ Impact Analyzer completed")
        
        return {
            "impact_report": report.model_dump(),
            "phase": "post_report",
            "waiting_for": "post_report_decision",  # Wait for user's next action
            "messages": [AIMessage(content=response)]
        }
    except Exception as e:
        log_error("Impact Analyzer", e)
        return {
            "messages": [AIMessage(content="❌ I encountered an error generating the report. Please try again.")]
        }

async def mentor_finder_node(state: WorkflowState) -> Dict:
    """Find similar professionals on LinkedIn using Tavily search"""
    log_trace("👥 Mentor Finder activated")
    
    role = get_role(state["packet_id"])
    if not role:
        return {
            "messages": [AIMessage(content="⚠️ Please define your target role first before I can find mentors.")]
        }
    
    # Search LinkedIn profiles via Tavily
    mentors_found = []
    if MCP_CLIENT:
        try:
            tools = await get_mcp_tools()
            search_tool = None
            for tool in tools:
                if 'tavily' in tool.name.lower() or 'search' in tool.name.lower():
                    search_tool = tool
                    break
            
            if search_tool:
                # Use LLM to generate title variations for better search results
                variation_prompt = f"""Given the target role: {role.get('title', '')}
                
Generate 3-4 variations of this title that professionals might use on LinkedIn.
Include abbreviations (VP vs Vice President), alternative phrasings, and related titles.

Return ONLY a search query string with OR operators, like:
(VP Robotics OR "Vice President of Robotics" OR "Director Robotics Engineering" OR "Head of Robotics")

Be concise and focus on realistic LinkedIn titles."""

                try:
                    # Get variations from LLM
                    variation_response = await model.ainvoke([
                        SystemMessage(content=variation_prompt)
                    ])
                    title_variations = variation_response.content.strip()
                    
                    # Combine with domain search
                    search_query = f"site:linkedin.com/in/ {title_variations}"
                    log_trace("🔎 Searching LinkedIn with LLM-generated variations", 
                             original_title=role.get('title', ''),
                             variations=title_variations[:100])
                    
                except Exception as e:
                    # Fallback to simple search if LLM fails
                    log_trace("⚠️ LLM variation generation failed, using simple search", error=str(e))
                    search_query = f"site:linkedin.com/in/ \"{role.get('title', '')}\" \"{role.get('level', '')}\""
                
                search_result = await search_tool.ainvoke({"query": search_query})
                
                if search_result:
                    # Extract profiles from search results
                    result_text = str(search_result) if not isinstance(search_result, str) else search_result
                    
                    # Parse out LinkedIn URLs and snippets
                    import re
                    linkedin_urls = re.findall(r'https://www\.linkedin\.com/in/[^/\s]+', result_text)
                    
                    # Extract information about each profile found
                    lines = result_text.split('\n')
                    profiles = []
                    current_profile = {}
                    
                    for line in lines:
                        if 'Title:' in line:
                            if current_profile:
                                profiles.append(current_profile)
                            current_profile = {'title': line.split('Title:')[1].strip()}
                        elif 'URL:' in line:
                            current_profile['url'] = line.split('URL:')[1].strip()
                        elif 'Content:' in line:
                            current_profile['snippet'] = line.split('Content:')[1].strip()[:200]
                    
                    if current_profile:
                        profiles.append(current_profile)
                    
                    # If no profiles parsed, try to extract any LinkedIn URLs found
                    if len(profiles) == 0 and linkedin_urls:
                        log_trace("⚠️ Could not parse profiles, using URL extraction fallback")
                        for url in linkedin_urls[:5]:
                            profiles.append({
                                'title': 'LinkedIn Professional',
                                'url': url,
                                'snippet': 'View profile for details'
                            })
                    
                    log_trace("✅ Found LinkedIn profiles", count=len(profiles), 
                             had_urls=len(linkedin_urls), 
                             sample_response=result_text[:200] if len(profiles) == 0 else "")
                    
                    # Format mentor recommendations
                    response = f"## 👥 Similar Professionals on LinkedIn\n\n"
                    response += f"*Found professionals in similar {role.get('title', '')} roles:*\n\n"
                    
                    for i, profile in enumerate(profiles[:5], 1):  # Show top 5
                        response += f"### {i}. {profile.get('title', 'Professional')}\n"
                        if profile.get('snippet'):
                            response += f"{profile['snippet']}...\n"
                        if profile.get('url'):
                            response += f"**[View LinkedIn Profile]({profile['url']})**\n\n"
                    
                    response += "💡 **Tips for reaching out:**\n"
                    response += "• Mention specific accomplishments from their profile\n"
                    response += "• Ask about their journey to the role\n"
                    response += "• Request a brief informational interview\n"
                    response += "• Share your career goals and ask for advice\n\n"
                    
                    response += "**Options:**\n"
                    response += "• Type 'add projects' to add more accomplishments\n"
                    response += "• Type 'download' for your complete packet\n"
                    response += "• Type 'done' if you're finished\n\n"
                    response += "*What would you like to do next?*"
                    
                    mentors_found = profiles
                    
                    return {
                        "messages": [AIMessage(content=response)],
                        "phase": "post_mentors",
                        "waiting_for": "next_action",
                        "mentors_found": profiles[:5]  # Store top 5 for UI panel
                    }
                    
        except Exception as e:
            log_error("Mentor Finder", e)
    
    return {
        "messages": [AIMessage(content="❌ Could not find mentors at this time. Please try again later.")]
    }

async def guidance_agent_node(state: WorkflowState) -> Dict:
    """Handle general guidance and unclear requests"""
    log_trace("💬 Guidance Agent activated")
    
    role = get_role(state["packet_id"])
    projects = get_projects(state["packet_id"])
    report = get_report(state["packet_id"])
    
    # Check if we need more project details
    if state.get("intent") == "need_more_project_details":
        response_text = """I see you're ready to share your projects! To create a comprehensive impact report, please provide specific details about your work. For example:

**Project Name:** [What you called this initiative]
**Context:** [The problem or opportunity you addressed]
**Your Actions:** [What you specifically did]
**Outcomes:** [Results, metrics, or impact achieved]

You can share multiple projects at once. The more detail you provide, the better I can assess alignment with your VP of AI target role."""
        
        return {
            "messages": [AIMessage(content=response_text)],
            "waiting_for": "projects"  # Keep waiting for proper project input
        }
    
    # Check if no role is defined and user seems to want to define one
    if not role and state.get("phase") == "setup":
        response_text = """I understand you want to become a VP of AI! Let me help you define that role properly.

Please share more details about the VP of AI position you're targeting:
- What company or industry?
- What specific AI areas would you oversee?
- What level of responsibility are you aiming for?

Or you can simply confirm "I want to become a VP of AI" and I'll create a comprehensive role definition for you."""
        
        # Force route to target_builder on next message
        return {
            "messages": [AIMessage(content=response_text)],
            "route": "target_builder"
        }
    
    
    context = f"""You are a helpful career coach for promotion preparation.

Current state:
- Phase: {state["phase"]}
- Has target role defined: {"Yes - " + role.get("title", "") if role else "No"}
- Number of projects: {len(projects)}
- Has impact report: {"Yes" if report else "No"}

Provide helpful guidance based on where they are in the process.
If they haven't defined a target role yet, encourage them to do so.
If they have a role but no projects, encourage them to add projects with specific details.
If they have both, suggest they can add more projects or download their packet.
Be encouraging, specific, and concise."""
    
    try:
        messages = state["messages"][-5:] if state["messages"] else []
        response = await model.ainvoke([
            SystemMessage(content=context),
            *messages
        ])
        
        log_trace("✅ Guidance Agent completed")
        
        return {
            "messages": [AIMessage(content=response.content)]
        }
    except Exception as e:
        log_error("Guidance Agent", e)
        return {
            "messages": [AIMessage(content="I'm here to help! Try describing your target role or sharing your projects.")]
        }

# ============================================================================
# ROUTING LOGIC
# ============================================================================

def route_supervisor(state: WorkflowState) -> str:
    """Route based on supervisor decision"""
    route = state.get("route", "guidance_agent")
    
    # Map 'end' to END constant
    if route == "end":
        return END
    elif route == "iteration":
        # After seeing the report, user wants to add more projects
        return "project_curator"
    elif route == "wait_for_input":
        # Need to wait for user input
        return END  # End here to wait for next user message
    else:
        return route

# ============================================================================
# LANGGRAPH WORKFLOW
# ============================================================================

workflow = StateGraph(WorkflowState)

# Add nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("target_builder", target_builder_node)
workflow.add_node("project_curator", project_curator_node)
workflow.add_node("impact_analyzer", impact_analyzer_node)
workflow.add_node("mentor_finder", mentor_finder_node)
workflow.add_node("guidance_agent", guidance_agent_node)
workflow.add_node("wait_for_input", wait_for_input_node)

# Set entry point
workflow.set_entry_point("supervisor")

# Add routing from supervisor - include END in the mapping
workflow.add_conditional_edges(
    "supervisor",
    route_supervisor,
    {
        "target_builder": "target_builder",
        "project_curator": "project_curator",
        "impact_analyzer": "impact_analyzer",
        "mentor_finder": "mentor_finder",
        "guidance_agent": "guidance_agent",
        "wait_for_input": END,
        END: END  # Map END to itself to fix KeyError
    }
)

# All agents return to supervisor for next routing, except special cases
workflow.add_edge("target_builder", "wait_for_input")  # After setting target, interrupt for projects
workflow.add_edge("guidance_agent", "supervisor")
workflow.add_edge("wait_for_input", "supervisor")  # After interrupt resolves, go back to supervisor
workflow.add_edge("project_curator", "supervisor")  # Go back to supervisor for user decision
workflow.add_edge("impact_analyzer", "supervisor")  # Back to supervisor for iteration
workflow.add_edge("mentor_finder", "supervisor")  # Back to supervisor after finding mentors

# Compile with checkpointer
app = workflow.compile(checkpointer=checkpointer)

log_trace("✅ LangGraph workflow compiled")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_role_panel(packet_id: str) -> Dict:
    """Format role data for UI display"""
    role = get_role(packet_id)
    if not role:
        return {"status": "No target role defined yet"}
    
    return {
        "title": role.get("title", ""),
        "level": role.get("level", ""),
        "industry_salary": role.get("industry_salary", "Not found"),
        "focus_areas": role.get("focus_areas", []),
        "responsibilities": role.get("responsibilities", [])[:3],
        "core_competencies": role.get("core_competencies", [])[:3]
    }

def format_projects_panel(packet_id: str) -> List[Dict]:
    """Format all project data with rich details for display"""
    projects = get_projects(packet_id)
    if not projects:
        return []
    
    formatted_projects = []
    for p in projects:
        # Format metrics for better display
        formatted_metrics = []
        for m in p.get("metrics", []):
            metric_str = f"{m.get('name')}: {m.get('value')}"
            if m.get('unit'):
                metric_str += f" {m.get('unit')}"
            if m.get('improvement'):
                metric_str += f" ({m.get('improvement')})"
            formatted_metrics.append(metric_str)
        
        project_details = {
            "🎯 Name": p.get("name", "Unnamed"),
            "📅 Timeline": {
                "Duration": p.get("duration", "Not specified"),
                "Quarter": p.get("quarter", "Not specified")
            },
            "👤 Role": p.get("role", "Not specified"),
            "👥 Team Size": p.get("team_size", "Not specified"),
            "📝 Context": p.get("context", ""),
            "🎬 Actions": p.get("actions", []),
            "📊 Outcomes": p.get("outcomes", []),
            "📈 Metrics": formatted_metrics if formatted_metrics else ["No metrics captured"],
            "🛠️ Technologies": p.get("technologies", []),
            "👔 Stakeholders": p.get("stakeholders", []),
            "🎯 Focus Areas": p.get("related_focus_areas", []),
            "💪 Skills": p.get("skills_demonstrated", []),
            "🚧 Challenges": p.get("challenges_overcome", []),
            "📢 Visibility": p.get("visibility", "team"),
            "⭐ Impact": f"{p.get('impact_rating', 0)}/5"
        }
        
        # Only include evidence links if they exist
        if p.get("evidence_links"):
            project_details["🔗 Evidence"] = p.get("evidence_links")
        
        formatted_projects.append(project_details)
    
    return formatted_projects

def format_projects_table(packet_id: str) -> List[List[str]]:
    """Format projects for table display"""
    projects = get_projects(packet_id)
    if not projects:
        return [["No projects yet", "", "", ""]]
    
    rows = []
    for p in projects:
        # Build metrics summary
        metrics_summary = ""
        if p.get("metrics"):
            first_metric = p["metrics"][0]
            metrics_summary = f"{first_metric.get('value')} {first_metric.get('unit', '')}"
            if first_metric.get('improvement'):
                metrics_summary += f" ({first_metric.get('improvement')})"
        
        rows.append([
            p.get("name", "Unnamed"),
            p.get("duration", p.get("quarter", "")),
            metrics_summary or p.get("visibility", ""),
            str(p.get("impact_rating", 0))
        ])
    return rows

def format_project_details(packet_id: str, selected_row: Optional[List] = None) -> Dict:
    """Format detailed project information for display when a row is selected"""
    projects = get_projects(packet_id)
    
    if not projects or not selected_row or len(selected_row) == 0:
        return {"message": "Select a project from the table to view details"}
    
    # Find project by name (first column of selected row)
    project_name = selected_row[0] if isinstance(selected_row, list) else None
    if not project_name or project_name == "No projects yet":
        return {"message": "No project selected"}
    
    # Find the matching project
    matching_project = None
    for p in projects:
        if p.get("name") == project_name:
            matching_project = p
            break
    
    if not matching_project:
        return {"message": "Project not found"}
    
    p = matching_project
    
    # Build comprehensive details object
    details = {
        "🎯 Project Name": p.get("name", "Unnamed"),
        "📅 Timeline": {
            "Duration": p.get("duration", "Not specified"),
            "Quarter": p.get("quarter", "Not specified")
        },
        "👥 Team & Role": {
            "Your Role": p.get("role", "Not specified"),
            "Team Size": p.get("team_size", "Not specified")
        },
        "📝 Context": p.get("context", "No context provided"),
        "🎬 Actions Taken": p.get("actions", []),
        "📊 Outcomes": p.get("outcomes", []),
        "📈 Metrics": [
            {
                "Metric": m.get("name"),
                "Value": f"{m.get('value')} {m.get('unit', '')}",
                "Improvement": m.get("improvement", "")
            } for m in p.get("metrics", [])
        ] if p.get("metrics") else "No metrics captured",
        "🛠️ Technologies": p.get("technologies", []),
        "👔 Stakeholders": p.get("stakeholders", []),
        "🎯 Focus Areas": p.get("related_focus_areas", []),
        "💪 Skills Demonstrated": p.get("skills_demonstrated", []),
        "🚧 Challenges Overcome": p.get("challenges_overcome", []),
        "🔗 Evidence/Links": p.get("evidence_links", []) if p.get("evidence_links") else "None provided",
        "📢 Visibility Level": p.get("visibility", "team"),
        "⭐ Impact Rating": f"{p.get('impact_rating', 0)}/5"
    }
    
    return details

def format_mentors_panel(mentors_data: List[Dict]) -> List[Dict]:
    """Format mentor profiles for UI display"""
    if not mentors_data:
        return []
    
    formatted_mentors = []
    for mentor in mentors_data:
        # Handle the actual structure of profiles
        formatted_mentors.append({
            "Title": mentor.get("title", "Professional"),
            "Summary": mentor.get("snippet", "")[:150] + "..." if mentor.get("snippet") else "No summary available",
            "LinkedIn": mentor.get("url", "No URL")
        })
    
    return formatted_mentors

def format_report_panel(packet_id: str) -> str:
    """Format report for markdown display"""
    report = get_report(packet_id)
    if not report:
        return "*No impact report generated yet*"
    
    md = f"### Executive Summary\n{report.get('executive_summary', '')}\n\n"
    
    if report.get('strengths'):
        md += "### ✅ Strengths\n"
        for s in report['strengths']:
            md += f"- {s}\n"
        md += "\n"
    
    if report.get('gaps'):
        md += "### ⚠️ Gaps\n"
        for g in report['gaps']:
            md += f"- {g}\n"
        md += "\n"
    
    return md

def generate_markdown_export(packet_id: str) -> str:
    """Generate complete markdown document for download"""
    role = get_role(packet_id)
    projects = get_projects(packet_id)
    report = get_report(packet_id)
    
    md = "# Promotion Packet\n\n"
    md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    
    if role:
        md += f"## 🎯 Target Role: {role.get('title', '')}\n\n"
        md += f"**Level:** {role.get('level', '')}\n\n"
        
        if role.get('focus_areas'):
            md += "**Focus Areas:**\n"
            for fa in role['focus_areas']:
                md += f"- {fa}\n"
            md += "\n"
        
        if role.get('responsibilities'):
            md += "**Key Responsibilities:**\n"
            for resp in role['responsibilities']:
                md += f"- {resp}\n"
            md += "\n"
    
    if projects:
        md += "## 📁 Projects\n\n"
        for i, p in enumerate(projects, 1):
            md += f"### {i}. {p.get('name', 'Unnamed Project')}\n"
            md += f"**Duration:** {p.get('duration', 'Not specified')}\n"
            md += f"**Role:** {p.get('role', 'Not specified')}\n\n"
            md += f"**Context:** {p.get('context', '')}\n\n"
            
            if p.get('actions'):
                md += "**Actions:**\n"
                for action in p['actions']:
                    md += f"- {action}\n"
                md += "\n"
            
            if p.get('outcomes'):
                md += "**Outcomes:**\n"
                for outcome in p['outcomes']:
                    md += f"- {outcome}\n"
                md += "\n"
            
            if p.get('metrics'):
                md += "**Metrics:**\n"
                for m in p['metrics']:
                    md += f"- {m.get('name')}: {m.get('value')} {m.get('unit', '')}"
                    if m.get('improvement'):
                        md += f" ({m.get('improvement')})"
                    md += "\n"
                md += "\n"
    
    if report:
        md += "## 📊 Impact Report\n\n"
        md += f"{report.get('executive_summary', '')}\n\n"
        
        if report.get('strengths'):
            md += "### Strengths\n"
            for s in report['strengths']:
                md += f"- {s}\n"
            md += "\n"
        
        if report.get('gaps'):
            md += "### Gaps to Address\n"
            for g in report['gaps']:
                md += f"- {g}\n"
            md += "\n"
        
        if report.get('recommendations'):
            md += "### Recommendations\n"
            for r in report['recommendations']:
                md += f"- {r}\n"
    
    return md

# ============================================================================
# GRADIO UI
# ============================================================================

def create_ui():
    with gr.Blocks(theme=gr.themes.Soft(), title="Promotion Advisor") as demo:
        # State variables
        packet_id_state = gr.State(value=lambda: create_packet("demo_user"))
        thread_id_state = gr.State(value=lambda: str(uuid.uuid4()))
        
        gr.Markdown("# 🚀 Promotion Advisor — Multi-Agent Workspace")
        gr.Markdown("*AI-powered promotion packet preparation with LangGraph + MongoDB*")
        
        # First row: Target Role and Projects
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 🎯 Target Role")
                target_panel = gr.JSON(label="", value={})
            
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Projects")
                projects_panel = gr.JSON(label="", value=[])
        
        # Second row: Impact Report and Mentors side by side
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Impact Report")
                report_panel = gr.Markdown("*No report generated yet*")
            
            with gr.Column(scale=1):
                gr.Markdown("### 👥 Similar Professionals")
                mentors_panel = gr.JSON(label="", value=[])
        
        # Third row: Execution Trace (full width)
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Accordion("### 🔍 Execution Trace", open=False):
                    trace_html = gr.HTML(value=format_trace_for_ui())
                    refresh_trace_btn = gr.Button("Refresh Trace", size="sm")
        
        gr.Markdown("---")
        
        # Chat interface
        chatbot = gr.Chatbot(
            height=400,
            label="Chat",
            value=[
                {"role": "assistant", "content": "👋 Welcome! I'll help you prepare your promotion packet.\n\n"
                 "**To get started, tell me:** What role are you targeting for promotion?\n\n"
                 "*Example: \"I want to become a Staff Software Engineer\"*"}
            ],
            type="messages"
        )
        
        msg = gr.Textbox(
            label="Your message",
            placeholder="Describe your target role or paste project information...",
            lines=3
        )
        
        with gr.Row():
            send_btn = gr.Button("📤 Send", variant="primary", scale=2)
            clear_btn = gr.Button("🔄 Clear Chat", scale=1)
            download_btn = gr.Button("⬇️ Download Packet", scale=1)
        
        # Event handlers
        async def chat_handler(message: str, history: list, packet_id: str, thread_id: str):
            if not message.strip():
                return history, "", format_role_panel(packet_id), format_projects_panel(packet_id), format_report_panel(packet_id)
            
            log_trace("💬 User message received", preview=message[:50])
            
            # Add user message to history in messages format
            history = history + [{"role": "user", "content": message}]
            
            try:
                # Check if we need to resume from an interrupt
                # Get the current state to see if we're interrupted
                config = {"configurable": {"thread_id": thread_id}}
                
                # Try to get current state
                current_state = app.get_state(config)
                
                # Check if we're in an interrupted state
                if current_state and current_state.next:
                    # We're interrupted, need to resume with Command
                    from langgraph.types import Command
                    log_trace("📥 Resuming from interrupt", next_nodes=current_state.next)
                    result = await app.ainvoke(
                        Command(resume=HumanMessage(content=message)),
                        config=config
                    )
                else:
                    # Normal invocation
                    result = await app.ainvoke(
                        {
                            "messages": [HumanMessage(content=message)],
                            "packet_id": packet_id,
                            "phase": "setup",
                            "projects": [],
                            "mentors_found": None,  # Initialize mentors_found
                            "user_id": "demo_user",
                            "waiting_for": None
                        },
                        config=config
                    )
                
                # Extract assistant response
                assistant_msg = result["messages"][-1].content
                history.append({"role": "assistant", "content": assistant_msg})
                
                log_trace("✅ Workflow completed")
                
            except Exception as e:
                log_error("Chat Handler", e)
                history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
            
            # Refresh UI panels
            mentors = result.get("mentors_found", []) if result else []
            return (
                history,
                "",
                format_role_panel(packet_id),
                format_projects_panel(packet_id),
                format_report_panel(packet_id),
                format_mentors_panel(mentors)
            )
        
        def clear_chat():
            """Reset to new session"""
            new_packet_id = create_packet("demo_user")
            new_thread_id = str(uuid.uuid4())
            
            initial_history = [
                {"role": "assistant", "content": "👋 Chat cleared! Let's start fresh.\n\n"
                 "**What role are you targeting for promotion?**"}
            ]
            
            log_trace("🔄 Chat cleared", new_packet_id=new_packet_id)
            
            return (
                new_packet_id,
                new_thread_id,
                initial_history,
                {},
                [],
                "*No report generated yet*",
                []  # Empty mentors panel
            )
        
        def download_packet(packet_id: str):
            """Generate markdown file for download"""
            try:
                md_content = generate_markdown_export(packet_id)
                
                # Create outputs directory if it doesn't exist
                output_dir = Path("outputs")
                output_dir.mkdir(exist_ok=True)
                
                # Save to outputs directory
                output_path = output_dir / f"promotion_packet_{packet_id[:8]}.md"
                with open(output_path, "w") as f:
                    f.write(md_content)
                
                log_trace("📥 Packet downloaded", path=str(output_path))
                return gr.update(value=f"✅ Downloaded to: {output_path}")
            except Exception as e:
                log_error("Download", e)
                return gr.update(value=f"❌ Download failed: {str(e)}")
        
        def refresh_trace():
            return format_trace_for_ui()
        
        def show_project_details(evt: gr.SelectData, packet_id: str):
            """Show detailed project information when a row is selected"""
            if evt and evt.value:
                return format_project_details(packet_id, evt.value)
            return {"message": "Select a project to view details"}
        
        # Wire up events
        send_btn.click(
            chat_handler,
            inputs=[msg, chatbot, packet_id_state, thread_id_state],
            outputs=[chatbot, msg, target_panel, projects_panel, report_panel, mentors_panel]
        )
        
        msg.submit(
            chat_handler,
            inputs=[msg, chatbot, packet_id_state, thread_id_state],
            outputs=[chatbot, msg, target_panel, projects_panel, report_panel, mentors_panel]
        )
        
        clear_btn.click(
            clear_chat,
            outputs=[packet_id_state, thread_id_state, chatbot, target_panel, projects_panel, report_panel, mentors_panel]
        )
        
        download_btn.click(
            download_packet,
            inputs=[packet_id_state],
            outputs=[msg]
        )
        
        refresh_trace_btn.click(
            refresh_trace,
            outputs=[trace_html]
        )
    
    return demo

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    log_trace("🚀 Starting Promotion Advisor")
    
    if not OPENAI_API_KEY:
        print("⚠️ WARNING: OPENAI_API_KEY not set!")
    
    demo = create_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)