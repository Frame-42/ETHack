"""
Materialitaet aus der Taetigkeit statt aus dem Sektorlabel.

Der uebliche Weg: eine Tabelle ordnet jedem GICS-Sektor Themen zu, jede
Firma erbt das Profil ihres Sektors. Eine Firma, die drei Dinge gleichzeitig
tut, bekommt trotzdem nur ein Profil.

Hier: Jede Anlage hat einen NAICS-Code, also eine dokumentierte Taetigkeit.
Das Materialitaetsprofil einer Firma ist die emissionsgewichtete Mischung
der Profile ihrer Taetigkeiten. Berkshire bekommt damit das Profil eines
Stromerzeugers, weil dort die Anlagen stehen - nicht das einer Bank.

Zweiter Teil: Fuer jedes als relevant erkannte Thema wird geprueft, ob es
aus freien Quellen ueberhaupt messbar ist. Die Differenz ist die
Messluecke - und die ist das eigentliche Ergebnis.
"""
import numpy as np
import pandas as pd
from pathlib import Path

F = Path("fusion")
LATEST = 2023

# ----------------------------------------------------------------------
# Zwoelf Themen. Bewusst an dem ausgerichtet, was industrielle Taetigkeit
# physisch erzeugt - nicht an einem Berichtsstandard.
TOPICS = [
    "Treibhausgase", "Energie und Brennstoffmix", "Luftschadstoffe",
    "Giftstoffe", "Wasser", "Abfall", "Flaeche und Natur",
    "Arbeitssicherheit", "Regeltreue", "Lieferkette",
    "Transitionsrisiko", "Physisches Klimarisiko",
]

