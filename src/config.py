"""Loader config.yaml + .env og bygger en typed config-objekt."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    raw: dict
    secrets: dict = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str | Path = "config.yaml") -> "Config":
        load_dotenv()
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        secrets = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
            "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
            "MS_CLIENT_ID": os.environ.get("MS_CLIENT_ID", ""),
            "MS_TENANT_ID": os.environ.get("MS_TENANT_ID", "consumers"),
            "MS_REFRESH_TOKEN": os.environ.get("MS_REFRESH_TOKEN", ""),
            "SMTP_HOST": os.environ.get("SMTP_HOST", ""),
            "SMTP_PORT": int(os.environ.get("SMTP_PORT", "587")),
            "SMTP_USER": os.environ.get("SMTP_USER", ""),
            "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        }
        return cls(raw=raw, secrets=secrets)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node
