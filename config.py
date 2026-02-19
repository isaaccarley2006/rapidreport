import os
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_TOKEN = os.environ["CLICKUP_API_TOKEN"]
CLICKUP_TEAM_ID = os.environ["CLICKUP_TEAM_ID"]

MS_CLIENT_ID = os.environ["MS_CLIENT_ID"]
MS_TENANT_ID = os.environ["MS_TENANT_ID"]

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

REPORT_RECIPIENT_EMAIL = os.environ["REPORT_RECIPIENT_EMAIL"]
REPORT_SENDER_NAME = os.getenv("REPORT_SENDER_NAME", "RapidReport Bot")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "data", "reports.db"),
)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
