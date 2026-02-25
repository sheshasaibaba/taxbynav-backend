import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_email_sync(to_email: str, subject: str, html_body: str) -> None:
    """Send email via SMTP (blocking). Use from background task."""
    if not settings.email_enabled:
        logger.debug("Email disabled (SMTP not configured), skipping send")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.from_name} <{settings.from_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.from_email, [to_email], msg.as_string())
        logger.info("Email sent to %s", to_email)
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", to_email, e)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_appointment_confirmation_html(
    recipient_name: str,
    slot_start_utc: datetime,
    duration_minutes: int,
    message: str | None,
) -> str:
    """Build HTML body for appointment confirmation."""
    # Format in a readable way (UTC; you can later add timezone conversion)
    date_str = slot_start_utc.strftime("%A, %B %d, %Y")
    time_str = slot_start_utc.strftime("%I:%M %p")
    end_dt = slot_start_utc + timedelta(minutes=duration_minutes)
    time_end_str = end_dt.strftime("%I:%M %p")
    slot_display = f"{time_str} – {time_end_str} (UTC)"
    logo_html = ""
    if settings.email_logo_url:
        logo_html = f'<img src="{settings.email_logo_url}" alt="{settings.site_name}" width="120" style="display:block;margin-bottom:24px;" />'
    message_section = ""
    if message:
        safe_message = _html_escape(message)
        message_section = f"""
        <p style="margin:0 0 16px 0;color:#374151;"><strong>Your message:</strong></p>
        <p style="margin:0 0 24px 0;color:#6b7280;font-size:14px;">{safe_message}</p>
        """
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Appointment Confirmation</title>
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,sans-serif;background-color:#f3f4f6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f3f4f6;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);overflow:hidden;">
          <tr>
            <td style="padding:32px 32px 24px 32px;">
              {logo_html}
              <h1 style="margin:0 0 8px 0;font-size:22px;font-weight:600;color:#111827;">Appointment Confirmed</h1>
              <p style="margin:0 0 24px 0;font-size:15px;color:#6b7280;">Hi {recipient_name or 'there'}, your consultation is booked.</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f9fafb;border-radius:8px;margin-bottom:24px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 8px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Date</p>
                    <p style="margin:0;font-size:16px;font-weight:600;color:#111827;">{date_str}</p>
                    <p style="margin:12px 0 0 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Time (30-minute session)</p>
                    <p style="margin:0;font-size:16px;font-weight:600;color:#111827;">{slot_display}</p>
                  </td>
                </tr>
              </table>
              {message_section}
              <p style="margin:0 0 8px 0;font-size:14px;color:#374151;">If you need to reschedule or cancel, please contact us.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 32px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 4px 0;font-size:13px;font-weight:600;color:#111827;">{settings.site_name}</p>
              <p style="margin:0;font-size:13px;color:#6b7280;">
                {settings.contact_email} &nbsp;·&nbsp; {settings.contact_phone}<br>
                {settings.contact_address}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_appointment_confirmation_email(
    to_email: str,
    recipient_name: str | None,
    slot_start_utc: datetime,
    duration_minutes: int,
    message: str | None = None,
) -> None:
    """Compose and send appointment confirmation (call from background task)."""
    subject = f"{settings.site_name} – Appointment Confirmed"
    html = build_appointment_confirmation_html(
        recipient_name=_html_escape(recipient_name or ""),
        slot_start_utc=slot_start_utc,
        duration_minutes=duration_minutes,
        message=message,
    )
    _send_email_sync(to_email, subject, html)
