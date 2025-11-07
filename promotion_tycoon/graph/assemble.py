from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.models import WorkflowState
from promotion_tycoon.storage import checkpointer
from promotion_tycoon.tracing import log_trace

from promotion_tycoon.graph.nodes.supervisor import supervisor_node
from promotion_tycoon.graph.nodes.target_builder import target_builder_node
from promotion_tycoon.graph.nodes.project_curator import project_curator_node
from promotion_tycoon.graph.nodes.impact_analyzer import impact_analyzer_node
from promotion_tycoon.graph.nodes.mentor_finder import mentor_finder_node
from promotion_tycoon.graph.nodes.guidance import guidance_agent_node




__all__ = ["app", "END"]

workflow = StateGraph(WorkflowState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("target_builder", target_builder_node)
workflow.add_node("project_curator", project_curator_node)
workflow.add_node("impact_analyzer", impact_analyzer_node)
workflow.add_node("mentor_finder", mentor_finder_node)
workflow.add_node("guidance_agent", guidance_agent_node)

workflow.set_entry_point("supervisor")

def route_supervisor(state: WorkflowState) -> str:
    route = state.get("route", "guidance_agent")
    if route == "end": return END
    if route == "iteration": return "project_curator"
    if route == "wait_for_input": return END
    return route

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
        END: END,
    }
)

# After-nodes routing
workflow.add_edge("target_builder", "supervisor")
workflow.add_edge("project_curator", "supervisor")
workflow.add_edge("impact_analyzer", "supervisor")
workflow.add_edge("mentor_finder", "supervisor")
workflow.add_edge("guidance_agent", "supervisor")

app = workflow.compile(checkpointer=checkpointer)
log_trace("✅ LangGraph workflow compiled")
