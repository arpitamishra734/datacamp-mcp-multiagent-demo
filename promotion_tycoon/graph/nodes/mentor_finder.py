import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.storage import get_role
from promotion_tycoon.tracing import log_trace, log_error
from promotion_tycoon.mcp_client import get_mcp_tools
from promotion_tycoon.models import WorkflowState


model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def mentor_finder_node(state: WorkflowState):
    log_trace("👥 Mentor Finder activated")
    role = get_role(state["packet_id"])
    if not role:
        return {"messages": [AIMessage(content="⚠️ Define your target role first.")]}

    mentors_found = []
    try:
        tools = await get_mcp_tools()
        search_tool = next((t for t in tools if "tavily" in t.name.lower() or "search" in t.name.lower()), None)
        if search_tool:
            variation_prompt = f"""Given the target role: {role.get('title','')}
Generate 3-4 LinkedIn title variations. Return a single OR-query like:
(VP Robotics OR "Vice President of Robotics" OR "Director Robotics Engineering" OR "Head of Robotics")"""
            title_variations = (await model.ainvoke([SystemMessage(content=variation_prompt)])).content.strip()
            query = f"site:linkedin.com/in/ {title_variations}"
            log_trace("🔎 Searching LinkedIn with variations", variations=title_variations[:120])
            res = await search_tool.ainvoke({"query": query})
            text = str(res) if not isinstance(res, str) else res

            urls = re.findall(r'https://www\\.linkedin\\.com/in/[^/\\s]+', text)
            profiles = []
            current = {}
            for line in text.splitlines():
                if 'Title:' in line:
                    if current: profiles.append(current)
                    current = {'title': line.split('Title:')[1].strip()}
                elif 'URL:' in line: current['url'] = line.split('URL:')[1].strip()
                elif 'Content:' in line: current['snippet'] = line.split('Content:')[1].strip()[:200]
            if current: profiles.append(current)
            if not profiles and urls:
                for u in urls[:5]:
                    profiles.append({'title': 'LinkedIn Professional', 'url': u, 'snippet': 'View profile for details'})
            mentors_found = profiles[:5]
            if mentors_found:
                out = ["## 👥 Similar Professionals on LinkedIn", f"*Found professionals in similar {role.get('title','')} roles:*\n"]
                for i, p in enumerate(mentors_found, 1):
                    out.append(f"### {i}. {p.get('title','Professional')}")
                    if p.get('snippet'): out.append(f"{p['snippet']}...")
                    if p.get('url'): out.append(f"**[View LinkedIn Profile]({p['url']})**\n")
                out += ["💡 **Tips:** Mention specifics, ask about their journey, request brief chat.", "",
                        "**Options:** 'add projects' • 'download' • 'done'", "*What would you like to do next?*"]
                return {"messages": [AIMessage(content="\n".join(out))],
                        "phase": "post_mentors", "waiting_for": "next_action", "mentors_found": mentors_found}
    except Exception as e:
        log_error("Mentor Finder", e)

    return {"messages": [AIMessage(content="❌ Could not find mentors at this time. Please try again later.")]}
