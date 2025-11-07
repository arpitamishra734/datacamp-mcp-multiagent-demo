## Project layout (detailed)

```
promotion_tycoon/
  graph/
    nodes/
      guidance.py         # Guidance Agent — generic help/UX guardrails, prompts user for next step
      impact_analyzer.py  # Impact Analyzer — builds executive report; can enrich with Tavily MCP
      mentor_finder.py    # Mentor Finder — searches LinkedIn via Tavily; formats top profiles
      project_curator.py  # Project Curator — extracts structured projects (context/actions/metrics)
      supervisor.py       # Supervisor/Router — routes to the right agent based on state+intent
      target_builder.py   # Target Role Builder — parses role, level, focus areas, salary hints
    assemble.py           # Builds the LangGraph StateGraph, edges, and checkpointer-backed app
  config.py               # Loads .env, enforces Atlas-only (or DEMO_MODE), exposes config constants
  storage.py              # Atlas CRUD (roles/projects/reports) + LangGraph MongoDBSaver checkpointer
  prompts.py              # System prompts: SUPERVISOR / TARGET_BUILDER / PROJECT_CURATOR / IMPACT_ANALYZER
  tracing.py              # Pretty trace buffer + log helpers for the UI (INFO/ERROR entries)
  models.py               # Pydantic models (RoleDefinition, ProjectRecord, ImpactReport, etc.) + WorkflowState
  mcp_client.py           # Optional MCP client (Tavily) + tool discovery
  formatting.py           # Helpers to shape UI panels, markdown export, and table/detail views
  ui.py                   # Gradio UI wiring: state, handlers, panels, download/export, trace refresh
  main.py                 # Entrypoint (python -m promotion_tycoon.main)
Makefile                  # (optional) setup/run/lint/format/clean
.env.template             # Example environment variables; copy to .env and fill in secrets
requirements.txt          # Pinned dependencies for the app
```

### Deeper descriptions

- **graph/nodes/**
  - **supervisor.py (Supervisor/Router)**
    - **Purpose:** First stop for each user message; decides which agent to run next.
    - **Inputs:** Latest `HumanMessage`, current `phase`, DB presence of role/projects/report.
    - **Outputs:** `{route, intent}`; may short-circuit to wait states.
    - **Failure modes:** Falls back to `guidance` on exceptions.

  - **target_builder.py (Target Role Builder)**
    - **Purpose:** Extracts *title, level, focus areas, responsibilities, metrics, competencies*; may incorporate salary hints from research.
    - **Side effects:** `upsert_role()` to MongoDB; advances `phase` to `projects`; sets `waiting_for="projects"`.

  - **project_curator.py (Project Curator)**
    - **Purpose:** Turns free text into structured **ProjectRecord**(s) with context/actions/outcomes/metrics/tech.
    - **Side effects:** `insert_projects()` to MongoDB; prompts user to generate report or add more.

  - **impact_analyzer.py (Impact Analyzer)**
    - **Purpose:** Produces **ImpactReport** (exec summary, strengths, gaps, recommendations).
    - **Enhancements:** If MCP/Tavily present, parses salary ranges, sources, key requirements.
    - **Side effects:** `upsert_report()` to MongoDB; sets `phase="post_report"` and waits for next decision.

  - **mentor_finder.py (Mentor Finder)**
    - **Purpose:** Uses Tavily to find relevant LinkedIn profiles; formats top results for the UI.
    - **Side effects:** Stores `mentors_found` in state for panel display.

  - **guidance.py (Guidance Agent)**
    - **Purpose:** Friendly helper; nudges user to define role/add projects/generate report based on state.
    - **Use case:** Default when intent is unclear or after errors.

- **graph/assemble.py**
  - **Purpose:** Defines `StateGraph`, nodes, conditional edges, and compiles to `app` with the **MongoDBSaver** checkpointer.
  - **Special logic:** Handles LangGraph interrupts (`wait_for_input`) and post-node routing to `supervisor`.

- **config.py**
  - **Purpose:** Centralized config loader: reads `.env`, validates **Atlas** URI (or enables `DEMO_MODE`), passes keys (OpenAI, Tavily), and sets app/server options.
  - **Notes:** “Fail fast” if Atlas is required and missing.

- **storage.py**
  - **Purpose:** Thin MongoDB data layer: `create_packet`, `upsert_role`, `insert_projects`, `upsert_report`, and `get_*` reads.
  - **Also:** Instantiates **MongoDBSaver** for LangGraph checkpoints.

- **prompts.py**
  - **Purpose:** All system prompts in one place (supervisor/target_builder/project_curator/impact_analyzer).
  - **Tip:** Easier to iterate prompts without hunting through code.

- **tracing.py**
  - **Purpose:** Pretty, structured tracing (INFO/ERROR, timestamps); `format_trace_for_ui()` renders HTML for the Gradio panel.

- **models.py**
  - **Purpose:** Pydantic models for everything stored or exchanged (role/project/report) + `WorkflowState` (`TypedDict` with `messages: add_messages`).

- **mcp_client.py**
  - **Purpose:** Optional MCP client bootstrap; discovers/searches Tavily tools.
  - **Behavior:** If missing key, gracefully disables research.

- **formatting.py**
  - **Purpose:** UI formatting & export utilities: role/projects/report/mentors panels; markdown packet export.

- **ui.py**
  - **Purpose:** Gradio app definition, chat handler (including handling interrupts/resume), panel refreshers, download, trace refresh.

- **main.py**
  - **Purpose:** Small entrypoint that logs start, checks `OPENAI_API_KEY`, creates UI, and launches Gradio.

- **Makefile (optional)**
  - **Targets:** `setup`, `run`, `lint`, `format`, `clean`.

- **.env.template**
  - **Purpose:** Copy to `.env`; fill in `MONGODB_URI`, `OPENAI_API_KEY`, optional `TAVILY_API_KEY`.

- **requirements.txt**
  - **Purpose:** Pinned dependencies for reproducible installs.
