import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN", "")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID", "")

MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

REPORT_RECIPIENT_EMAIL = os.getenv("REPORT_RECIPIENT_EMAIL", "")
REPORT_SENDER_NAME = os.getenv("REPORT_SENDER_NAME", "RapidReport Bot")

# Use /data on Railway (persistent volume), local data/ dir otherwise
_default_db_dir = "/data" if os.getenv("RAILWAY_ENVIRONMENT") else os.path.join(os.path.dirname(__file__), "data")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(_default_db_dir, "reports.db"),
)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "sofiasauraborrego")
