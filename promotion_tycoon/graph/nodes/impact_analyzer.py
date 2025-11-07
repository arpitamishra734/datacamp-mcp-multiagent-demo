from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.models import ImpactReport, WorkflowState
from promotion_tycoon.prompts import IMPACT_ANALYZER_PROMPT
from promotion_tycoon.storage import get_role, get_projects, upsert_report
from promotion_tycoon.tracing import log_trace, log_error
from promotion_tycoon.mcp_client import get_mcp_tools


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def impact_analyzer_node(state: WorkflowState):
    log_trace("📊 Impact Analyzer activated")
    role = get_role(state["packet_id"]); projects = get_projects(state["packet_id"])
    if not role:
        return {"messages": [AIMessage(content="⚠️ Define your target role first.")]}
    if not projects:
        return {"messages": [AIMessage(content="⚠️ Add some projects first.")]}
    industry_insights = None
    try:
        tools = await get_mcp_tools()
        search_tool = next((t for t in tools if "tavily" in t.name.lower() or "search" in t.name.lower()), None)
        if search_tool:
            q = f"{role.get('title','')} {role.get('level','')} requirements responsibilities salary 2024"
            log_trace("🔎 Searching for role insights", query=q)
            res = await search_tool.ainvoke({"query": q})
            industry_insights = str(res) if res else None
    except Exception as e:
        log_trace("⚠️ Tavily search failed, continuing without", error=str(e))

    details = ""
    for i, p in enumerate(projects, 1):
        details += f"\n**Project {i}: {p.get('name','Unnamed')}**\n"
        details += f"- Role: {p.get('role','Not specified')}\n"
        details += f"- Duration: {p.get('duration', p.get('quarter','Not specified'))}\n"
        details += f"- Team Size: {p.get('team_size','Not specified')}\n"
        details += f"- Context: {p.get('context','No context')}\n"
        if p.get('metrics'):
            details += "- Metrics:\n"
            for m in p['metrics']:
                imp = f" ({m.get('improvement')})" if m.get('improvement') else ""
                unit = f" {m.get('unit')}" if m.get('unit') else ""
                details += f"  • {m.get('name')}: {m.get('value')}{unit}{imp}\n"
        if p.get('technologies'):
            details += f"- Technologies: {', '.join(p['technologies'])}\n"
        if p.get('stakeholders'):
            details += f"- Stakeholders: {', '.join(p['stakeholders'])}\n"
        details += f"- Visibility: {p.get('visibility','team')}-level impact\n"
        details += f"- Impact Rating: {p.get('impact_rating',0)}/5\n"

    prompt = IMPACT_ANALYZER_PROMPT.format(
        role_title=role.get("title","Unknown"),
        role_level=role.get("level",""),
        focus_areas=", ".join(role.get("focus_areas", [])),
        responsibilities=", ".join(role.get("responsibilities", [])[:3]),
        industry_insights=industry_insights or "No external research available",
        project_count=len(projects),
        projects_detail=details,
    )

    try:
        structured = model.with_structured_output(ImpactReport)
        report = await structured.ainvoke([SystemMessage(content=prompt)])
        upsert_report(state["packet_id"], report)

        lines = [ "## 📊 Impact Report Generated",
                  "", f"**Executive Summary:**\n{report.executive_summary}", "" ]
        if report.strengths:
            lines += ["### ✅ Key Strengths", *[f"• {s}" for s in report.strengths], ""]
        if report.gaps:
            lines += ["### ⚠️ Gaps to Address", *[f"• {g}" for g in report.gaps], ""]
        if report.recommendations:
            lines += ["### 💡 Recommendations", *[f"• {r}" for r in report.recommendations], ""]
        lines += ["---", "", "**What next?**",
                  "• Type 'find mentors'  • Type 'add projects'  • Type 'download'  • Type 'done'", "*Waiting for your decision...*"]

        log_trace("✅ Impact Analyzer completed")
        return {
            "impact_report": report.model_dump(),
            "phase": "post_report",
            "waiting_for": "post_report_decision",
            "messages": [AIMessage(content="\n".join(lines))]
        }
    except Exception as e:
        log_error("Impact Analyzer", e)
        return {"messages": [AIMessage(content="❌ Error generating the report. Please try again.")]}
