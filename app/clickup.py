import requests

import config

BASE_URL = "https://api.clickup.com/api/v2"


def _headers():
    return {"Authorization": config.CLICKUP_API_TOKEN}


def get_completed_tasks(week_start_ms: int, week_end_ms: int) -> list[dict]:
    """Fetch tasks completed within the given date range (epoch ms)."""
    url = f"{BASE_URL}/team/{config.CLICKUP_TEAM_ID}/task"
    params = {
        "statuses[]": ["complete", "closed"],
        "date_done_gt": str(week_start_ms),
        "date_done_lt": str(week_end_ms),
        "subtasks": "true",
        "include_closed": "true",
        "page": 0,
    }

    all_tasks = []
    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        tasks = data.get("tasks", [])
        if not tasks:
            break
        for t in tasks:
            all_tasks.append(
                {
                    "name": t.get("name"),
                    "status": t.get("status", {}).get("status"),
                    "list": t.get("list", {}).get("name"),
                    "space": t.get("space", {}).get("name") if t.get("space") else None,
                    "date_done": t.get("date_done"),
                    "url": t.get("url"),
                }
            )
        params["page"] += 1

    return all_tasks


def get_upcoming_tasks(next_week_start_ms: int, next_week_end_ms: int) -> list[dict]:
    """Fetch tasks that are recurring or due during the given date range (epoch ms)."""
    url = f"{BASE_URL}/team/{config.CLICKUP_TEAM_ID}/task"
    params = {
        "due_date_gt": str(next_week_start_ms),
        "due_date_lt": str(next_week_end_ms),
        "subtasks": "true",
        "include_closed": "false",
        "page": 0,
    }

    all_tasks = []
    seen_ids = set()
    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        tasks = data.get("tasks", [])
        if not tasks:
            break
        for t in tasks:
            tid = t.get("id")
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            all_tasks.append(
                {
                    "name": t.get("name"),
                    "status": t.get("status", {}).get("status"),
                    "list": t.get("list", {}).get("name"),
                    "space": t.get("space", {}).get("name") if t.get("space") else None,
                    "due_date": t.get("due_date"),
                    "recurring": bool(t.get("recurrence")),
                    "url": t.get("url"),
                }
            )
        params["page"] += 1

    return all_tasks
