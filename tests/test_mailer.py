from datetime import date
from email.message import EmailMessage

from pipeline.mailer import MailConfig, build_failure_email, build_report_email, send_message

CONFIG = MailConfig("smtp.qq.com", 465, "a@qq.com", "SECRET-CODE", "b@qq.com")


def test_report_email_has_html_body_and_two_attachments():
    msg = build_report_email(
        report_date=date(2026, 11, 14),
        md_text="# 标题\n正文",
        html_text="<h1>标题</h1>",
        config=CONFIG,
    )
    assert msg["Subject"] == "投资日报 2026-11-14"
    assert msg["To"] == "b@qq.com"
    parts = list(msg.walk())
    assert any(p.get_content_type() == "text/html" for p in parts)
    names = [p.get_filename() for p in parts if p.get_filename()]
    assert names == ["daily-brief.md", "daily-brief.html"]


def test_failure_email_redacts_auth_code():
    msg = build_failure_email(
        report_date=date(2026, 11, 14),
        stage="headless",
        detail="login failed SECRET-CODE",
        coverage={"雪球": 0},
        config=CONFIG,
    )
    assert msg["Subject"] == "[失败] 投资日报 2026-11-14"
    assert "SECRET-CODE" not in msg.as_string()


def test_failure_email_redaction_survives_decoding():
    msg = build_failure_email(
        report_date=date(2026, 11, 14),
        stage="headless",
        detail="login failed SECRET-CODE",
        coverage={"雪球": 0},
        config=CONFIG,
    )
    text_part = msg.get_body(preferencelist=("plain",))
    assert text_part is not None
    assert "SECRET-CODE" not in text_part.get_content()


def test_send_message_retries_then_returns_message_id():
    class FakeSMTP:
        attempts = 0

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, code):
            assert (user, code) == ("a@qq.com", "SECRET-CODE")

        def send_message(self, msg):
            FakeSMTP.attempts += 1
            if FakeSMTP.attempts < 2:
                raise OSError("temporary")

    msg = EmailMessage()
    msg["Subject"] = "s"
    msg["To"] = "b@qq.com"
    msg.set_content("x")
    message_id = send_message(msg, config=CONFIG, smtp_factory=FakeSMTP, sleep=lambda _: None)
    assert message_id.startswith("<")
    assert FakeSMTP.attempts == 2
