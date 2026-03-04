"""Send the HTML digest via SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _html_to_plain(html: str) -> str:
    """Very minimal HTML → plain-text strip for fallback part."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s{2,}", "\n", text)
    return text.strip()


def send_digest(
    html_body: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    email_from: str,
    email_to: str,   # comma-separated
    subject: str,
) -> None:
    """
    Send the rendered HTML digest via SMTP with plain-text fallback.

    Raises:
        smtplib.SMTPException on delivery failure.
    """
    recipients = [addr.strip() for addr in email_to.split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to

    plain_text = _html_to_plain(html_body)
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info(
        "Sending digest to %d recipient(s) via %s:%d…", len(recipients), smtp_host, smtp_port
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(email_from, recipients, msg.as_string())

    logger.info("Digest sent successfully.")
