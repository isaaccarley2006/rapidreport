import json
import re
from datetime import datetime, timedelta, timezone

import anthropic

import config
from app.models import LinkedInPost, LinkedInStat, LinkedInWeek, get_session

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CONTENT_PILLARS = {
    "monday": {
        "name": "Market Insights",
        "audiences": ["Property Managers", "Landlords"],
        "template": "pain_point_data",
        "stat_categories": ["market_scale", "void_periods", "renters_rights_act"],
    },
    "tuesday": {
        "name": "Product Spotlight",
        "audiences": ["Property Managers", "Real Estate Investors"],
        "template": "product_spotlight",
        "stat_categories": ["referencing", "void_periods", "tenant_behaviour"],
    },
    "wednesday": {
        "name": "Educational Content",
        "audiences": ["Landlords", "Property Managers"],
        "template": "blog_repurpose",
        "stat_categories": ["renters_rights_act", "market_scale", "tenant_behaviour"],
    },
    "thursday": {
        "name": "Partnership & Community",
        "audiences": ["Industry Partners", "Property Managers"],
        "template": "partnership_announcement",
        "stat_categories": ["market_scale", "referencing"],
    },
    "friday": {
        "name": "Founder Story",
        "audiences": ["Entrepreneurs", "Property Managers"],
        "template": "founder_story",
        "stat_categories": ["market_scale", "referencing", "void_periods"],
    },
    "saturday": {
        "name": "Quick Tips",
        "audiences": ["Landlords", "New Property Managers"],
        "template": "quick_tip",
        "stat_categories": ["void_periods", "referencing", "tenant_behaviour"],
    },
    "sunday": {
        "name": "Recycle & Reflect",
        "audiences": ["Property Managers", "Landlords"],
        "template": "recycle",
        "stat_categories": [],
    },
}

POST_TEMPLATES = {
    "pain_point_data": (
        "Write a LinkedIn post that opens with a surprising industry statistic, "
        "describes the pain point it reveals for property managers/landlords, "
        "and positions RapidRent ID as the solution. Include a call-to-action."
    ),
    "product_spotlight": (
        "Write a LinkedIn post highlighting a specific RapidRent ID feature (instant tenant referencing, "
        "digital ID verification, or automated affordability checks). "
        "Explain the problem it solves, how it works in simple terms, "
        "and end with a customer-benefit statement and CTA."
    ),
    "blog_repurpose": (
        "Write a LinkedIn post that distills key takeaways from an educational topic "
        "relevant to UK property management and the private rented sector. "
        "Use a numbered list or bullet format. "
        "End with an engaging question to drive comments."
    ),
    "partnership_announcement": (
        "Write a LinkedIn post about industry collaboration, community involvement, "
        "or a partner spotlight in the UK PropTech/lettings space. "
        "Tone should be warm and community-focused. "
        "Tag a hypothetical partner and include a forward-looking statement."
    ),
    "founder_story": (
        "Write a LinkedIn post from the founder's perspective sharing a lesson learned, "
        "a behind-the-scenes moment, or a reflection on building RapidRent. "
        "Keep it personal, authentic, and end with a takeaway for the audience."
    ),
    "quick_tip": (
        "Write a short LinkedIn post with a single actionable tip for UK landlords or "
        "letting agents. Keep it under 150 words. Use a hook, the tip, and a CTA."
    ),
    "recycle": (
        "Rewrite and refresh the following post with updated framing, new hook, "
        "and current language. Keep the core message but make it feel new. "
        "ORIGINAL POST:\n{original_content}"
    ),
}

BRAND_RULES = """You are a LinkedIn content writer for RapidRent, a UK PropTech company that provides instant tenant referencing and digital ID verification for letting agents, landlords, and property managers.

BRAND VOICE RULES:
- Professional but approachable. Confident and knowledgeable about the UK private rental sector.
- Use short paragraphs (1-2 sentences each) for LinkedIn readability.
- Include relevant emojis sparingly (1-3 per post max).
- NEVER fabricate statistics. Only use the verified statistics provided below.
- When citing a stat, mention the source naturally (e.g., "According to [Source]...").
- NEVER use em dashes. Use commas, periods, or parentheses instead.
- Keep posts under 2500 characters (LinkedIn limit). Aim for 150-300 words.
- End with a clear call-to-action or engagement question.

POSITIONING:
- RapidRent ID reduces void periods by enabling instant tenant referencing (minutes, not days).
- Frame value from 3 sides: landlords save money, agents save time, tenants get a smoother experience.
- Reference the Renters' Rights Act where relevant as a driver for modernisation.

HASHTAGS:
- Include 3-5 relevant hashtags at the end of each post.
- Always include #RapidRent. Mix in: #PropTech #UKRental #LettingAgents #PropertyManagement #TenantReferencing #RentersRightsAct

OUTPUT FORMAT:
Return ONLY valid JSON with exactly this structure:
{"drafts": ["post1 content here", "post2 content here", "post3 content here"]}
Do not include any text before or after the JSON.
"""


