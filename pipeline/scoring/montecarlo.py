"""Stufe 05 A: branchenrelative Kernnote mit Unsicherheitsanalyse.

Das OECD/JRC-Handbuch ist an diesem Punkt eindeutig: Normalisierung,
Gewichtung und Aggregation sind Ermessensentscheidungen, also *muss* gezeigt
werden, wie stark das Ergebnis von ihnen abhaengt. Genau das passiert hier.

Ein Monte-Carlo-Zug zieht zufaellig

* ein Normalisierungsverfahren,
* ein Gewichtungsschema,
* eine Aggregationsfunktion,
* die Ebene der Vergleichsgruppe (Sektor oder Sub-Industry),
* eine Trimmstufe fuer Extremwerte,
* optional das Weglassen einer Kennzahl (Leave-one-out),
* eine Stoerung der Eingangswerte, deren Breite von ``match_confidence``
  abhaengt.

Der letzte Punkt ist der Grund, warum die Unsicherheit aus Stufe 03 nicht
unterwegs verloren geht: Eine Firma, deren Anlagen nur unsicher zugeordnet
werden konnten, bekommt am Ende ein breiteres Rangband.

Ergebnis ist kein Platz, sondern eine Verteilung von Perzentilen innerhalb
der Vergleichsgruppe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .aggregate import AGGREGATORS
from .normalize import NORMALIZERS
from .weight import WEIGHTERS


@dataclass(frozen=True)
class Metric:
    """Eine Kennzahl der Kernnote."""

    column: str
    direction: int  # -1 = kleiner ist besser
    label: str


@dataclass(frozen=True)
class Draw:
    """Eine gezogene Methodenkombination."""

    normalizer: str
    weighter: str
    aggregator: str
    peer_level: str
    winsor: float
    dropped: str | None


@dataclass
class MonteCarloConfig:
    n_draws: int = 1000
    peer_levels: tuple[str, ...] = ("gics_sector", "gics_sub_industry")
    winsor_levels: tuple[float, ...] = (0.0, 0.01, 0.05)
    #: Mindestgroesse einer Vergleichsgruppe; kleinere fallen auf den Sektor zurueck.
    min_peers: int = 6
    #: Grundrauschen auf den Eingangswerten, in Einheiten der Querschnittsstreuung.
    base_noise: float = 0.05
    #: Zusatzrauschen fuer unsicher zugeordnete Firmen.
    match_noise: float = 0.35
    #: Wahrscheinlichkeit, in einem Zug eine Kennzahl wegzulassen.
    p_drop: float = 0.30
    seed: int = 20260912
    normalizers: tuple[str, ...] = field(default_factory=lambda: tuple(NORMALIZERS))
    weighters: tuple[str, ...] = field(default_factory=lambda: tuple(WEIGHTERS))
    aggregators: tuple[str, ...] = field(default_factory=lambda: tuple(AGGREGATORS))


def _peer_key(df: pd.DataFrame, level: str, min_peers: int) -> pd.Series:
    """Vergleichsgruppe je Firma; zu duenne Gruppen fallen auf den Sektor zurueck."""
    key = df[level].astype(str)
    if level == "gics_sector":
        return key
    counts = key.map(key.value_counts())
    return key.where(counts >= min_peers, df["gics_sector"].astype(str))


def score_once(
    df: pd.DataFrame,
    metrics: list[Metric],
    draw: Draw,
    rng: np.random.Generator | None = None,
    cfg: MonteCarloConfig | None = None,
) -> pd.DataFrame:
    """Rechnet eine einzelne Rangliste fuer eine Methodenkombination.

    Rueckgabe je Firma: ``score`` und ``percentile`` (0-100, hoeher = besser)
    innerhalb der Vergleichsgruppe.
    """
    cfg = cfg or MonteCarloConfig()
    used = [m for m in metrics if m.column != draw.dropped]
    if not used:
        used = metrics

    work = df.copy()
    work["_peer"] = _peer_key(work, draw.peer_level, cfg.min_peers)

    # Stoerung der Eingangswerte: additiv in Einheiten der Querschnittsstreuung,
    # damit auch Trendkennzahlen mit negativem Vorzeichen sauber behandelt werden.
    if rng is not None:
        conf = work.get("match_confidence", pd.Series(1.0, index=work.index)).fillna(0.0)
        sigma = cfg.base_noise + cfg.match_noise * (1.0 - conf).clip(0, 1)
        for m in used:
            col = work[m.column].astype(float)
            sd = col.std(ddof=0)
            if np.isfinite(sd) and sd > 0:
                work[m.column] = col + rng.normal(0.0, 1.0, len(col)) * sigma * sd

    # Normalisierung innerhalb jeder Vergleichsgruppe.
    norm_fn = NORMALIZERS[draw.normalizer]
    normed = pd.DataFrame(index=work.index)
    for m in used:
        normed[m.column] = (
            work.groupby("_peer", group_keys=False)[m.column]
            .apply(lambda s, _m=m: norm_fn(s.astype(float), _m.direction, draw.winsor))
            .reindex(work.index)
        )

    w = WEIGHTERS[draw.weighter](normed.fillna(normed.mean()))
    score = AGGREGATORS[draw.aggregator](normed, w)

    out = pd.DataFrame({"ticker": work["ticker"].values, "_peer": work["_peer"].values})
    out["score"] = score.values
    out["percentile"] = (
        out.groupby("_peer")["score"].rank(pct=True, na_option="keep") * 100.0
    )
    return out


def sample_draw(rng: np.random.Generator, metrics: list[Metric], cfg: MonteCarloConfig) -> Draw:
    dropped = None
    if len(metrics) > 2 and rng.random() < cfg.p_drop:
        dropped = metrics[int(rng.integers(len(metrics)))].column
    return Draw(
        normalizer=str(rng.choice(cfg.normalizers)),
        weighter=str(rng.choice(cfg.weighters)),
        aggregator=str(rng.choice(cfg.aggregators)),
        peer_level=str(rng.choice(cfg.peer_levels)),
        winsor=float(rng.choice(cfg.winsor_levels)),
        dropped=dropped,
    )


def run(
    df: pd.DataFrame,
    metrics: list[Metric],
    cfg: MonteCarloConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fuehrt die Unsicherheitsanalyse aus.

    Rueckgabe:
        ``bands``  -- je Firma p10/p50/p90 des Perzentils, Bandbreite, Anteil
                      der Zuege im obersten und untersten Fuenftel
        ``draws``  -- die Perzentile aller Zuege (Firmen x Zuege), fuer
                      Sensitivitaetsauswertungen nach Methode
    """
    cfg = cfg or MonteCarloConfig()
    rng = np.random.default_rng(cfg.seed)

    tickers = df["ticker"].tolist()
    mat = np.full((len(tickers), cfg.n_draws), np.nan)
    meta: list[dict] = []

    for j in range(cfg.n_draws):
        draw = sample_draw(rng, metrics, cfg)
        res = score_once(df, metrics, draw, rng=rng, cfg=cfg)
        mat[:, j] = res["percentile"].to_numpy()
        meta.append(
            {
                "draw": j,
                "normalizer": draw.normalizer,
                "weighter": draw.weighter,
                "aggregator": draw.aggregator,
                "peer_level": draw.peer_level,
                "winsor": draw.winsor,
                "dropped": draw.dropped or "-",
            }
        )

    p10, p50, p90 = (np.nanpercentile(mat, q, axis=1) for q in (10, 50, 90))
    with np.errstate(invalid="ignore"):
        top_share = np.nanmean(mat >= 80.0, axis=1)
        bottom_share = np.nanmean(mat <= 20.0, axis=1)

    bands = pd.DataFrame(
        {
            "ticker": tickers,
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "band_width": p90 - p10,
            "share_top_quintile": top_share * 100.0,
            "share_bottom_quintile": bottom_share * 100.0,
        }
    )
    bands = bands.merge(
        df[["ticker", "company", "gics_sector", "gics_sub_industry", "match_confidence"]],
        on="ticker",
        how="left",
    )
    draws = pd.DataFrame(mat, index=tickers).reset_index(names="ticker")
    draws.attrs["meta"] = pd.DataFrame(meta)
    return bands, pd.DataFrame(meta).join(
        pd.DataFrame(mat.T, columns=tickers)
    )
