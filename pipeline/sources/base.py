"""Connector-Schicht: die Plug-in-Grenze der Pipeline.

Jede Datenquelle erbt von :class:`DataSource` und implementiert genau eine
Methode, ``_fetch``. Alles andere -- Caching, Provenienz, Registrierung --
passiert hier. Eine neue Quelle anzubinden heisst: eine Klasse schreiben und
mit ``@register`` versehen. Stufen 03 bis 07 der Pipeline aendern sich nicht.
"""
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
    """Traegt eine Quelle in die Registry ein."""
    _REGISTRY[cls.name] = cls
    return cls


def available() -> dict[str, type["DataSource"]]:
    return dict(_REGISTRY)


def get(name: str) -> "DataSource":
    return _REGISTRY[name]()


@dataclass
class Provenance:
    """Woher ein Datensatz stammt -- wandert bis in die Oberflaeche mit."""

    source: str
    endpoint: str
    fetched_at: str
    rows: int
    note: str = ""


class DataSource(ABC):
    """Gemeinsames Interface aller Quellen.

    ``fetch()`` liefert einen DataFrame und cacht ihn als Parquet. Der Cache
    macht die Pipeline reproduzierbar und schont die APIs; ``force=True``
    erzwingt einen Neuabruf.
    """

    name: str = "unnamed"
    endpoint: str = ""
    #: Kurzbeschreibung fuer die Provenienz-Tabelle im Bericht.
    description: str = ""

    def __init__(self) -> None:
        self.provenance: Provenance | None = None

    @property
    def cache_path(self):
        return RAW / f"{self.name}.parquet"

    @abstractmethod
    def _fetch(self) -> pd.DataFrame:
        """Holt die Rohdaten. Einzige Methode, die eine neue Quelle braucht."""

    def fetch(self, force: bool = False) -> pd.DataFrame:
        if self.cache_path.exists() and not force:
            df = pd.read_parquet(self.cache_path)
            self.provenance = Provenance(
                self.name, self.endpoint, "cache", len(df), "aus Parquet-Cache"
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


# --------------------------------------------------------------------------
# gemeinsamer HTTP-Helfer
# --------------------------------------------------------------------------

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


def get_json(url: str, tries: int = 4, timeout: int = 60, pause: float = 0.0):
    """GET mit Retry. Gibt ``None`` zurueck, wenn alle Versuche scheitern."""
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