# --- Stats CRUD ---

def get_all_stats(include_expired=False):
    db = get_session()
    query = db.query(LinkedInStat)
    if not include_expired:
        query = query.filter_by(is_expired=False)
    stats = query.order_by(LinkedInStat.created_at.desc()).all()
    db.close()
    return stats


def get_filtered_stats(categories):
    """Query LinkedInStat filtered by category list."""
    if not categories:
        return get_all_stats()
    db = get_session()
    stats = (
        db.query(LinkedInStat)
        .filter(LinkedInStat.is_expired == False, LinkedInStat.category.in_(categories))
        .order_by(LinkedInStat.created_at.desc())
        .all()
    )
    db.close()
    return stats


def create_stat(stat_text, source_name, source_url, date_verified, category):
    db = get_session()
    stat = LinkedInStat(
        stat_text=stat_text,
        source_name=source_name,
        source_url=source_url,
        date_verified=date_verified,
        category=category,
    )
    db.add(stat)
    db.commit()
    db.refresh(stat)
    db.close()
    return stat


def update_stat(stat_id, **kwargs):
    db = get_session()
    stat = db.query(LinkedInStat).get(stat_id)
    if not stat:
        db.close()
        return None
    for key, value in kwargs.items():
        if hasattr(stat, key):
            setattr(stat, key, value)
    db.commit()
    db.refresh(stat)
    db.close()
    return stat


def delete_stat(stat_id):
    db = get_session()
    stat = db.query(LinkedInStat).get(stat_id)
    if not stat:
        db.close()
        return False
    db.delete(stat)
    db.commit()
    db.close()
    return True


# --- Week Management ---

def get_current_week_start():
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def get_or_create_week(week_start):
    db = get_session()
    week = db.query(LinkedInWeek).filter_by(week_start=week_start).first()
    if not week:
        week = LinkedInWeek(week_start=week_start)
        db.add(week)
        db.commit()
        db.refresh(week)
    db.close()
    return week


def get_week_posts(week):
    db = get_session()
    posts = {}
    for day in DAY_ORDER:
        post_id = getattr(week, f"{day}_post_id")
        if post_id:
            post = db.query(LinkedInPost).get(post_id)
            posts[day] = post
        else:
            posts[day] = None
    db.close()
    return posts


def assign_post_to_day(post_id, week_start, day):
    db = get_session()
    week = db.query(LinkedInWeek).filter_by(week_start=week_start).first()
    if not week:
        week = LinkedInWeek(week_start=week_start)
        db.add(week)
        db.commit()
        db.refresh(week)
    setattr(week, f"{day}_post_id", post_id)
    db.commit()
    db.close()


def mark_recyclable(post_id):
    db = get_session()
    post = db.query(LinkedInPost).get(post_id)
    if post:
        post.is_recyclable = True
        db.commit()
    db.close()


def get_recyclable_posts():
    db = get_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    posts = (
        db.query(LinkedInPost)
        .filter(
            LinkedInPost.is_recyclable == True,
            LinkedInPost.recycle_count < 2,
            LinkedInPost.created_at <= cutoff,
        )
        .all()
    )
    db.close()
    return posts


# --- Generation ---

def _format_stats_for_prompt(stats):
    if not stats:
        return "No verified statistics available. Do not fabricate any stats."
    lines = []
    for s in stats:
        lines.append(f'- "{s.stat_text}" (Source: {s.source_name}, verified: {s.date_verified})')
    return "\n".join(lines)


def _get_news_context():
    """Fetch last 3 days of NewsDigest summaries for generation context."""
    try:
        from app.news_scraper import get_recent_digests
        digests = get_recent_digests(days=3)
        if not digests:
            return ""
        parts = []
        for d in digests:
            parts.append(f"[{d.date}] {d.summary or 'No summary'}")
            if d.post_angles_json:
                try:
                    angles = json.loads(d.post_angles_json)
                    if angles:
                        parts.append("Post angles: " + "; ".join(angles[:3]))
                except (json.JSONDecodeError, TypeError):
                    pass
        return "\n".join(parts)
    except Exception:
        return ""


