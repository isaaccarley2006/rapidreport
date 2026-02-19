import json
from datetime import datetime, timedelta, timezone

from app.clickup import get_completed_tasks, get_upcoming_tasks
from app.models import Report, get_session, init_db
from app.outlook import get_emails, send_email
from app.summarizer import generate_summary

import config


def _week_range() -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Friday 23:59) for the current week."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    friday = monday + timedelta(days=4, hours=23, minutes=59, seconds=59)
    return monday, friday


def generate_weekly_report():
    """Gather data, summarize with Claude, and store in the database."""
    init_db()
    week_start, week_end = _week_range()

    print(f"Generating report for {week_start.date()} to {week_end.date()}")

    # Fetch data
    start_ms = int(week_start.timestamp() * 1000)
    end_ms = int(week_end.timestamp() * 1000)
    tasks = get_completed_tasks(start_ms, end_ms)
    print(f"  Found {len(tasks)} completed tasks")

    # Fetch upcoming tasks (next week: following Monday to Friday)
    next_monday = week_end + timedelta(days=3)  # Friday -> Monday
    next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    next_friday = next_monday + timedelta(days=4, hours=23, minutes=59, seconds=59)
    next_start_ms = int(next_monday.timestamp() * 1000)
    next_end_ms = int(next_friday.timestamp() * 1000)
    upcoming_tasks = get_upcoming_tasks(next_start_ms, next_end_ms)
    print(f"  Found {len(upcoming_tasks)} upcoming tasks for next week")

    emails = get_emails(week_start.isoformat(), week_end.isoformat())
    print(f"  Found {len(emails)} emails")

    # Summarize
    summary_text, suggestions_text = generate_summary(tasks, emails, upcoming_tasks)
    print("  Summary generated")

    # Store
    session = get_session()
    report = Report(
        week_start=str(week_start.date()),
        week_end=str(week_end.date()),
        tasks_json=json.dumps(tasks),
        emails_json=json.dumps(emails),
        upcoming_tasks_json=json.dumps(upcoming_tasks),
        summary_text=summary_text,
        suggestions_text=suggestions_text,
    )
    session.add(report)
    session.commit()
    print(f"  Report saved (id={report.id})")
    session.close()
    return report


def send_weekly_report():
    """Load the latest report and send it as an HTML email."""
    init_db()
    session = get_session()
    report = session.query(Report).order_by(Report.created_at.desc()).first()
    session.close()

    if not report:
        print("No report found to send.")
        return

    html = _format_report_html(report)
    subject = f"RapidReport: {report.week_start} to {report.week_end}"

    send_email(config.REPORT_RECIPIENT_EMAIL, subject, html)
    print(f"Report sent to {config.REPORT_RECIPIENT_EMAIL}")


def _md_to_html(text: str) -> str:
    """Convert simple markdown to inline-styled HTML for email clients."""
    import re

    lines = text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue

        # Headers
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<h3 style="color:#2c3e50;font-size:16px;margin:16px 0 8px;">'
                f"{_inline_md(stripped[4:])}</h3>"
            )
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<h2 style="color:#2c3e50;font-size:18px;margin:20px 0 10px;'
                f'border-bottom:1px solid #eee;padding-bottom:6px;">'
                f"{_inline_md(stripped[3:])}</h2>"
            )
        elif stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(
                f'<h1 style="color:#2c3e50;font-size:22px;margin:20px 0 10px;">'
                f"{_inline_md(stripped[2:])}</h1>"
            )
        # List items (- or 1.)
        elif re.match(r"^[-*]\s", stripped) or re.match(r"^\d+\.\s", stripped):
            if not in_list:
                html_lines.append('<ul style="padding-left:20px;margin:8px 0;">')
                in_list = True
            content = re.sub(r"^[-*]\s|^\d+\.\s", "", stripped)
            html_lines.append(
                f'<li style="margin-bottom:6px;line-height:1.5;">{_inline_md(content)}</li>'
            )
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<p style="margin:8px 0;line-height:1.5;">{_inline_md(stripped)}</p>')

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, links) to HTML."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:#4A90D9">\1</a>', text)
    return text


def _format_report_html(report: Report) -> str:
    """Convert a report into a styled HTML email body."""
    tasks = json.loads(report.tasks_json)
    upcoming = json.loads(report.upcoming_tasks_json)
    task_list = "".join(
        f"<li style='margin-bottom:4px;'>{t['name']} "
        f"<span style='color:#888;font-size:13px;'>({t.get('list', 'N/A')})</span></li>"
        for t in tasks
    )
    recurring_tag = ' <span style="background:#fff3e0;color:#e65100;font-size:11px;padding:1px 6px;border-radius:8px;">recurring</span>'
    upcoming_list = "".join(
        f"<li style='margin-bottom:4px;'>{t['name']} "
        f"<span style='color:#888;font-size:13px;'>({t.get('list', 'N/A')})</span>"
        f"{recurring_tag if t.get('recurring') else ''}</li>"
        for t in upcoming
    )

    summary_html = _md_to_html(report.summary_text)
    suggestions_html = _md_to_html(report.suggestions_text)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:20px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#333;font-size:14px;">

    <tr><td style="background:#4A90D9;padding:24px 32px;">
        <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">
            RapidReport
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">
            {report.week_start} to {report.week_end}
        </p>
    </td></tr>

    <tr><td style="padding:24px 32px;">
        {summary_html}
    </td></tr>

    <tr><td style="padding:0 32px 24px;">
        {suggestions_html}
    </td></tr>

    <tr><td style="padding:0 32px 24px;">
        <h2 style="color:#2c3e50;font-size:18px;margin:0 0 10px;border-bottom:1px solid #eee;padding-bottom:6px;">
            Completed Tasks ({len(tasks)})
        </h2>
        <ul style="padding-left:20px;margin:8px 0;">
            {task_list if tasks else '<li style="color:#888;">None this week</li>'}
        </ul>
    </td></tr>

    <tr><td style="padding:0 32px 24px;">
        <h2 style="color:#2c3e50;font-size:18px;margin:0 0 10px;border-bottom:1px solid #eee;padding-bottom:6px;">
            Upcoming Tasks ({len(upcoming)})
        </h2>
        <ul style="padding-left:20px;margin:8px 0;">
            {upcoming_list if upcoming else '<li style="color:#888;">None scheduled</li>'}
        </ul>
    </td></tr>

    <tr><td style="padding:16px 32px;border-top:1px solid #eee;background:#fafafa;">
        <p style="margin:0;color:#999;font-size:12px;">
            Generated on {report.created_at.strftime('%B %d, %Y at %H:%M UTC') if report.created_at else 'N/A'}
        </p>
    </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
