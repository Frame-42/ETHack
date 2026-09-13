"""Source connector registry. Implement _fetch in a DataSource subclass and register it; common code handles caching and fetch metadata."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pandas as pd
import requests

from ..config import RAW, USER_AGENT

_REGISTRY: dict[str, type["DataSource"]] = {}


def register(cls: type["DataSource"]) -> type["DataSource"]:
    """Register a source class."""
    _REGISTRY[cls.name] = cls
    return cls


def available() -> dict[str, type["DataSource"]]:
    return dict(_REGISTRY)


def get(name: str) -> "DataSource":
    return _REGISTRY[name]()


@dataclass
class Provenance:
    """Record source endpoint, retrieval metadata, and row count."""

    source: str
    endpoint: str
    fetched_at: str
    rows: int
    note: str = ""


class DataSource(ABC):
    """Shared source interface. fetch returns a DataFrame, reuses a Parquet cache by default, and refreshes when force=True."""

    name: str = "unnamed"
    endpoint: str = ""
    # Short source description for provenance.
    description: str = ""

    def __init__(self) -> None:
        self.provenance: Provenance | None = None

    @property
    def cache_path(self):
        return RAW / f"{self.name}.parquet"

    @abstractmethod
    def _fetch(self) -> pd.DataFrame:
        """Retrieve source data; implement this method in each connector."""

    def fetch(self, force: bool = False) -> pd.DataFrame:
        if self.cache_path.exists() and not force:
            df = pd.read_parquet(self.cache_path)
            self.provenance = Provenance(
                self.name, self.endpoint, "cache", len(df), "From Parquet cache"
            )
            return df
        df = self._fetch()
        df.to_parquet(self.cache_path, index=False)
        self.provenance = Provenance(
            self.name,
            self.endpoint,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            len(df),
        )
        return df


# Shared HTTP helpers.

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


def get_json(url: str, tries: int = 4, timeout: int = 60, pause: float = 0.0):
    """GET with retries; return None after unsuccessful attempts."""
    for attempt in range(tries):
        try:
            r = session().get(url, timeout=timeout)
            if r.status_code == 200:
                if pause:
                    time.sleep(pause)
                return r.json()
            if r.status_code in (403, 404):
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (attempt + 1))
    return None
