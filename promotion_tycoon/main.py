from promotion_tycoon.tracing import log_trace
from promotion_tycoon.config import OPENAI_API_KEY
from promotion_tycoon.ui import create_ui

def main():
    log_trace("🚀 Starting Promotion Advisor")
    if not OPENAI_API_KEY:
        print("⚠️ WARNING: OPENAI_API_KEY not set!")
    demo = create_ui()
    demo.launch(share=False, server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()