# Taetigkeitsprofile je NAICS-3. Regel: Ein Thema ist relevant (2), wenn die
# Taetigkeit es systematisch erzeugt, teilweise relevant (1), wenn nur unter
# bestimmten Bedingungen, sonst 0. Abgeleitet aus der Taetigkeitsbeschreibung
# des NAICS-Codes, nicht aus einer Branchentabelle.
ACTIVITY = {
    "221": ("Stromerzeugung und Versorgung",
            dict(Treibhausgase=2, **{"Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
            "Giftstoffe": 1, "Wasser": 2, "Abfall": 1, "Flaeche und Natur": 2,
            "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 1,
            "Transitionsrisiko": 2, "Physisches Klimarisiko": 2})),
    "211": ("Oel- und Gasfoerderung",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 1, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 1,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "324": ("Raffinerien",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 1,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 1,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "325": ("Chemie",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 1,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 2,
             "Transitionsrisiko": 1, "Physisches Klimarisiko": 1}),
    "327": ("Zement, Glas, Beton",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 1, "Wasser": 1, "Abfall": 1, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 1, "Lieferkette": 1,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "331": ("Metallerzeugung",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 1,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 2,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "212": ("Bergbau",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 1,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "322": ("Papier und Zellstoff",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 1, "Lieferkette": 2,
             "Transitionsrisiko": 1, "Physisches Klimarisiko": 1}),
    "486": ("Pipelines",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 1,
             "Giftstoffe": 1, "Wasser": 1, "Abfall": 0, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 0,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 2}),
    "562": ("Abfallwirtschaft",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 2,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 2, "Lieferkette": 1,
             "Transitionsrisiko": 1, "Physisches Klimarisiko": 1}),
    "311": ("Lebensmittelherstellung",
            {"Treibhausgase": 1, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 1,
             "Giftstoffe": 1, "Wasser": 2, "Abfall": 2, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 1, "Lieferkette": 2,
             "Transitionsrisiko": 1, "Physisches Klimarisiko": 2}),
    "334": ("Elektronikfertigung",
            {"Treibhausgase": 1, "Energie und Brennstoffmix": 2, "Luftschadstoffe": 1,
             "Giftstoffe": 2, "Wasser": 2, "Abfall": 1, "Flaeche und Natur": 0,
             "Arbeitssicherheit": 1, "Regeltreue": 1, "Lieferkette": 2,
             "Transitionsrisiko": 1, "Physisches Klimarisiko": 1}),
    "336": ("Fahrzeugbau",
            {"Treibhausgase": 1, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 1,
             "Giftstoffe": 2, "Wasser": 1, "Abfall": 2, "Flaeche und Natur": 0,
             "Arbeitssicherheit": 2, "Regeltreue": 1, "Lieferkette": 2,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
    "213": ("Bergbau-/Foerderdienstleistungen",
            {"Treibhausgase": 2, "Energie und Brennstoffmix": 1, "Luftschadstoffe": 2,
             "Giftstoffe": 1, "Wasser": 1, "Abfall": 1, "Flaeche und Natur": 2,
             "Arbeitssicherheit": 2, "Regeltreue": 1, "Lieferkette": 1,
             "Transitionsrisiko": 2, "Physisches Klimarisiko": 1}),
}
DEFAULT = ("Sonstige Industrie",
           {t: 1 for t in TOPICS})

# Welche Themen sind aus den tatsaechlich angebundenen freien Quellen messbar?
# "voll": eine unabhaengige Messung je Firma liegt vor.
# "teil": nur fuer einen Teil der Firmen oder als Naeherung.
# "nein": keine freie Quelle.
MEASURABLE = {
    "Treibhausgase": ("voll", "EPA GHGRP, Scope 1, Anlagenebene"),
    "Energie und Brennstoffmix": ("voll", "EPA Unit & Fuel Data, Kohleanteil"),
    "Luftschadstoffe": ("teil", "TRI deckt Chemikalien, nicht NOx/SOx/PM"),
    "Giftstoffe": ("voll", "EPA TRI, inkl. Krebserreger-Kennzeichen"),
    "Wasser": ("nein", "keine freie firmenscharfe Quelle"),
    "Abfall": ("nein", "RCRA nur zweijaehrlich, eigene Kennungen"),
    "Flaeche und Natur": ("nein", "keine freie firmenscharfe Quelle"),
    "Arbeitssicherheit": ("teil", "OSHA ITA, 47 von 116 Firmen"),
    "Regeltreue": ("nein", "EPA ECHO angebunden, Daten fehlen noch"),
    "Lieferkette": ("nein", "Scope 3 nicht frei verfuegbar"),
    "Transitionsrisiko": ("teil", "Kohleanteil und Trend als Naeherung"),
    "Physisches Klimarisiko": ("nein", "keine freie firmenscharfe Quelle"),
}


# ----------------------------------------------------------------------
def build_company_materiality():
    """Emissionsgewichtete Mischung der Taetigkeitsprofile je Firma."""
    fac = pd.read_parquet(F / "src_epa_facility.parquet")
    link = pd.read_parquet("build/src_parent_link.parquet")
    er = pd.read_parquet(F / "src_entity_resolution.parquet")
    er = er[(er.threshold == 90) & er.company_id.notna()]

    f = fac[fac.reporting_year == LATEST]
    l = link[link.reporting_year == LATEST]
    m = (l.merge(f[["facility_id", "co2e_tonnes", "naics_code"]], on="facility_id")
           .merge(er[["name_raw", "company_id"]], left_on="parent_name_raw",
                  right_on="name_raw"))
    m["attr"] = m.co2e_tonnes * m.parent_share_pct / 100.0
    m["naics3"] = m.naics_code.astype(str).str[:3]
    m["company_id"] = m.company_id.astype(int)

    panel_ids = set(pd.read_parquet(F / "int_indicator_panel.parquet").company_id)
    m = m[m.company_id.isin(panel_ids)]

    rows, mix_rows = [], []
    for cid, g in m.groupby("company_id"):
        w = g.groupby("naics3").attr.sum()
        w = w / w.sum()
        prof = {t: 0.0 for t in TOPICS}
        for n3, share in w.items():
            name, p = ACTIVITY.get(n3, DEFAULT)
            for t in TOPICS:
                prof[t] += share * p.get(t, 0)
        rows.append({"company_id": cid, **prof})
        top = w.sort_values(ascending=False).head(3)
        mix_rows.append({"company_id": cid,
                         "haupttaetigkeit": ACTIVITY.get(top.index[0], DEFAULT)[0],
                         "anteil_haupt": round(float(top.iloc[0]), 3),
                         "n_taetigkeiten": int((w > 0.05).sum())})

    mat = pd.DataFrame(rows)
    mix = pd.DataFrame(mix_rows)
    meta = pd.read_parquet(F / "out_rank_bands.parquet")[
        ["company_id", "ticker", "company_name", "gics_sector", "profile_group"]]
    out = mat.merge(mix, on="company_id").merge(meta, on="company_id")
    out.to_parquet(F / "out_materiality.parquet", index=False)
    out.to_csv(F / "out_materiality.csv", index=False)

    print(f"out_materiality: {len(out)} Firmen, Profil aus "
          f"{m.naics3.nunique()} Taetigkeiten gemischt")
    print(f"  Firmen mit mehr als einer relevanten Taetigkeit: "
          f"{(out.n_taetigkeiten > 1).sum()} von {len(out)}")
    return out


# ----------------------------------------------------------------------
def coverage_gap(mat, schwelle=1.5):
    """Fuer jede Vergleichsgruppe: wie viele relevante Themen sind messbar?"""
    rows = []
    for grp, g in mat.groupby("profile_group"):
        for t in TOPICS:
            rel = float(g[t].mean())
            if rel < schwelle:
                continue
            status, note = MEASURABLE[t]
            rows.append({"gruppe": grp, "thema": t, "relevanz": round(rel, 2),
                         "messbar": status, "quelle": note})
    d = pd.DataFrame(rows)
    d.to_csv(F / "out_coverage_gap.csv", index=False)

    summ = (d.assign(voll=(d.messbar == "voll").astype(int),
                     teil=(d.messbar == "teil").astype(int))
              .groupby("gruppe")
              .agg(relevant=("thema", "size"), voll=("voll", "sum"),
                   teil=("teil", "sum")))
    summ["luecke"] = summ.relevant - summ.voll - summ.teil
    summ["quote"] = ((summ.voll + 0.5 * summ.teil) / summ.relevant * 100).round(0)

    names = mat.groupby("profile_group").haupttaetigkeit.agg(
        lambda s: s.value_counts().index[0])
    summ["haupttaetigkeit"] = names
    summ = summ.sort_values("quote", ascending=False)
    summ.to_csv(F / "out_coverage_gap_summary.csv")

    print("\nMessluecke je Vergleichsgruppe:")
    print(summ.to_string())
    tot_rel = len(d)
    tot_voll = (d.messbar == "voll").sum()
    tot_teil = (d.messbar == "teil").sum()
    print(f"\nGesamt: {tot_rel} relevante Thema-Gruppe-Paare, "
          f"{tot_voll} voll messbar, {tot_teil} teilweise, "
          f"{tot_rel-tot_voll-tot_teil} gar nicht "
          f"= {(tot_rel-tot_voll-tot_teil)/tot_rel*100:.0f} Prozent blind")
    return d, summ


if __name__ == "__main__":
    mat = build_company_materiality()
    coverage_gap(mat)
