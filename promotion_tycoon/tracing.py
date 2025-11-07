import json
from datetime import datetime, timezone

TRACE_BUFFER = []

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

def log_trace(msg: str, **kv):
    entry = {"timestamp": _ts(), "level": "INFO", "message": msg, "ctx": kv}
    TRACE_BUFFER.append(entry)
    print(f"[{entry['timestamp']}] 🟢 {msg} {json.dumps(kv) if kv else ''}")

def log_error(label: str, exc: Exception, **kv):
    entry = {
        "timestamp": _ts(),
        "level": "ERROR",
        "label": label,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "ctx": kv,
    }
    TRACE_BUFFER.append(entry)
    print(f"[{entry['timestamp']}] 🔴 {label} ERROR: {entry['error_type']} {entry['error']}")

def format_trace_for_ui() -> str:
    html = [
        """<div style="font-family:'Fira Code',monospace;background:#0f1117;
        color:#f1f1f1;padding:10px 12px;border-radius:10px;line-height:1.4em;
        font-size:13px;overflow-y:auto;max-height:520px;">"""
    ]
    for e in TRACE_BUFFER[-400:]:
        ts = e.get("timestamp", "")
        lvl = e.get("level", "INFO")
        msg = e.get("message", "")
        ctx = e.get("ctx", {})
        color = "#ff6b6b" if lvl == "ERROR" else "#8be9fd"
        icon = "🔴" if lvl == "ERROR" else "🟢"
        html.append(f"""
            <div style="margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #2a2d36;">
                <span style="color:#888;">[{ts}]</span>
                <span style="color:{color};">{icon} {msg}</span>
        """)
        if ctx:
            pretty_ctx = json.dumps(ctx, indent=2).replace(" ", "&nbsp;").replace("\n", "<br>")
            html.append(f"<div style='margin-top:4px;color:#aaa;font-size:12px;'><pre>{pretty_ctx}</pre></div>")
        html.append("</div>")
    html.append("</div>")
    return "".join(html)
