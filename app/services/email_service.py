import logging
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.time_utils import to_saskatoon_cst
from app.models.user import User
from app.services.calendar_service import (
    build_google_calendar_url,
    build_ics_content,
)

logger = logging.getLogger(__name__)


def _send_email_sync(
    to_email: str,
    subject: str,
    html_body: str,
    ics_content: str | None = None,
) -> None:
    """Send email via SMTP with optional .ics attachment (blocking). Use from background task."""
    if not settings.email_enabled:
        logger.debug("Email disabled (SMTP not configured), skipping send")
        return

    # Outer container is mixed to support body + attachment
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{settings.from_name} <{settings.from_email}>"
    msg["To"] = to_email

    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    if ics_content:
        ics_part = MIMEBase("text", "calendar", method="REQUEST", name="invite.ics")
        ics_part.set_payload(ics_content.encode("utf-8"))
        encoders.encode_base64(ics_part)
        ics_part.add_header("Content-Disposition", "attachment; filename=invite.ics")
        msg.attach(ics_part)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.from_email, [to_email], msg.as_string())
        logger.info("Email sent to %s with subject: %s", to_email, subject)
    except Exception as e:
        logger.exception("Failed to send email to %s: %s", to_email, e)


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _display_contact_mode(contact_mode: str) -> str:
    return contact_mode.replace("_", " ").title()


def _format_service_title(service_type: str | None) -> str:
    if not service_type:
        return "Tax & Advisory Consultation"
    mapping = {
        "personal-tax": "Personal Tax Consultation",
        "business-tax": "Business Tax Advisory",
        "gst-hst-pst-returns": "GST/HST & PST Returns",
        "tax-saving-planning": "Tax Saving Planning",
        "payroll-services": "Payroll Services Consultation",
        "indian-embassy-services": "Indian Embassy & Passport Services",
        "cra-audit-support": "CRA Audit Support",
        "other": "General Tax Consultation",
    }
    return mapping.get(service_type, service_type.replace("-", " ").title())


def _format_cst_slot(slot_start_utc: datetime, duration_minutes: int) -> tuple[str, str]:
    """Return (date_str, slot_display_cst) in Saskatoon CST timezone."""
    start_cst = to_saskatoon_cst(slot_start_utc)
    end_cst = start_cst + timedelta(minutes=duration_minutes)
    date_str = start_cst.strftime("%A, %B %d, %Y")
    time_start_str = start_cst.strftime("%I:%M %p").lstrip("0")
    time_end_str = end_cst.strftime("%I:%M %p CST").lstrip("0")
    slot_display = f"{time_start_str} – {time_end_str} (Saskatoon time)"
    return date_str, slot_display


