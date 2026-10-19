import logging
import smtplib
from email.message import EmailMessage
from fastapi import HTTPException, status
from app.config import settings

logger = logging.getLogger("loja3d.email")

# Messages captured when EMAIL_BACKEND=console, so tests and developers can read them.
outbox: list = []


def send_email(to: str, subject: str, body: str) -> None:
    """Send an e-mail through the configured backend.

    The console backend only logs the message and is refused in production, so a
    delivery is never reported as successful when nothing was actually sent.
    """
    backend = settings.EMAIL_BACKEND.lower()
    if backend == "console":
        if settings.ENVIRONMENT.lower() == "production":
            logger.error("EMAIL_BACKEND=console is not allowed in production.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Serviço de e-mail não configurado.",
            )
        outbox.append({"to": to, "subject": subject, "body": body})
        logger.warning("[DEV EMAIL] to=%s subject=%s\n%s", to, subject, body)
        return

    if backend == "smtp":
        if not settings.SMTP_HOST:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Serviço de e-mail não configurado.")
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                if settings.SMTP_STARTTLS:
                    smtp.starttls()
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError):
            logger.exception("Failed to send e-mail to %s", to)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Não foi possível enviar o e-mail.")
        return

    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Serviço de e-mail não configurado.")
