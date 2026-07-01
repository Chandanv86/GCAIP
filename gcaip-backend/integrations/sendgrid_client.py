"""SendGrid email client for alert dispatch (Phase 2)."""
import structlog

from config import settings

log = structlog.get_logger(__name__)


class SendGridClient:
    def send_alert_email(self, alert) -> bool:
        """Send an alert email via SendGrid."""
        if not settings.SENDGRID_API_KEY:
            log.warning("sendgrid.no_api_key")
            return False
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            message = Mail(
                from_email=settings.SENDGRID_FROM_EMAIL,
                to_emails=settings.SENDGRID_FROM_EMAIL,  # TODO: user email from AOI
                subject=alert.title,
                html_content=f"""
<h2>{alert.title}</h2>
<p><strong>Severity:</strong> {alert.severity}</p>
<p>{alert.message}</p>
<p><strong>Theme:</strong> {alert.theme}</p>
<p><strong>Triggered:</strong> {alert.triggered_at}</p>
<hr>
<p><em>GCAIP Climate Intelligence Platform</em></p>
""",
            )
            response = sg.send(message)
            return response.status_code in (200, 202)
        except Exception as exc:
            log.error("sendgrid.send_failed", error=str(exc))
            return False
