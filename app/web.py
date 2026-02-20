import json
import os
import re

import anthropic
from flask import Flask, render_template, abort, request, jsonify

import config
from app.models import ChatMessage, LinkedInPost, LinkedInWeek, NewsDigest, Report, get_session, init_db, seed_stats
from app.linkedin import (
    CONTENT_PILLARS,
    DAY_ORDER,
    assign_post_to_day,
    create_stat,
    delete_stat,
    generate_post_drafts,
    generate_recycle_post,
    generate_week_batch,
    get_all_stats,
    get_current_week_start,
    get_or_create_week,
    get_recyclable_posts,
    get_week_posts,
    mark_recyclable,
    update_stat,
)
from app.news_scraper import get_recent_digests, run_daily_digest


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
        seed_stats()

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
        session_id = data.get("session_id", "default")

        if not question:
            return jsonify({"error": "No question provided"}), 400

        db = get_session()

        # Get report context
        if report_id:
            reports = [db.query(Report).get(report_id)]
            reports = [r for r in reports if r]
        else:
            reports = db.query(Report).order_by(Report.created_at.desc()).limit(5).all()

        if not reports:
            db.close()
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

        # Load conversation history for this session
        history = (
            db.query(ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(20)
            .all()
        )

        # Build messages: first message includes report context, then history
        messages = []
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": question})

        # Save user message
        db.add(ChatMessage(session_id=session_id, role="user", content=question))
        db.commit()

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            system=(
                "You are an assistant that answers questions about weekly work reports. "
                "Be concise, specific, and reference actual task names, emails, or details. "
                "If the data doesn't contain the answer, say so honestly. "
                "Keep answers to 2-4 sentences unless more detail is needed.\n\n"
                f"Here are the recent weekly reports:\n\n{context}"
            ),
            messages=messages,
        )

        answer = message.content[0].text

        # Save assistant response
        db.add(ChatMessage(session_id=session_id, role="assistant", content=answer))
        db.commit()
        db.close()

        return jsonify({"answer": answer, "session_id": session_id})

    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        secret = request.headers.get("Authorization", "")
        if secret != f"Bearer {config.FLASK_SECRET_KEY}":
            return jsonify({"error": "Unauthorized"}), 401

        from app.report import generate_weekly_report
        report = generate_weekly_report()
        return jsonify({"status": "ok", "report_id": report.id})

    # --- LinkedIn Routes ---

    @app.route("/linkedin")
    def linkedin_page():
        week_start = request.args.get("week", get_current_week_start())
        week = get_or_create_week(week_start)
        posts = get_week_posts(week)
        stats = get_all_stats()
        news_digests = get_recent_digests(days=7)
        return render_template(
            "linkedin.html",
            week=week,
            week_start=week_start,
            posts=posts,
            stats=stats,
            pillars=CONTENT_PILLARS,
            day_order=DAY_ORDER,
            news_digests=news_digests,
            sidebar_reports=_sidebar_reports(),
            nav_active="linkedin",
        )

    @app.route("/api/linkedin/generate", methods=["POST"])
    def linkedin_generate():
        data = request.get_json()
        pillar = data.get("pillar", "")
        audience = data.get("audience", "")
        if not pillar or not audience:
            return jsonify({"error": "pillar and audience required"}), 400
        drafts = generate_post_drafts(pillar, audience)
        # Return all 3 drafts to client — don't auto-save, let user pick
        return jsonify({"drafts": drafts})

    @app.route("/api/linkedin/post", methods=["POST"])
    def linkedin_save_post():
        """Save a selected draft as a new LinkedInPost."""
        data = request.get_json()
        content = data.get("content", "")
        pillar = data.get("pillar", "")
        audience = data.get("audience", "")
        template_type = data.get("template_type", "generated")
        if not content or not pillar:
            return jsonify({"error": "content and pillar required"}), 400
        db = get_session()
        post = LinkedInPost(
            pillar=pillar,
            audience=audience,
            template_type=template_type,
            content=content,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id
        db.close()
        return jsonify({"status": "ok", "post_id": post_id})

    @app.route("/api/linkedin/generate-week", methods=["POST"])
    def linkedin_generate_week():
        data = request.get_json()
        week_start = data.get("week_start", get_current_week_start())
        week = generate_week_batch(week_start)
        return jsonify({"status": "ok", "week_id": week.id})

    @app.route("/api/linkedin/post/<int:post_id>/approve", methods=["POST"])
    def linkedin_approve(post_id):
        db = get_session()
        post = db.query(LinkedInPost).get(post_id)
        if not post:
            db.close()
            return jsonify({"error": "Post not found"}), 404
        post.status = "approved"
        db.commit()
        db.close()
        return jsonify({"status": "ok"})

    @app.route("/api/linkedin/post/<int:post_id>/reject", methods=["POST"])
    def linkedin_reject(post_id):
        db = get_session()
        post = db.query(LinkedInPost).get(post_id)
        if not post:
            db.close()
            return jsonify({"error": "Post not found"}), 404
        # Clear week FK references
        weeks = db.query(LinkedInWeek).all()
        for week in weeks:
            for day in DAY_ORDER:
                if getattr(week, f"{day}_post_id") == post_id:
                    setattr(week, f"{day}_post_id", None)
        db.delete(post)
        db.commit()
        db.close()
        return jsonify({"status": "ok"})

    @app.route("/api/linkedin/post/<int:post_id>/regenerate", methods=["POST"])
    def linkedin_regenerate(post_id):
        db = get_session()
        post = db.query(LinkedInPost).get(post_id)
        db.close()
        if not post:
            return jsonify({"error": "Post not found"}), 404
        drafts = generate_post_drafts(post.pillar, post.audience)
        return jsonify({"drafts": drafts, "post_id": post_id})

    @app.route("/api/linkedin/post/<int:post_id>", methods=["PUT"])
    def linkedin_update_post(post_id):
        db = get_session()
        post = db.query(LinkedInPost).get(post_id)
        if not post:
            db.close()
            return jsonify({"error": "Post not found"}), 404
        data = request.get_json()
        for field in ["content", "status", "scheduled_date", "scheduled_time", "performance_notes"]:
            if field in data:
                setattr(post, field, data[field])
        db.commit()
        db.close()
        return jsonify({"status": "ok"})

    @app.route("/api/linkedin/post/<int:post_id>/recycle", methods=["POST"])
    def linkedin_recycle(post_id):
        mark_recyclable(post_id)
        return jsonify({"status": "ok"})

    @app.route("/api/linkedin/post/<int:post_id>/assign", methods=["POST"])
    def linkedin_assign(post_id):
        data = request.get_json()
        week_start = data.get("week_start")
        day = data.get("day")
        if not week_start or not day or day not in DAY_ORDER:
            return jsonify({"error": "week_start and valid day required"}), 400
        assign_post_to_day(post_id, week_start, day)
        return jsonify({"status": "ok"})

    # --- Stats Routes ---

    @app.route("/api/linkedin/stats", methods=["GET"])
    def linkedin_stats_list():
        include_expired = request.args.get("include_expired", "0") == "1"
        stats = get_all_stats(include_expired=include_expired)
        return jsonify([{
            "id": s.id,
            "stat_text": s.stat_text,
            "source_name": s.source_name,
            "source_url": s.source_url,
            "date_verified": s.date_verified,
            "category": s.category,
            "is_expired": s.is_expired,
        } for s in stats])

    @app.route("/api/linkedin/stats", methods=["POST"])
    def linkedin_stats_create():
        data = request.get_json()
        stat = create_stat(
            stat_text=data.get("stat_text", ""),
            source_name=data.get("source_name", ""),
            source_url=data.get("source_url"),
            date_verified=data.get("date_verified", ""),
            category=data.get("category", ""),
        )
        return jsonify({"status": "ok", "id": stat.id})

    @app.route("/api/linkedin/stats/<int:stat_id>", methods=["PUT"])
    def linkedin_stats_update(stat_id):
        data = request.get_json()
        stat = update_stat(stat_id, **data)
        if not stat:
            return jsonify({"error": "Stat not found"}), 404
        return jsonify({"status": "ok"})

    @app.route("/api/linkedin/stats/<int:stat_id>", methods=["DELETE"])
    def linkedin_stats_delete(stat_id):
        if delete_stat(stat_id):
            return jsonify({"status": "ok"})
        return jsonify({"error": "Stat not found"}), 404

    # --- News Routes ---

    @app.route("/api/linkedin/news", methods=["GET"])
    def linkedin_news_list():
        days = int(request.args.get("days", 7))
        digests = get_recent_digests(days=days)
        return jsonify([{
            "id": d.id,
            "date": d.date.isoformat(),
            "summary": d.summary,
            "key_stats": json.loads(d.key_stats_json) if d.key_stats_json else [],
            "post_angles": json.loads(d.post_angles_json) if d.post_angles_json else [],
            "article_count": d.article_count,
            "articles": json.loads(d.raw_articles_json) if d.raw_articles_json else [],
        } for d in digests])

    @app.route("/api/linkedin/news/refresh", methods=["POST"])
    def linkedin_news_refresh():
        try:
            digest = run_daily_digest()
            return jsonify({
                "status": "ok",
                "date": digest.date.isoformat(),
                "article_count": digest.article_count,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/linkedin/news/add-stat", methods=["POST"])
    def linkedin_news_add_stat():
        """Add an extracted stat from news digest to the stats bank."""
        data = request.get_json()
        stat = create_stat(
            stat_text=data.get("stat_text", ""),
            source_name=data.get("source_name", ""),
            source_url=data.get("source_url"),
            date_verified=data.get("date_verified", ""),
            category=data.get("category", "market_scale"),
        )
        return jsonify({"status": "ok", "id": stat.id})

    # Set up cron jobs on Railway
    if os.getenv("RAILWAY_ENVIRONMENT"):
        from apscheduler.schedulers.background import BackgroundScheduler

        def _scheduled_generate():
            with app.app_context():
                from app.report import generate_weekly_report
                try:
                    report = generate_weekly_report()
                    print(f"  [cron] Weekly report generated (id={report.id})")
                except Exception as e:
                    print(f"  [cron] Report generation failed: {e}")

        def _scheduled_news_digest():
            with app.app_context():
                try:
                    digest = run_daily_digest()
                    print(f"  [cron] News digest generated for {digest.date} ({digest.article_count} articles)")
                except Exception as e:
                    print(f"  [cron] News digest failed: {e}")

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_generate, "cron", day_of_week="fri", hour=16, minute=0)
        scheduler.add_job(_scheduled_news_digest, "cron", hour=6, minute=0)
        scheduler.start()
        print("  [cron] Scheduled weekly report for Fridays at 16:00 UTC")
        print("  [cron] Scheduled daily news digest at 06:00 UTC")

    return app


app = create_app()
