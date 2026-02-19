import json
import re

import anthropic
from flask import Flask, render_template, abort, request, jsonify

import config
from app.models import Report, get_session, init_db


def _md_to_html(text: str) -> str:
    """Convert markdown to HTML for display in the web UI."""
    lines = text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{_inline(stripped[2:])}</h3>")
        elif re.match(r"^[-*]\s", stripped) or re.match(r"^\d+\.\s", stripped):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = re.sub(r"^[-*]\s|^\d+\.\s", "", stripped)
            html_lines.append(f"<li>{_inline(content)}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def create_app():
    app = Flask(__name__)
    app.secret_key = config.FLASK_SECRET_KEY

    with app.app_context():
        init_db()

    def _sidebar_reports():
        session = get_session()
        reports = session.query(Report).order_by(Report.created_at.desc()).limit(20).all()
        session.close()
        return reports

    @app.route("/")
    def index():
        session = get_session()
        reports = session.query(Report).order_by(Report.created_at.desc()).all()
        session.close()

        latest_task_count = 0
        latest_upcoming_count = 0
        if reports:
            latest_task_count = len(json.loads(reports[0].tasks_json))
            latest_upcoming_count = len(json.loads(reports[0].upcoming_tasks_json))

        return render_template(
            "index.html",
            reports=reports,
            sidebar_reports=reports,
            latest_task_count=latest_task_count,
            latest_upcoming_count=latest_upcoming_count,
            nav_active="dashboard",
        )

    @app.route("/report/<int:report_id>")
    def report_detail(report_id):
        session = get_session()
        report = session.query(Report).get(report_id)
        session.close()
        if not report:
            abort(404)
        tasks = json.loads(report.tasks_json)
        emails = json.loads(report.emails_json)
        upcoming_tasks = json.loads(report.upcoming_tasks_json)

        summary_html = _md_to_html(report.summary_text)
        suggestions_html = _md_to_html(report.suggestions_text)

        return render_template(
            "report.html",
            report=report,
            tasks=tasks,
            emails=emails,
            upcoming_tasks=upcoming_tasks,
            summary_html=summary_html,
            suggestions_html=suggestions_html,
            sidebar_reports=_sidebar_reports(),
            report_active=True,
            active_id=report.id,
        )

    @app.route("/ask")
    def ask_page():
        return render_template(
            "ask.html",
            sidebar_reports=_sidebar_reports(),
            nav_active="ask",
        )

    @app.route("/api/ask", methods=["POST"])
    def ask():
        data = request.get_json()
        question = data.get("question", "").strip()
        report_id = data.get("report_id")

        if not question:
            return jsonify({"error": "No question provided"}), 400

        session = get_session()
        if report_id:
            reports = [session.query(Report).get(report_id)]
            reports = [r for r in reports if r]
        else:
            reports = session.query(Report).order_by(Report.created_at.desc()).limit(5).all()
        session.close()

        if not reports:
            return jsonify({"answer": "No reports found to reference."})

        context_parts = []
        for r in reports:
            tasks = json.loads(r.tasks_json)
            emails = json.loads(r.emails_json)
            upcoming = json.loads(r.upcoming_tasks_json)
            context_parts.append(
                f"--- Report: {r.week_start} to {r.week_end} ---\n"
                f"Summary:\n{r.summary_text}\n\n"
                f"Suggestions:\n{r.suggestions_text}\n\n"
                f"Completed Tasks ({len(tasks)}):\n"
                + "\n".join(f"  - {t['name']} ({t.get('list', 'N/A')})" for t in tasks)
                + f"\n\nUpcoming Tasks ({len(upcoming)}):\n"
                + "\n".join(
                    f"  - {t['name']} ({t.get('list', 'N/A')})"
                    + (" [recurring]" if t.get("recurring") else "")
                    for t in upcoming
                )
                + f"\n\nEmails ({len(emails)}):\n"
                + "\n".join(
                    f"  - {e.get('subject', '(no subject)')} from {e.get('from', 'unknown')}"
                    for e in emails[:20]
                )
            )

        context = "\n\n".join(context_parts)

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            system=(
                "You are an assistant that answers questions about weekly work reports. "
                "Be concise, specific, and reference actual task names, emails, or details. "
                "If the data doesn't contain the answer, say so honestly. "
                "Keep answers to 2-4 sentences unless more detail is needed."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Here are the recent weekly reports:\n\n{context}\n\n"
                    f"Question: {question}",
                }
            ],
        )

        return jsonify({"answer": message.content[0].text})

    return app


app = create_app()
