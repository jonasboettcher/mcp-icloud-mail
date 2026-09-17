import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, SecretStr, field_validator


class Config(BaseModel):
    email: str
    app_password: SecretStr
    public_url: str = "http://localhost:8000"
    login_key_hash: str = ""
    drafts_folder: str | None = None
    state_dir: Path = Path("state")
    max_message_bytes: int = 25 * 1024 * 1024

    @field_validator('app_password')
    @classmethod
    def nonempty_password(cls, value):
        if not value.get_secret_value():
            raise ValueError('An app-specific password is required')
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if any(c in value for c in "\r\n\x00") or value.count("@") != 1:
            raise ValueError("A full email address is required")
        value.encode("ascii")
        return value

    @field_validator("public_url")
    @classmethod
    def valid_url(cls, value):
        u = urlsplit(value)
        if u.username or u.password or u.query or u.fragment or u.path not in ("", "/") or not u.hostname:
            raise ValueError("public_url must be an origin without path or credentials")
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1")):
            raise ValueError("HTTPS is required except on localhost")
        return value.rstrip("/")


def config_path():
    return Path(os.environ.get("ICLOUD_MAIL_CONFIG", Path.home() / ".config/icloud-mail/config.json"))


def load_config():
    path = config_path()
    if not path.is_file():
        raise RuntimeError("Configuration missing. Run icloud-mail-setup in a private terminal.")
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise RuntimeError("Configuration permissions must be 0600.")
    return Config.model_validate(json.loads(path.read_text()))
