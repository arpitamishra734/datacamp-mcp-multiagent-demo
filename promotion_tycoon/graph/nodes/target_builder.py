from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.models import RoleDefinition, WorkflowState
from promotion_tycoon.prompts import TARGET_BUILDER_PROMPT
from promotion_tycoon.storage import upsert_role, get_role, get_projects, get_report
from promotion_tycoon.tracing import log_trace, log_error
from promotion_tycoon.mcp_client import get_mcp_tools



model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def target_builder_node(state: WorkflowState):
    log_trace("🎯 Target Builder activated")
    user_message = state["messages"][-1].content

    industry_insights = None
    try:
        tools = await get_mcp_tools()
        search_tool = next((t for t in tools if "tavily" in t.name.lower() or "search" in t.name.lower()), None)
        if search_tool:
            q = f"{user_message} requirements responsibilities salary skills qualifications 2024 2025"
            log_trace("🔎 Searching for role insights", query=q)
            search_result = await search_tool.ainvoke({"query": q})
            industry_insights = str(search_result) if search_result else None
    except Exception as e:
        log_trace("⚠️ Tavily search failed", error=str(e))

    enhanced = TARGET_BUILDER_PROMPT
    if industry_insights:
        enhanced = f"**MANDATORY: Use the following industry research data:**\n\n{industry_insights[:2000]}\n\n{TARGET_BUILDER_PROMPT}\n"

    try:
        structured = model.with_structured_output(RoleDefinition)
        role_def = await structured.ainvoke([SystemMessage(content=enhanced), HumanMessage(content=user_message)])
        upsert_role(state["packet_id"], role_def)

        response = [f"✅ **Target role defined: {role_def.title}**",
                    f"**Level:** {role_def.level}"]
        if role_def.industry_salary:
            response.append(f"**💰 Industry Salary:** {role_def.industry_salary}")
        if role_def.focus_areas:
            response.append("**Focus Areas (based on industry research):**")
            response.extend([f"• {fa}" for fa in role_def.focus_areas[:3]])
        if role_def.responsibilities:
            response.append("**Key Responsibilities:**")
            response.extend([f"• {r}" for r in role_def.responsibilities[:3]])
        response.append("Great! Now share your projects (context, actions, outcomes, metrics).")

        log_trace("✅ Target Builder completed", title=role_def.title, used_tavily=bool(industry_insights))
        return {
            "role_definition": role_def.model_dump(),
            "phase": "projects",
            "waiting_for": "projects",
            "messages": [AIMessage(content="\n\n".join(response))]
        }
    except Exception as e:
        log_error("Target Builder", e)
        return {"messages": [AIMessage(content="❌ I had trouble parsing that role. Please try again with more detail.")]}
