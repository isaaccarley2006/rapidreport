# RapidReport

Automated weekly report that gathers completed ClickUp tasks and Outlook emails, generates a summary using Claude, stores reports in a database, and sends them via email.

## Setup

```bash
cd ~/Projects/weekly-report
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials (see below)
```

## Credential Setup

### ClickUp API Token
1. Go to **ClickUp Settings > Apps** (or https://app.clickup.com/settings/apps)
2. Click **Generate** under Personal API Token
3. Copy the token into `CLICKUP_API_TOKEN` in `.env`
4. Find your Team ID in the URL when viewing your workspace (e.g., `https://app.clickup.com/12345678/...` → `12345678`)
5. Set `CLICKUP_TEAM_ID` in `.env`

### Microsoft Graph (Outlook)
1. Go to [Azure Portal > App Registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **New registration**
   - Name: "RapidReport"
   - Supported account types: Single tenant
   - Redirect URI: `http://localhost` (Web)
3. Note the **Application (client) ID** → `MS_CLIENT_ID`
4. Note the **Directory (tenant) ID** → `MS_TENANT_ID`
5. Go to **API Permissions > Add a permission > Microsoft Graph > Delegated**
6. Add: `Mail.Read`, `Mail.Send`
7. Click **Grant admin consent** (or have an admin do it)
8. On first run, you'll see a device code prompt — follow the instructions to authenticate in your browser. The token is cached for subsequent runs.

### Anthropic API Key
1. Go to https://console.anthropic.com/settings/keys
2. Create a new key
3. Set `ANTHROPIC_API_KEY` in `.env`

## Usage

### Generate a report (manually or via cron)
```bash
python generate_report.py
```

### Send the latest report via email
```bash
python send_report.py
```

### Browse reports in the web UI
```bash
flask --app app.web run
# Visit http://localhost:5000
```

## Cron Setup

```bash
crontab -e
```

Add these entries (adjust the venv path):

```cron
# Generate report every Friday at 4:00 PM
0 16 * * 5 cd ~/Projects/weekly-report && ~/Projects/weekly-report/venv/bin/python generate_report.py >> ~/Projects/weekly-report/data/cron.log 2>&1

# Send report every Sunday at 8:00 PM
0 20 * * 0 cd ~/Projects/weekly-report && ~/Projects/weekly-report/venv/bin/python send_report.py >> ~/Projects/weekly-report/data/cron.log 2>&1
```

## Verification

1. Fill in `.env` with real credentials
2. Run `python generate_report.py` — check that it prints task/email counts and saves a report
3. Run `flask --app app.web run` — visit http://localhost:5000 and verify the report appears
4. Run `python send_report.py` — check that the email arrives
5. Set up cron and verify the jobs fire on schedule
