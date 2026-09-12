import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def safe_text(value: str) -> str:
    if not value or len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid text value")
    return value


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    label: str = Field(max_length=80)
    host: str = "imap.mailprotect.be"
    port: int = Field(default=993, ge=1, le=65535)
    username_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    password_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    folders: list[str] = Field(min_length=1, max_length=20)
    enabled: bool = False
    airmail_flag_verified: bool = False

    @field_validator("host")
    @classmethod
    def host_name(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", value):
            raise ValueError("Invalid IMAP host")
        return value

    @field_validator("folders")
    @classmethod
    def folder_names(cls, value):
        for folder in value:
            safe_text(folder)
        if len(set(value)) != len(value):
            raise ValueError("Duplicate folders")
        return value

    def credentials(self):
        username, password = os.getenv(self.username_env), os.getenv(self.password_env)
        if not username or not password:
            raise ValueError("Mailbox secrets are not configured")
        return username, password


class MailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    accounts: list[Account] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_accounts(self):
        if len({a.id for a in self.accounts}) != len(self.accounts):
            raise ValueError("Duplicate account IDs")
        if not any(a.enabled for a in self.accounts):
            raise ValueError("Enable at least one account explicitly")
        return self

    @classmethod
    def load(cls):
        return cls.model_validate_json(Path(os.environ["IMAP_CONFIG_FILE"]).read_text())


def https_url(value: str) -> str:
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("A canonical HTTPS URL is required")
    return value


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    resource: str
    issuer: str
    jwks_url: str
    allowed_subjects: list[str] = Field(min_length=1, max_length=10)
    allowed_client_ids: list[str] = Field(min_length=1, max_length=10)

    @field_validator("resource", "issuer", "jwks_url")
    @classmethod
    def secure_urls(cls, value):
        return https_url(value)

    @field_validator("resource")
    @classmethod
    def mcp_path(cls, value):
        if urlsplit(value).path != "/mcp":
            raise ValueError("Resource URL must end in /mcp")
        return value

    @classmethod
    def load(cls):
        return cls(
            resource=os.environ["MCP_RESOURCE_URL"],
            issuer=os.environ["OAUTH_ISSUER"],
            jwks_url=os.environ["OAUTH_JWKS_URL"],
            allowed_subjects=os.environ["OAUTH_ALLOWED_SUBJECTS"].split(),
            allowed_client_ids=os.environ["OAUTH_ALLOWED_CLIENT_IDS"].split(),
        )

