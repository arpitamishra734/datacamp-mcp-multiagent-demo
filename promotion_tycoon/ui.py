import uuid
import gradio as gr
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


from promotion_tycoon.tracing import format_trace_for_ui, log_trace, log_error
from promotion_tycoon.storage import create_packet
from promotion_tycoon.formatting import (
    format_role_panel, format_projects_panel, format_report_panel,
    format_mentors_panel, generate_markdown_export
)
from promotion_tycoon.graph.assemble import app


def create_ui():
    with gr.Blocks(theme=gr.themes.Soft(), title="Promotion Advisor") as demo:
        packet_id_state = gr.State(value=lambda: create_packet("demo_user"))
        thread_id_state = gr.State(value=lambda: str(uuid.uuid4()))

        gr.Markdown("# 🚀 Promotion Advisor — Multi-Agent Workspace")
        gr.Markdown("*AI-powered promotion packet preparation with LangGraph + MongoDB*")
        gr.Markdown("---")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 🎯 Target Role")
                target_panel = gr.JSON(label="", value={})
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Projects")
                projects_panel = gr.JSON(label="", value=[])

        gr.Markdown("---")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Impact Report")
                report_panel = gr.Markdown("*No report generated yet*")
            with gr.Column(scale=1):
                gr.Markdown("### 👥 Similar Professionals")
                mentors_panel = gr.JSON(label="", value=[])
        
        gr.Markdown("---")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Execution Trace")
                with gr.Accordion("", open=False):
                    trace_html = gr.HTML(value=format_trace_for_ui())
                    refresh_trace_btn = gr.Button("Refresh Trace", size="sm")

            with gr.Column(scale=1):
                chatbot = gr.Chatbot(
                    height=400,
                    label="Chat",
                    value=[{"role": "assistant", "content":
                            "👋 Welcome! Tell me your target role to begin.\n\n"
                            "*Example: \"I want to become a Staff Software Engineer\"*"}],
                    type="messages"
                )
                msg = gr.Textbox(label="Your message",
                                placeholder="Describe your target role or paste project information...",
                                lines=3)
                with gr.Row():
                    send_btn = gr.Button("📤 Send", variant="primary", scale=2)
                    clear_btn = gr.Button("🔄 Clear Chat", scale=1)
                    download_btn = gr.Button("⬇️ Download Packet", scale=1)

        async def chat_handler(message: str, history: list, packet_id: str, thread_id: str):
            if not message.strip():
                return history, "", format_role_panel(packet_id), format_projects_panel(packet_id), format_report_panel(packet_id)
            log_trace("💬 User message received", preview=message[:50])
            history = history + [{"role": "user", "content": message}]
            result = None
            try:
                config = {"configurable": {"thread_id": thread_id}}
                # Try interrupted resume
                current_state = app.get_state(config)
                if current_state and current_state.next:
                    from langgraph.types import Command
                    log_trace("📥 Resuming from interrupt", next_nodes=current_state.next)
                    result = await app.ainvoke(Command(resume=HumanMessage(content=message)), config=config)
                else:
                    result = await app.ainvoke(
                        {"messages": [HumanMessage(content=message)],
                         "packet_id": packet_id, "phase": "setup", "projects": [],
                         "mentors_found": None, "user_id": "demo_user", "waiting_for": None},
                        config=config
                    )
                assistant_msg = result["messages"][-1].content
                history.append({"role": "assistant", "content": assistant_msg})
                log_trace("✅ Workflow completed")
            except Exception as e:
                log_error("Chat Handler", e)
                history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

            mentors = result.get("mentors_found", []) if result else []
            return (history, "",
                    format_role_panel(packet_id),
                    format_projects_panel(packet_id),
                    format_report_panel(packet_id),
                    format_mentors_panel(mentors))

        def clear_chat():
            new_packet_id = create_packet("demo_user")
            new_thread_id = str(uuid.uuid4())
            initial_history = [{"role": "assistant",
                                "content": "👋 Chat cleared! What role are you targeting for promotion?"}]
            log_trace("🔄 Chat cleared", new_packet_id=new_packet_id)
            return (new_packet_id, new_thread_id, initial_history, {}, [], "*No report generated yet*", [])

        def download_packet(packet_id: str):
            try:
                md = generate_markdown_export(packet_id)
                from pathlib import Path
                out_dir = Path("outputs"); out_dir.mkdir(exist_ok=True)
                out_path = out_dir / f"promotion_packet_{packet_id[:8]}.md"
                out_path.write_text(md)
                log_trace("📥 Packet downloaded", path=str(out_path))
                return gr.update(value=f"✅ Downloaded to: {out_path}")
            except Exception as e:
                return gr.update(value=f"❌ Download failed: {e}")

        def refresh_trace():
            return format_trace_for_ui()

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
        download_btn.click(download_packet, inputs=[packet_id_state], outputs=[msg])
        refresh_trace_btn.click(refresh_trace, outputs=[trace_html])

    return demo
