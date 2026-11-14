from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import html as html_lib
import os
import smtplib
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    user: str
    auth_code: str
    recipient: str


def load_mail_config(environ: Mapping[str, str] | None = None) -> MailConfig:
    env = environ if environ is not None else os.environ
    host = (env.get("BRIEF_SMTP_HOST") or "smtp.qq.com").strip()
    try:
        port = int((env.get("BRIEF_SMTP_PORT") or "465").strip())
    except ValueError:
        port = 465
    user = (env.get("BRIEF_SMTP_USER") or "").strip()
    auth_code = (env.get("BRIEF_SMTP_AUTH_CODE") or "").strip()
    recipient = (env.get("BRIEF_MAIL_TO") or "").strip()
    missing = [
        name
        for name, value in (
            ("BRIEF_SMTP_USER", user),
            ("BRIEF_SMTP_AUTH_CODE", auth_code),
            ("BRIEF_MAIL_TO", recipient),
        )
        if not value
    ]
    if missing:
        raise ValueError("missing mail settings: " + ", ".join(missing))
    return MailConfig(host=host, port=port, user=user, auth_code=auth_code, recipient=recipient)


def redact(text: str, secrets: Iterable[str]) -> str:
    result = str(text or "")
    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")
    return result


def _set_headers(message: EmailMessage, *, subject: str, config: MailConfig) -> None:
    message["Subject"] = subject
    message["From"] = config.user
    message["To"] = config.recipient
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="qq.com")


def build_report_email(
    *,
    report_date: date,
    md_text: str,
    html_text: str,
    config: MailConfig,
) -> EmailMessage:
    message = EmailMessage()
    _set_headers(
        message,
        subject=f"投资日报 {report_date.isoformat()}",
        config=config,
    )
    message.set_content("请在支持 HTML 的客户端查看正文，或打开附件。")
    message.add_alternative(html_text, subtype="html")
    message.add_attachment(
        md_text.encode("utf-8"),
        maintype="text",
        subtype="markdown",
        filename="daily-brief.md",
    )
    message.add_attachment(
        html_text.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename="daily-brief.html",
    )
    return message


def build_failure_email(
    *,
    report_date: date,
    stage: str,
    detail: str,
    coverage: dict[str, int],
    config: MailConfig,
) -> EmailMessage:
    safe_detail = redact(detail, [config.auth_code])
    rows_text = "\n".join(f"- {name}: {count}" for name, count in coverage.items())
    if not rows_text:
        rows_text = "- （无覆盖数据）"
    text = (
        f"投资日报 {report_date.isoformat()} 生成失败。\n\n"
        f"阶段: {stage}\n\n"
        f"当日采集数量:\n{rows_text}\n\n"
        f"错误详情:\n{safe_detail}\n"
    )
    rows_html = "".join(
        f"<tr><td>{html_lib.escape(str(name))}</td><td>{count}</td></tr>"
        for name, count in coverage.items()
    )
    if not rows_html:
        rows_html = "<tr><td colspan=\"2\">无覆盖数据</td></tr>"
    html_body = (
        f"<h2>投资日报 {report_date.isoformat()} 生成失败</h2>"
        f"<p><strong>阶段：</strong>{html_lib.escape(stage)}</p>"
        f"<table border=\"1\" cellpadding=\"6\"><tr><th>来源</th><th>条数</th></tr>"
        f"{rows_html}</table>"
        f"<pre>{html_lib.escape(safe_detail)}</pre>"
    )
    message = EmailMessage()
    _set_headers(
        message,
        subject=f"[失败] 投资日报 {report_date.isoformat()}",
        config=config,
    )
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")
    return message


def send_message(
    message: EmailMessage,
    *,
    config: MailConfig,
    smtp_factory: Callable[..., object] | None = None,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    if message["Message-ID"] is None:
        message["Message-ID"] = make_msgid(domain="qq.com")
    factory = smtp_factory or smtplib.SMTP_SSL
    delays = (10, 30)
    attempts = max(1, retries)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with factory(config.host, config.port, timeout=30) as smtp:
                smtp.login(config.user, config.auth_code)
                smtp.send_message(message)
            return str(message["Message-ID"])
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last_error = exc
            if attempt < attempts - 1:
                sleep(delays[min(attempt, len(delays) - 1)])
    assert last_error is not None
    raise last_error


def send_report_email(
    *,
    report_date: date,
    md_path: Path | str,
    html_path: Path | str,
    config: MailConfig | None = None,
    smtp_factory: Callable[..., object] | None = None,
) -> str:
    config = config or load_mail_config()
    md_text = Path(md_path).read_text(encoding="utf-8")
    html_text = Path(html_path).read_text(encoding="utf-8")
    message = build_report_email(
        report_date=report_date,
        md_text=md_text,
        html_text=html_text,
        config=config,
    )
    return send_message(message, config=config, smtp_factory=smtp_factory)


def send_failure_email(
    *,
    report_date: date,
    stage: str,
    detail: str,
    coverage: dict[str, int],
    config: MailConfig | None = None,
    smtp_factory: Callable[..., object] | None = None,
) -> str:
    config = config or load_mail_config()
    message = build_failure_email(
        report_date=report_date,
        stage=stage,
        detail=detail,
        coverage=coverage,
        config=config,
    )
    return send_message(message, config=config, smtp_factory=smtp_factory)
