import pytest
from household_imap.config import MailConfig, AuthConfig


@pytest.fixture
def mail_config(monkeypatch):
    monkeypatch.setenv("IMAP_USER", "test@example.invalid")
    monkeypatch.setenv("IMAP_PASSWORD", "fake-test-password")
    return MailConfig(accounts=[dict(id="personal", label="Test", username_env="IMAP_USER",
                                    password_env="IMAP_PASSWORD", enabled=True, folders=["INBOX", "Sent"]),
                                dict(id="hidden", label="Hidden", username_env="HIDDEN_USER",
                                     password_env="HIDDEN_PASSWORD", enabled=False, folders=["INBOX"])])


@pytest.fixture
def auth_config():
    return AuthConfig(resource="https://mail.example.com/mcp", issuer="https://auth.example.com/",
                      jwks_url="https://auth.example.com/.well-known/jwks.json",
                      allowed_subjects=["owner"], allowed_client_ids=["chatgpt-client"])
