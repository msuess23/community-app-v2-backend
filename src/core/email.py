import logging
import smtplib
import ssl
from email.message import EmailMessage

from src.core.config import settings


logger = logging.getLogger(__name__)


def _send_email(message: EmailMessage) -> None:
  """
  Deliver an email synchronously from a FastAPI background task.

  Delivery failures are intentionally not exposed through password-reset HTTP
  responses, but they are recorded with a traceback for operational diagnosis.
  """
  recipient = str(message.get("To", ""))
  subject = str(message.get("Subject", ""))

  if not settings.SMTP_HOST:
    logger.warning(
      "SMTP is not configured; email was not sent",
      extra={"recipient": recipient, "subject": subject},
    )
    return

  try:
    with smtplib.SMTP(
      settings.SMTP_HOST,
      settings.SMTP_PORT,
      timeout=settings.SMTP_TIMEOUT_SECONDS,
    ) as server:
      if settings.SMTP_TLS:
        server.starttls(context=ssl.create_default_context())
      if settings.SMTP_USER:
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
      server.send_message(message)
  except (OSError, smtplib.SMTPException):
    logger.exception(
      "Email delivery failed",
      extra={"recipient": recipient, "subject": subject},
    )


def _create_message(
  *,
  recipient_email: str,
  subject: str,
  content: str,
) -> EmailMessage:
  message = EmailMessage()
  message.set_content(content)
  message["Subject"] = subject
  message["From"] = settings.SMTP_USER
  message["To"] = recipient_email
  return message


def send_otp_email(recipient_email: str, otp_code: str) -> None:
  """Send a password-reset OTP without ever logging the credential."""
  message = _create_message(
    recipient_email=recipient_email,
    subject="Ihr Passwort-Reset-Code",
    content=(
      "Guten Tag,\n\n"
      "Sie haben das Zurücksetzen Ihres Passworts angefordert.\n"
      f"Ihr 6-stelliger Bestätigungscode lautet: {otp_code}\n\n"
      f"Dieser Code ist für {settings.PASSWORD_RESET_EXPIRE_MINUTES} "
      "Minuten gültig.\n\n"
      "Falls Sie die Änderung nicht angefordert haben, können Sie diese "
      "E-Mail ignorieren.\n\n"
      "Mit freundlichen Grüßen,\nIhr Community-App-Team"
    ),
  )
  _send_email(message)


def send_password_changed_email(recipient_email: str) -> None:
  """Notify the account owner after a successful password reset."""
  message = _create_message(
    recipient_email=recipient_email,
    subject="Ihr Passwort wurde geändert",
    content=(
      "Guten Tag,\n\n"
      "das Passwort Ihres Community-App-Kontos wurde erfolgreich geändert.\n"
      "Alle bestehenden Anmeldesitzungen wurden beendet.\n\n"
      "Falls Sie diese Änderung nicht vorgenommen haben, wenden Sie sich "
      "bitte umgehend an die zuständige Administration.\n\n"
      "Mit freundlichen Grüßen,\nIhr Community-App-Team"
    ),
  )
  _send_email(message)
