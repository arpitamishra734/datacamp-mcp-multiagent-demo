from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.storage import get_role, get_projects, get_report
from promotion_tycoon.tracing import log_trace, log_error
from promotion_tycoon.models import WorkflowState


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def guidance_agent_node(state: WorkflowState):
    log_trace("💬 Guidance Agent activated")
    role = get_role(state["packet_id"]); projects = get_projects(state["packet_id"]); report = get_report(state["packet_id"])
    context = f"""You are a helpful career coach.
Phase: {state['phase']}; Has role: {'Yes' if role else 'No'}; Projects: {len(projects)}; Has report: {'Yes' if report else 'No'}."""
    try:
        messages = state["messages"][-5:] if state["messages"] else []
        resp = await model.ainvoke([SystemMessage(content=context), *messages])
        log_trace("✅ Guidance Agent completed")
        return {"messages": [AIMessage(content=resp.content)]}
    except Exception as e:
        log_error("Guidance Agent", e)
        return {"messages": [AIMessage(content="I'm here to help! Describe your target role or share your projects.")]}
