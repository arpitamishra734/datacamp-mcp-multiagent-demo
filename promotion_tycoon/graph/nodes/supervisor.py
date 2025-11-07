from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.prompts import SUPERVISOR_PROMPT
from promotion_tycoon.models import RoutingDecision, WorkflowState
from promotion_tycoon.storage import get_role, get_projects, get_report
from promotion_tycoon.tracing import log_trace, log_error


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def supervisor_node(state: WorkflowState):
    log_trace("🚦 Supervisor deciding",
              phase=state["phase"],
              preview=state["messages"][-1].content[:50] if state["messages"] else "",
              waiting_for=state.get("waiting_for"))
    role = get_role(state["packet_id"])
    projects = get_projects(state["packet_id"])
    report = get_report(state["packet_id"])

    waiting_for = state.get("waiting_for")
    last_msg = state["messages"][-1] if state["messages"] else None
    is_human_msg = isinstance(last_msg, HumanMessage)

    if waiting_for and not is_human_msg:
        return {"route": "wait_for_input", "intent": f"waiting_for_{waiting_for}"}

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
        decision = await structured_model.ainvoke([SystemMessage(content=prompt), *messages])
        log_trace("🤖 Routing Decision", route=decision.route, intent=decision.intent, reasoning=decision.reasoning[:100])
        return {"route": decision.route, "intent": decision.intent}
    except Exception as e:
        log_error("Supervisor Decision", e)
        return {"route": "guidance_agent", "intent": "error_recovery"}
