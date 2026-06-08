import mimetypes
import os
import smtplib
from email.message import EmailMessage

LOADED_ENV_FILES = []
CHECKED_ENV_FILES = []

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional import safety
    load_dotenv = None


def _load_env_files():
    """
    Load .env files so SMTP works even when vars are not exported
    in the active shell session.
    """
    if not load_dotenv:
        return

    cwd_env = os.path.join(os.getcwd(), ".env")
    project_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    project_env = os.path.abspath(project_env)
    root_env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    root_env = os.path.abspath(root_env)

    for env_path in [cwd_env, project_env, root_env]:
        CHECKED_ENV_FILES.append(env_path)
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
            LOADED_ENV_FILES.append(env_path)


_load_env_files()


def _env_flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_password(password: str | None) -> str | None:
    if not password:
        return password
    # Gmail displays app passwords as four groups separated by spaces.
    return "".join(password.split())


def send_email(to_email: str, subject: str, body: str, attachments: list[str] | None = None) -> tuple[bool, str]:
    """
    Send a real email using SMTP configuration from environment variables.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = _normalize_password(os.getenv("SMTP_PASSWORD"))
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username or "noreply@urbanresolve.local")
    use_tls = _env_flag("SMTP_USE_TLS", "true")
    use_ssl = _env_flag("SMTP_USE_SSL", "false")
    debug = _env_flag("SMTP_DEBUG", "false")

    # Convenience default for Gmail users who forgot to set SMTP_HOST.
    if not smtp_host and smtp_username and smtp_username.lower().endswith("@gmail.com"):
        smtp_host = "smtp.gmail.com"

    if not smtp_host or not from_email:
        checked = ", ".join(CHECKED_ENV_FILES) if CHECKED_ENV_FILES else "no .env files checked"
        loaded = ", ".join(LOADED_ENV_FILES) if LOADED_ENV_FILES else "none"
        msg = (
            "SMTP is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL. "
            f"Loaded .env files: {loaded}. Checked: {checked}."
        )
        print(f"[EMAIL ERROR] {msg}")
        return False, msg

    if "@" not in from_email:
        msg = "SMTP_FROM_EMAIL is invalid."
        print(f"[EMAIL ERROR] {msg}")
        return False, msg

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(body)

    for attachment_path in attachments or []:
        if not attachment_path or not os.path.exists(attachment_path):
            continue

        mime_type, _ = mimetypes.guess_type(attachment_path)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)

        with open(attachment_path, "rb") as attachment_file:
            message.add_attachment(
                attachment_file.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(attachment_path)
            )

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

    try:
        if debug:
            print(
                f"[EMAIL DEBUG] host={smtp_host} port={smtp_port} "
                f"tls={use_tls} ssl={use_ssl} from={from_email} to={to_email}"
            )
        with smtp_class(smtp_host, smtp_port, timeout=30) as server:
            if not use_ssl and use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
        msg = "Email sent successfully."
        if debug:
            print(f"[EMAIL DEBUG] {msg}")
        return True, msg
    except smtplib.SMTPAuthenticationError as exc:
        msg = (
            "SMTP authentication failed. For Gmail, use a 16-character Google App Password "
            "with 2-Step Verification enabled, not your normal Gmail password."
        )
        if debug:
            print(f"[EMAIL DEBUG] Raw SMTP auth error: {exc}")
        print(f"[EMAIL ERROR] {msg}")
        return False, msg
    except Exception as exc:
        msg = str(exc)
        print(f"[EMAIL ERROR] {msg}")
        return False, msg
