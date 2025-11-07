# Promotion Tycoon — Multi-Agent Promotion Advisor (LangGraph + MongoDB Atlas + Gradio)

> Build a **promotion packet** with AI: define a target role, add your projects, generate an impact report, and discover mentor profiles — all persisted in **MongoDB Atlas**, orchestrated with **LangGraph**, and wrapped in a clean **Gradio** UI. Optional **MCP (Tavily)** enriches analysis with industry research.

---

## What this project is about

A **developer-friendly demo** that shows a practical, end-to-end **agentic workflow** for career growth:

- **Target Role Builder** → parses your goal (e.g., *AI Engineer, Staff PM, Director of Data*) and sets expectations  
- **Project Curator** → extracts structured, evidence-backed project records from free text  
- **Impact Analyzer** → produces an executive-ready report (strengths, gaps, recommendations), optionally citing industry research  
- **Mentor Finder** → surfaces similar roles on LinkedIn (via Tavily MCP)

It demonstrates how to move **beyond stateless chat** into an app with **memory, structure, and repeatability**.

---

## What it’s showing (key concepts)

- **MongoDB Atlas** as the **system memory** and **LangGraph checkpointer**  
  (Atlas by default; optional *Demo Mode* uses pure in-memory)  
- **LangGraph** for **multi-agent routing**, **interrupt/resume**, and **checkpoints**  
- **Pydantic models** for typed, structured records (role, projects, report)  
- **Gradio** UI that’s simple, resilient, and demo-ready  
- **Optional MCP (Tavily)** to pull in industry insights/salary bands

---

## User workflow

1. **Start the app** → a chat prompt asks: *“What role are you targeting?”*  
2. **Define target role** → the agent parses role & level; sets focus areas & metrics.  
3. **Add projects** → paste one or more projects; the app extracts context/actions/outcomes/metrics.  
4. **Generate impact report** → strengths, gaps, concrete recommendations;  
   if Tavily is enabled, it includes **sources and salary ranges**.  
5. **Find mentors (optional)** → see relevant LinkedIn profiles to contact.  
6. **Export** → download a Markdown *Promotion Packet* for your brag doc or review cycles.

---

## Requirements & dependencies

**Runtime**
- Python **3.10+**
- `make` *(optional convenience)*

**Core Python deps** (pinned in `requirements.txt`)
- `gradio`, `pydantic`, `pymongo`, `python-dotenv`  
- `langchain-core`, `langchain-openai`, `langgraph`  
- *(optional)* `langchain-mcp-adapters` for Tavily MCP

**Accounts / keys**
- **MongoDB Atlas** SRV URI (`mongodb+srv://...`)  
- **OpenAI API key**  
- *(optional)* **Tavily API key** for industry research

---

## Project layout

```
promotion_tycoon/
  graph/
    nodes/                # individual agent nodes
    assemble.py           # builds StateGraph + conditional routing
  config.py               # env loading & Atlas-or-Demo policy
  storage.py              # Atlas CRUD + LangGraph checkpointer
  prompts.py              # all system prompts (single source of truth)
  tracing.py              # pretty audit log for the UI
  models.py               # Pydantic models + WorkflowState
  ui.py                   # Gradio UI wiring + handlers
  main.py                 # app entrypoint (python -m promotion_tycoon.main)
```

---

## Get started

1) **Clone & enter**
```bash
git clone <your-repo-url>
cd <repo>
```

2) **Create env file**
```bash
cp .env.template .env
# edit .env with:
# MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority&appName=Promotion-Tycoon
# OPENAI_API_KEY=sk-...
# (optional) TAVILY_API_KEY=...
```

3) **Install**
```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

4) **Run**
```bash
python -m promotion_tycoon.main
# open http://localhost:7860
```

> **Atlas-only by default.** To run a no-network demo, set `DEMO_MODE=true` in `.env` to use in-memory (no DB).

---

## Makefile (optional)

Minimal targets:
```bash
make setup     # venv + install deps + linters/formatters
make run       # start app
make lint      # ruff check
make format    # ruff --fix, isort, black
make clean     # remove caches & outputs
```

---

## Configuration (.env)

```dotenv
# REQUIRED (unless DEMO_MODE=true)
MONGODB_URI=mongodb+srv://...
DATABASE_NAME=promotion_advisor

# REQUIRED
OPENAI_API_KEY=sk-...

# OPTIONAL
TAVILY_API_KEY=
GRADIO_SERVER_NAME=0.0.0.0
GRADIO_SERVER_PORT=7860

# Demo mode: skip DB, use in-memory (for workshops/offline demos)
DEMO_MODE=false
```

- Fails fast if Atlas is missing/misconfigured (unless `DEMO_MODE=true`).  
- If Tavily is absent, industry research is skipped gracefully.

---

## Screenshots / demo

Add 1–2 screenshots or a short GIF showing:
- Initial prompt (target role)
- Projects populated
- Generated impact report
- (Optional) mentor panel

---

## Future work

- **File uploads** (resume/JD) → auto-parse into structured projects/role expectations  
- **Inline editing** for projects & metrics in the UI  
- **Export to PDF** and/or Google Docs template  
- **Team mode** for reviewers and comments  
- **Advanced mentor search** (filters by company/region/seniority)  
- **Model adapters** for other providers / local models  

**New items (planned):**
- **Vector & Hybrid Search with MongoDB Atlas**  
  - Store embeddings alongside operational data; use Atlas Vector Search + **hybrid (BM25 + vector)** queries to enrich role/mentor matching and project retrieval.  
- **Embeddings & Reranking with Voyage**  
  - Use **Voyage** embeddings for high-quality semantic representations and **reranking** to boost report quality and mentor results.  
- **Monitoring & Observability**  
  - Add traces/metrics for agents, LLM cost/latency, prompt success rates; dashboards for **app health**, **LLM usage**, and **quality signals** (e.g., Prometheus/Grafana, OpenTelemetry).

---

## Troubleshooting

- **`RuntimeError: MONGODB_URI is required`**  
  Create `.env` from `.env.template` and set an Atlas SRV URI, or use `DEMO_MODE=true`.
- **MCP/Tavily timeouts**  
  The app will fall back. Leave `TAVILY_API_KEY` blank to disable.
- **Remote demos**  
  Set `GRADIO_SERVER_NAME=0.0.0.0` and open port `7860` on your VM.

---

## Call to action — Explore the Gen-AI Showcase

If this demo sparked ideas, **check out the Gen-AI Showcase** for more hands-on examples of **agentic patterns**, **memory architectures**, and **MongoDB-backed AI apps**.  
👉 **[Gen-AI Showcase]([https://example.com/showcase](https://github.com/mongodb-developer/GenAI-Showcase))** 

---

### License

MIT (or your preferred license). Add a `LICENSE` file to clarify usage.

---

**Happy building!** If you ship something cool with this, open a PR to add it to the Showcase or share your story in Issues/Discussions.
