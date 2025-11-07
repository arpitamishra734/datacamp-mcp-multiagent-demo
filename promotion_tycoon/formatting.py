from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from promotion_tycoon.storage import get_role, get_projects, get_report
from promotion_tycoon.tracing import log_trace


def format_role_panel(packet_id: str) -> Dict:
    role = get_role(packet_id)
    if not role:
        return {"status": "No target role defined yet"}
    return {
        "title": role.get("title", ""),
        "level": role.get("level", ""),
        "industry_salary": role.get("industry_salary", "Not found"),
        "focus_areas": role.get("focus_areas", []),
        "responsibilities": role.get("responsibilities", [])[:3],
        "core_competencies": role.get("core_competencies", [])[:3],
    }

def format_projects_panel(packet_id: str) -> List[Dict]:
    projects = get_projects(packet_id)
    out = []
    for p in projects:
        metrics_fmt = []
        for m in p.get("metrics", []):
            s = f"{m.get('name')}: {m.get('value')}"
            if m.get('unit'): s += f" {m['unit']}"
            if m.get('improvement'): s += f" ({m['improvement']})"
            metrics_fmt.append(s)
        d = {
            "🎯 Name": p.get("name", "Unnamed"),
            "📅 Timeline": {"Duration": p.get("duration", "Not specified"), "Quarter": p.get("quarter", "Not specified")},
            "👤 Role": p.get("role", "Not specified"),
            "👥 Team Size": p.get("team_size", "Not specified"),
            "📝 Context": p.get("context", ""),
            "🎬 Actions": p.get("actions", []),
            "📊 Outcomes": p.get("outcomes", []),
            "📈 Metrics": metrics_fmt or ["No metrics captured"],
            "🛠️ Technologies": p.get("technologies", []),
            "👔 Stakeholders": p.get("stakeholders", []),
            "🎯 Focus Areas": p.get("related_focus_areas", []),
            "💪 Skills": p.get("skills_demonstrated", []),
            "🚧 Challenges": p.get("challenges_overcome", []),
            "📢 Visibility": p.get("visibility", "team"),
            "⭐ Impact": f"{p.get('impact_rating', 0)}/5",
        }
        if p.get("evidence_links"): d["🔗 Evidence"] = p["evidence_links"]
        out.append(d)
    return out

def format_report_panel(packet_id: str) -> str:
    report = get_report(packet_id)
    if not report: return "*No impact report generated yet*"
    md = f"### Executive Summary\n{report.get('executive_summary','')}\n\n"
    if report.get('strengths'):
        md += "### ✅ Strengths\n" + "\n".join(f"- {s}" for s in report['strengths']) + "\n\n"
    if report.get('gaps'):
        md += "### ⚠️ Gaps\n" + "\n".join(f"- {g}" for g in report['gaps']) + "\n\n"
    return md

def format_mentors_panel(mentors: List[Dict]) -> List[Dict]:
    out = []
    for m in mentors or []:
        out.append({
            "Title": m.get("title", "Professional"),
            "Summary": (m.get("snippet","")[:150] + "...") if m.get("snippet") else "No summary available",
            "LinkedIn": m.get("url", "No URL"),
        })
    return out

def generate_markdown_export(packet_id: str) -> str:
    role = get_role(packet_id); projects = get_projects(packet_id); report = get_report(packet_id)
    md = "# Promotion Packet\n\n"
    md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
    if role:
        md += f"## 🎯 Target Role: {role.get('title','')}\n\n**Level:** {role.get('level','')}\n\n"
        if role.get('focus_areas'):
            md += "**Focus Areas:**\n" + "\n".join(f"- {fa}" for fa in role["focus_areas"]) + "\n\n"
        if role.get('responsibilities'):
            md += "**Key Responsibilities:**\n" + "\n".join(f"- {r}" for r in role["responsibilities"]) + "\n\n"
    if projects:
        md += "## 📁 Projects\n\n"
        for i, p in enumerate(projects, 1):
            md += f"### {i}. {p.get('name','Unnamed Project')}\n"
            md += f"**Duration:** {p.get('duration','Not specified')}\n"
            md += f"**Role:** {p.get('role','Not specified')}\n\n"
            md += f"**Context:** {p.get('context','')}\n\n"
            if p.get('actions'): md += "**Actions:**\n" + "\n".join(f"- {a}" for a in p["actions"]) + "\n\n"
            if p.get('outcomes'): md += "**Outcomes:**\n" + "\n".join(f"- {o}" for o in p["outcomes"]) + "\n\n"
            if p.get('metrics'):
                md += "**Metrics:**\n"
                for m in p["metrics"]:
                    line = f"- {m.get('name')}: {m.get('value')} {m.get('unit','')}".rstrip()
                    if m.get('improvement'): line += f" ({m['improvement']})"
                    md += line + "\n"
                md += "\n"
    if report:
        md += "## 📊 Impact Report\n\n" + report.get('executive_summary','') + "\n\n"
        if report.get('strengths'):
            md += "### Strengths\n" + "\n".join(f"- {s}" for s in report["strengths"]) + "\n\n"
        if report.get('gaps'):
            md += "### Gaps to Address\n" + "\n".join(f"- {g}" for g in report["gaps"]) + "\n\n"
        if report.get('recommendations'):
            md += "### Recommendations\n" + "\n".join(f"- {r}" for r in report["recommendations"])
    return md
