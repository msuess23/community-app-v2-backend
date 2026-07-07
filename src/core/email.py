import smtplib
from email.message import EmailMessage
from src.core.config import settings

def send_otp_email(recipient_email: str, otp_code: str):
  """
  Sends an OTP code via SMTP. 
  Designed to be executed in a FastAPI BackgroundTask to avoid blocking the event loop.
  """
  # Fallback for local development without real SMTP credentials
  if not settings.SMTP_HOST:
    print(f"\n[DEV MODE] Simulated Email to {recipient_email}: Your OTP is {otp_code}\n")
    return

  msg = EmailMessage()
  msg.set_content(
    f"Guten Tag,\n\n"
    f"Sie haben das Zurücksetzen Ihres Passworts angefordert.\n"
    f"Ihr 6-stelliger Bestätigungscode lautet: {otp_code}\n\n"
    f"Dieser Code ist für 15 Minuten gültig.\n\n"
    f"Mit freundlichen Grüßen,\nIhr Community-App-Team"
  )
  msg["Subject"] = "Ihr Passwort-Reset Code"
  msg["From"] = settings.SMTP_USER
  msg["To"] = recipient_email

  try:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
      if settings.SMTP_TLS:
        server.starttls()
      server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
      server.send_message(msg)
  except Exception as e:
    # In production, this should be logged to a file or monitoring system like Sentry
    print(f"Failed to send email: {e}")