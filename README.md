# UrbanResolve

UrbanResolve is a civic issue reporting platform built with FastAPI. Citizens can report problems with map-based location pins, image and video evidence, and community comments. Admins can validate issue demand, upload on-site resolution proof, and notify affected users by email.

## Features

- Public issue reporting with category, description, address, exact map pin, image, and video evidence
- Voice-to-text reporting for accessibility using the browser microphone
- Community comments so multiple users can confirm the same issue
- Duplicate issue hotspot detection and severity-based prioritization
- Public ward leaderboard showing which areas are improving fastest
- Admin dashboard with status updates, citizen-facing update messages, and resolution notes
- Admin-only civic heatmap analytics for recurring issue zones
- SLA-based overdue escalation alerts for higher officials through email
- Resolution video upload tied to the same issue, with a 300 meter on-site validation check against the original report location
- Trusted citizen verification with solved/not solved confirmations and image evidence after a fix is claimed
- SMTP-based email notifications to the reporter and commenters, including the resolution video as an attachment when available

## Requirements

Install everything with:

```bash
pip install -r requirements.txt
```

The file includes:

- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy`
- `pydantic`
- `jinja2`
- `python-multipart`

## Run

Open the terminal inside `civic_system`.

Public app:

```bash
uvicorn public_app.main:app --reload --port 8000
```

Admin app:

```bash
uvicorn admin_app.main:app --reload --port 9000
```

## Email Setup

Recommended: create a `.env` file inside `civic_system` (same folder where you run `uvicorn`) and paste:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_16_char_gmail_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_USE_TLS=true
SMTP_DEBUG=true
PUBLIC_BASE_URL=http://127.0.0.1:8000
ESCALATION_EMAIL=higher.authority@example.com
```

Alternative: set variables in PowerShell before starting the apps:

```powershell
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USERNAME="your_email@example.com"
$env:SMTP_PASSWORD="your_app_password"
$env:SMTP_FROM_EMAIL="your_email@example.com"
$env:SMTP_USE_TLS="true"
$env:SMTP_DEBUG="true"
$env:PUBLIC_BASE_URL="http://127.0.0.1:8000"
$env:ESCALATION_EMAIL="higher.authority@example.com"
```

If you use Gmail, create an App Password and use that in `SMTP_PASSWORD`.

Important:
- `SMTP_HOST` is required for non-Gmail domains.
- For Gmail, use `smtp.gmail.com` and an App Password (not your regular Gmail login password).
- `SMTP_FROM_EMAIL` must be a valid email address.

Quick SMTP test from `civic_system`:

```powershell
@'
from shared.email_utils import send_email
ok, msg = send_email("your_test_email@example.com", "UrbanResolve SMTP Test", "If you received this, SMTP is working.")
print(ok, msg)
'@ | python -
```

## Create an Admin User

Open Python in the `civic_system` folder:

```python
from shared.database import SessionLocal
from shared.models import User

db = SessionLocal()
db.add(User(email="admin@example.com", role="admin"))
db.commit()
db.close()
```