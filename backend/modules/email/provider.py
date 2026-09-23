"""Outbound email provider.

Send-only by design: the provider never opens, reads, imports, synchronizes
or deletes anything from a mailbox. The only network operation it performs is
submitting a fully-formed message to an SMTP server.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List

SMTP_DEFAULT_PORT = 587
SMTP_TIMEOUT_SECONDS = 30


class EmailError(Exception):
    """Base class for all email module errors."""


class EmailConfigError(EmailError):
    """Raised when email is enabled but the configuration is invalid."""


class EmailValidationError(EmailError):
    """Raised when a recipient address is invalid."""


class EmailDisabledError(EmailError):
    """Raised when an action requires email to be enabled but it is not."""


class EmailEventError(EmailError):
    """Raised when an unknown email event is requested."""


class EmailAuthError(EmailError):
    """Raised when the SMTP server rejects the configured credentials."""


class EmailTransportError(EmailError):
    """Raised when the SMTP server cannot be reached or rejects the message."""


@dataclass(frozen=True)
class EmailConfig:
    """Immutable view of every email setting the provider needs."""

    enabled: bool = False
    provider: str = "smtp"
    host: str = ""
    port: int = SMTP_DEFAULT_PORT
    username: str = ""
    password: str = ""
    from_addr: str = ""
    use_tls: bool = True
    use_ssl: bool = False

    @classmethod
    def from_mapping(cls, data) -> "EmailConfig":
        """Build an EmailConfig from a plain mapping (e.g. ``app.config``)."""
        return cls(
            enabled=_to_bool(data.get("EMAIL_ENABLED"), False),
            provider=(data.get("EMAIL_PROVIDER") or "smtp").strip().lower(),
            host=(data.get("EMAIL_HOST") or "").strip(),
            port=int(data.get("EMAIL_PORT") or SMTP_DEFAULT_PORT),
            username=(data.get("EMAIL_USERNAME") or "").strip(),
            password=(data.get("EMAIL_PASSWORD") or ""),
            from_addr=(data.get("EMAIL_FROM") or "").strip(),
            use_tls=_to_bool(data.get("EMAIL_USE_TLS"), True),
            use_ssl=_to_bool(data.get("EMAIL_USE_SSL"), False),
        )

    def validate(self) -> None:
        """Raise :class:`EmailConfigError` when the config is unusable.

        Validation only kicks in when email is enabled, so a development
        machine without any SMTP settings boots normally.
        """
        if not self.enabled:
            return
        problems = []
        if not self.host:
            problems.append("EMAIL_HOST is required")
        if not self.from_addr:
            problems.append("EMAIL_FROM is required")
        if not (1 <= self.port <= 65535):
            problems.append("EMAIL_PORT must be between 1 and 65535")
        if self.use_tls and self.use_ssl:
            problems.append("EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive")
        if bool(self.username) != bool(self.password):
            problems.append("EMAIL_USERNAME and EMAIL_PASSWORD must be set together")
        if self.provider not in ("smtp", "gmail"):
            problems.append("EMAIL_PROVIDER must be 'smtp' or 'gmail'")
        if problems:
            raise EmailConfigError(
                "Email is enabled but its configuration is invalid: "
                + "; ".join(problems)
            )


def _to_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class SMTPEmailProvider:
    """Submits email messages to an SMTP server.

    Plain SMTP is used by default with opportunistic STARTTLS when
    ``use_tls`` is set. ``use_ssl`` switches to a pre-wrapped SSL
    connection (implicit TLS, commonly port 465). Authentication is only
    attempted when both ``EMAIL_USERNAME`` and ``EMAIL_PASSWORD`` are set.
    """

    def __init__(self, config: EmailConfig):
        self._config = config
        self._smtp_class = smtplib.SMTP
        self._smtp_ssl_class = smtplib.SMTP_SSL

    @property
    def config(self) -> EmailConfig:
        return self._config

    def send(
        self,
        to: List[str],
        subject: str,
        text_body: str,
        html_body: str = None,
        request_id: str = "",
    ) -> None:
        """Send a message to the given recipients.

        Args:
            to: List of recipient addresses.
            subject: Message subject.
            text_body: Plain text body.
            html_body: Optional HTML body.
            request_id: Correlation id carried as an X-Request-Id header.

        Raises:
            EmailConfigError: If the config rejects the message.
            EmailAuthError: If SMTP authentication fails.
            EmailTransportError: If the server cannot be reached or refuses
                to accept the message.
        """
        config = self._config
        config.validate()
        message = self._build_message(to, subject, text_body, html_body, request_id)
        try:
            server = self._connect(config)
            try:
                self._authenticate(config, server)
                server.send_message(message)
            finally:
                _quit(server)
        except EmailError:
            raise
        except smtplib.SMTPAuthenticationError:
            raise EmailAuthError(
                "SMTP authentication failed; check EMAIL_USERNAME and "
                "EMAIL_PASSWORD"
            )
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailTransportError(f"SMTP send failed: {exc}")

    def _build_message(self, to, subject, text_body, html_body, request_id):
        message = EmailMessage()
        message["From"] = self._config.from_addr
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        if request_id:
            message["X-Request-Id"] = request_id
        message.set_content(text_body or "")
        if html_body:
            message.add_alternative(html_body, subtype="html")
        return message

    def _connect(self, config: EmailConfig):
        if config.use_ssl:
            return self._smtp_ssl_class(
                config.host, config.port, timeout=SMTP_TIMEOUT_SECONDS
            )
        server = self._smtp_class(
            config.host, config.port, timeout=SMTP_TIMEOUT_SECONDS
        )
        if config.use_tls:
            server.starttls(context=ssl.create_default_context())
        return server

    def _authenticate(self, config: EmailConfig, server):
        if config.username and config.password:
            server.login(config.username, config.password)


def _quit(server):
    try:
        server.quit()
    except Exception:
        server.close()