def _build_system_prompt(pillar, audience, stats, news_context=""):
    pillar_info = None
    for day, info in CONTENT_PILLARS.items():
        if info["name"] == pillar:
            pillar_info = info
            break

    template_key = pillar_info["template"] if pillar_info else "pain_point_data"
    template_text = POST_TEMPLATES.get(template_key, POST_TEMPLATES["pain_point_data"])

    stats_text = _format_stats_for_prompt(stats)

    prompt = (
        f"{BRAND_RULES}\n"
        f"TARGET AUDIENCE: {audience}\n"
        f"CONTENT PILLAR: {pillar}\n"
        f"POST TEMPLATE:\n{template_text}\n\n"
        f"VERIFIED STATISTICS:\n{stats_text}\n"
    )

    if news_context:
        prompt += (
            f"\nRECENT INDUSTRY NEWS (use for timely hooks and context, but do NOT fabricate stats from these):\n"
            f"{news_context}\n"
        )

    return prompt


def _parse_drafts(text):
    try:
        data = json.loads(text)
        return data.get("drafts", [])
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("drafts", [])
            except json.JSONDecodeError:
                pass
    return [text]


def generate_post_drafts(pillar, audience, context=""):
    # Get stats filtered by pillar categories
    pillar_info = None
    for day, info in CONTENT_PILLARS.items():
        if info["name"] == pillar:
            pillar_info = info
            break

    categories = pillar_info.get("stat_categories", []) if pillar_info else []
    stats = get_filtered_stats(categories) if categories else get_all_stats()

    news_context = _get_news_context()
    system = _build_system_prompt(pillar, audience, stats, news_context)

    user_msg = f"Generate 3 LinkedIn post drafts for the {pillar} pillar targeting {audience}."
    if context:
        user_msg += f"\n\nAdditional context: {context}"

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    return _parse_drafts(message.content[0].text)


def generate_recycle_post(original_post_id):
    db = get_session()
    original = db.query(LinkedInPost).get(original_post_id)
    db.close()
    if not original:
        return []

    stats = get_all_stats()
    template = POST_TEMPLATES["recycle"].format(original_content=original.content)
    stats_text = _format_stats_for_prompt(stats)
    news_context = _get_news_context()

    system = (
        f"{BRAND_RULES}\n"
        f"TARGET AUDIENCE: {original.audience}\n"
        f"CONTENT PILLAR: Recycle & Reflect\n"
        f"POST TEMPLATE:\n{template}\n\n"
        f"VERIFIED STATISTICS:\n{stats_text}\n"
    )

    if news_context:
        system += f"\nRECENT INDUSTRY NEWS:\n{news_context}\n"

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": "Generate 3 refreshed versions of the original post."}],
    )

    return _parse_drafts(message.content[0].text)


def generate_week_batch(week_start):
    db = get_session()
    week = db.query(LinkedInWeek).filter_by(week_start=week_start).first()
    if not week:
        week = LinkedInWeek(week_start=week_start)
        db.add(week)
        db.commit()
        db.refresh(week)

    for day in DAY_ORDER:
        existing_post_id = getattr(week, f"{day}_post_id")
        if existing_post_id:
            continue

        pillar_info = CONTENT_PILLARS[day]
        pillar_name = pillar_info["name"]
        audience = pillar_info["audiences"][0]

        # Sunday: try recycling first
        if day == "sunday":
            recyclable = get_recyclable_posts()
            if recyclable:
                original = recyclable[0]
                drafts = generate_recycle_post(original.id)
                if drafts:
                    post = LinkedInPost(
                        pillar=pillar_name,
                        audience=audience,
                        template_type="recycle",
                        content=drafts[0],
                        parent_post_id=original.id,
                    )
                    db.add(post)
                    db.commit()
                    db.refresh(post)
                    setattr(week, f"{day}_post_id", post.id)
                    original_post = db.query(LinkedInPost).get(original.id)
                    if original_post:
                        original_post.recycle_count += 1
                    db.commit()
                    continue

        drafts = generate_post_drafts(pillar_name, audience)
        if drafts:
            post = LinkedInPost(
                pillar=pillar_name,
                audience=audience,
                template_type=pillar_info["template"],
                content=drafts[0],
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            setattr(week, f"{day}_post_id", post.id)
            db.commit()

    db.refresh(week)
    db.close()
    return week
