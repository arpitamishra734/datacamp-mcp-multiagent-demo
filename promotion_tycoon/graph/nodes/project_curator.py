from typing import List
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.models import ProjectRecord, WorkflowState
from promotion_tycoon.prompts import PROJECT_CURATOR_PROMPT
from promotion_tycoon.storage import insert_projects
from promotion_tycoon.tracing import log_trace, log_error


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class ProjectList(BaseModel):
    projects: List[ProjectRecord]

async def project_curator_node(state: WorkflowState):
    log_trace("📁 Project Curator activated")
    last_msg = state["messages"][-1]
    if not isinstance(last_msg, HumanMessage):
        return {"messages": [AIMessage(content="Please provide your project information.")], "waiting_for": "projects"}

    try:
        structured = model.with_structured_output(ProjectList)
        result = await structured.ainvoke([SystemMessage(content=PROJECT_CURATOR_PROMPT), last_msg])
        insert_projects(state["packet_id"], result.projects)

        lines = [f"✅ **Added {len(result.projects)} project(s)**", ""]
        for i, p in enumerate(result.projects, 1):
            ctx = (p.context[:100] + "...") if p.context and len(p.context) > 100 else p.context
            lines.append(f"**{i}. {p.name}**")
            if ctx: lines.append(f"   *{ctx}*")
        lines += ["", "**Options:**",
                  "• Type 'generate report' to create your impact analysis",
                  "• Type 'add more' to add additional projects",
                  "• Type 'review' to see your current projects",
                  "", "*What would you like to do?*"]

        log_trace("✅ Project Curator completed", count=len(result.projects))
        return {
            "projects": state["projects"] + [p.model_dump() for p in result.projects],
            "phase": "projects_review",
            "waiting_for": "report_confirmation",
            "messages": [AIMessage(content="\n".join(lines))]
        }
    except Exception as e:
        log_error("Project Curator", e)
        return {"messages": [AIMessage(content="❌ I had trouble parsing those projects. Please try one at a time with clear structure.")]}