def build_appointment_confirmation_html(
    recipient_name: str,
    slot_start_utc: datetime,
    duration_minutes: int,
    message: str | None,
    contact_mode: str | None = None,
    service_type: str | None = None,
    contact_address: str | None = None,
    contact_phone: str | None = None,
    google_cal_url: str | None = None,
) -> str:
    """Build HTML body for appointment confirmation with CST time and Google Calendar button."""
    date_str, slot_display = _format_cst_slot(slot_start_utc, duration_minutes)
    address = contact_address or settings.contact_address
    phone = contact_phone or settings.contact_phone
    service_title = _format_service_title(service_type)

    logo_html = ""
    if settings.email_logo_url:
        logo_html = f'<img src="{settings.email_logo_url}" alt="{settings.site_name}" width="120" style="display:block;margin-bottom:24px;" />'

    cal_button_html = ""
    if google_cal_url:
        cal_button_html = f"""
        <div style="margin:24px 0;text-align:center;">
          <a href="{google_cal_url}" target="_blank" style="background-color:#0284c7;color:#ffffff;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none;display:inline-block;">
            📅 Add to Google Calendar
          </a>
          <p style="margin:8px 0 0 0;font-size:12px;color:#6b7280;">(An .ics calendar invite is also attached to this email)</p>
        </div>
        """

    message_section = ""
    if message:
        safe_message = _html_escape(message)
        message_section = f"""
        <p style="margin:0 0 8px 0;color:#374151;"><strong>Your notes:</strong></p>
        <p style="margin:0 0 20px 0;color:#6b7280;font-size:14px;">{safe_message}</p>
        """

    contact_mode_section = ""
    if contact_mode:
        safe_mode = _html_escape(_display_contact_mode(contact_mode))
        contact_mode_section = f"""
        <p style="margin:0 0 12px 0;font-size:14px;color:#374151;">
          <strong>Format:</strong> {safe_mode}
        </p>
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
              <p style="margin:0 0 20px 0;font-size:15px;color:#6b7280;">Hi {recipient_name or "there"}, your consultation is booked.</p>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f9fafb;border-radius:8px;margin-bottom:20px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 4px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Service</p>
                    <p style="margin:0 0 14px 0;font-size:16px;font-weight:600;color:#111827;">{service_title}</p>
                    <p style="margin:0 0 4px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Date & Time (Saskatoon CST)</p>
                    <p style="margin:0 0 4px 0;font-size:16px;font-weight:600;color:#111827;">{date_str}</p>
                    <p style="margin:0;font-size:15px;color:#374151;">{slot_display}</p>
                  </td>
                </tr>
              </table>

              {cal_button_html}
              {contact_mode_section}
              {message_section}

              <p style="margin:0 0 8px 0;font-size:13px;color:#6b7280;">Need to reschedule or have questions? Contact us or manage your booking from your TaxByNav account.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 32px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 4px 0;font-size:13px;font-weight:600;color:#111827;">{settings.site_name}</p>
              <p style="margin:0;font-size:13px;color:#6b7280;">
                {settings.contact_email} &nbsp;·&nbsp; {phone}<br>
                {address}
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


def build_admin_appointment_notification_html(
    slot_start_utc: datetime,
    duration_minutes: int,
    message: str | None = None,
    contact_mode: str | None = None,
    service_type: str | None = None,
    phone_number: str | None = None,
    user: User | None = None,
    guest_email: str | None = None,
    guest_full_name: str | None = None,
    is_reschedule: bool = False,
) -> str:
    """Build HTML body for admin notification when a booking or reschedule occurs."""
    date_str, slot_display = _format_cst_slot(slot_start_utc, duration_minutes)
    service_title = _format_service_title(service_type)

    if user is not None:
        client_name = _html_escape(user.full_name or "Not provided")
        client_email = _html_escape(user.email)
    elif guest_email:
        client_name = _html_escape(guest_full_name or "Not provided")
        client_email = _html_escape(guest_email)
    else:
        client_name = "Not provided"
        client_email = "Not provided"

    client_phone_section = ""
    if phone_number and phone_number.strip():
        client_phone = _html_escape(phone_number.strip())
        client_phone_section = f"""
        <p style="margin:0 0 8px 0;font-size:14px;color:#374151;">
          <strong>Phone:</strong> {client_phone}
        </p>
        """

    message_section = ""
    if message:
        safe_message = _html_escape(message)
        message_section = f"""
        <p style="margin:0 0 4px 0;font-size:14px;color:#374151;"><strong>Notes:</strong></p>
        <p style="margin:0 0 16px 0;color:#6b7280;font-size:14px;">{safe_message}</p>
        """

    contact_mode_section = ""
    if contact_mode:
        safe_mode = _html_escape(_display_contact_mode(contact_mode))
        contact_mode_section = f"""
        <p style="margin:0 0 8px 0;font-size:14px;color:#374151;">
          <strong>Appointment mode:</strong> {safe_mode}
        </p>
        """

    title_text = "Appointment Rescheduled" if is_reschedule else "New Appointment Booked"
    sub_text = (
        "A client has rescheduled an existing appointment."
        if is_reschedule
        else "A client has booked a consultation. Details below:"
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_text}</title>
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,sans-serif;background-color:#f3f4f6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f3f4f6;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);overflow:hidden;">
          <tr>
            <td style="padding:32px 32px 24px 32px;">
              <h1 style="margin:0 0 8px 0;font-size:22px;font-weight:600;color:#111827;">{title_text}</h1>
              <p style="margin:0 0 20px 0;font-size:15px;color:#6b7280;">{sub_text}</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f9fafb;border-radius:8px;margin-bottom:20px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 4px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Service</p>
                    <p style="margin:0 0 12px 0;font-size:16px;font-weight:600;color:#111827;">{service_title}</p>
                    <p style="margin:0 0 4px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:#6b7280;">Date & Time (Saskatoon CST)</p>
                    <p style="margin:0 0 4px 0;font-size:16px;font-weight:600;color:#111827;">{date_str}</p>
                    <p style="margin:0;font-size:15px;color:#374151;">{slot_display}</p>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px 0;font-size:14px;color:#374151;"><strong>Client:</strong> {client_name}</p>
              <p style="margin:0 0 8px 0;font-size:14px;color:#374151;"><strong>Email:</strong> {client_email}</p>
              {client_phone_section}
              {contact_mode_section}
              {message_section}
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
    contact_mode: str | None = None,
    service_type: str | None = None,
    contact_address: str | None = None,
    contact_phone: str | None = None,
) -> None:
    """Compose and send appointment confirmation with Google Calendar button and .ics file."""
    end_utc = slot_start_utc + timedelta(minutes=duration_minutes)
    service_title = _format_service_title(service_type)
    subject = f"{settings.site_name} – Appointment Confirmed: {service_title}"

    loc = contact_address or settings.contact_address
    if contact_mode == "online":
        loc = "Online Video / Phone Consultation (Link will be provided)"

    details_text = f"Consultation with TaxByNav for {service_title}. Mode: {_display_contact_mode(contact_mode or 'online')}"
    if message:
        details_text += f"\n\nClient notes: {message}"

    google_url = build_google_calendar_url(
        title=f"TaxByNav Consultation: {service_title}",
        start_utc=slot_start_utc,
        end_utc=end_utc,
        details=details_text,
        location=loc,
    )

    ics_content = build_ics_content(
        title=f"TaxByNav Consultation: {service_title}",
        start_utc=slot_start_utc,
        end_utc=end_utc,
        details=details_text,
        location=loc,
    )

    html = build_appointment_confirmation_html(
        recipient_name=_html_escape(recipient_name or ""),
        slot_start_utc=slot_start_utc,
        duration_minutes=duration_minutes,
        message=message,
        contact_mode=contact_mode,
        service_type=service_type,
        contact_address=contact_address,
        contact_phone=contact_phone,
        google_cal_url=google_url,
    )

    _send_email_sync(to_email, subject, html, ics_content=ics_content)


def send_admin_appointment_notification_email(
    admin_email: str,
    slot_start_utc: datetime,
    duration_minutes: int,
    message: str | None = None,
    contact_mode: str | None = None,
    service_type: str | None = None,
    phone_number: str | None = None,
    user: User | None = None,
    guest_email: str | None = None,
    guest_full_name: str | None = None,
    is_reschedule: bool = False,
) -> None:
    """Notify admin when a new appointment is booked or rescheduled."""
    prefix = "Rescheduled Appointment" if is_reschedule else "New Appointment Booked"
    service_title = _format_service_title(service_type)
    subject = f"{settings.site_name} – {prefix}: {service_title}"

    html = build_admin_appointment_notification_html(
        slot_start_utc=slot_start_utc,
        duration_minutes=duration_minutes,
        message=message,
        contact_mode=contact_mode,
        service_type=service_type,
        phone_number=phone_number,
        user=user,
        guest_email=guest_email,
        guest_full_name=guest_full_name,
        is_reschedule=is_reschedule,
    )
    _send_email_sync(admin_email, subject, html)


def send_contact_inquiry_admin_email(
    admin_email: str,
    name: str,
    email: str,
    phone: str | None,
    subject: str,
    message: str,
) -> None:
    """Send new contact form inquiry alert to admin."""
    mail_subject = f"{settings.site_name} – New Inquiry from {name}: {subject}"
    safe_name = _html_escape(name)
    safe_email = _html_escape(email)
    safe_phone = _html_escape(phone or "Not provided")
    safe_subject = _html_escape(subject)
    safe_message = _html_escape(message)

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;background-color:#f9fafb;padding:20px;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;padding:24px;border-radius:8px;border:1px solid #e5e7eb;">
    <h2 style="margin-top:0;color:#111827;">New Contact Form Message</h2>
    <p><strong>From:</strong> {safe_name} ({safe_email})</p>
    <p><strong>Phone:</strong> {safe_phone}</p>
    <p><strong>Subject:</strong> {safe_subject}</p>
    <div style="background:#f3f4f6;padding:16px;border-radius:6px;margin:16px 0;">
      <p style="margin:0;white-space:pre-wrap;">{safe_message}</p>
    </div>
    <p style="font-size:12px;color:#6b7280;">You can reply directly to {safe_email}.</p>
  </div>
</body>
</html>
"""
    _send_email_sync(admin_email, mail_subject, html)


def send_contact_acknowledgment_email(
    to_email: str,
    name: str,
    subject: str,
) -> None:
    """Send polite receipt confirmation to client."""
    mail_subject = f"Thank you for contacting {settings.site_name}"
    safe_name = _html_escape(name or "there")
    safe_subject = _html_escape(subject)

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;background-color:#f9fafb;padding:20px;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;padding:24px;border-radius:8px;border:1px solid #e5e7eb;">
    <h2 style="margin-top:0;color:#111827;">Message Received</h2>
    <p>Hi {safe_name},</p>
    <p>Thank you for reaching out regarding <strong>&quot;{safe_subject}&quot;</strong>. We have received your inquiry and our tax advisory team will review it and get back to you promptly.</p>
    <p style="margin-top:24px;font-size:13px;color:#6b7280;">
      Best regards,<br>
      <strong>{settings.site_name}</strong><br>
      {settings.contact_email} &nbsp;·&nbsp; {settings.contact_phone}
    </p>
  </div>
</body>
</html>
"""
    _send_email_sync(to_email, mail_subject, html)
