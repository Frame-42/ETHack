"""Vergleichsgruppen ("Peer Groups") für den branchenrelativen Vergleich.

Warum diese Datei existiert: Khan, Serafeim & Yoon (2016) zeigen, dass nur
branchenrelevante Kennzahlen Aussagekraft haben, und ein Stromversorger stößt
pro Umsatzdollar rund hundertmal mehr CO2 aus als ein Softwarehaus. Eine
gemeinsame Rangliste misst daher die Branche, nicht die Anstrengung. Die
Normalisierung muss folglich *innerhalb* einer Gruppe passieren -- und die
Gruppendefinition ist damit eine Ermessensentscheidung wie Normalisierung,
Gewichtung und Aggregation. Sie gehört deshalb in die Robustheitsschleife
(OECD/JRC, Nardo et al. 2008).

Drei Ebenen, absichtlich verschachtelt:

* ``ARCHETYPES`` -- 6 Wirkungsort-Archetypen. Grobe Ebene für Kommunikation
  und als Rückfallposition, wenn die Datendichte eine feine Gruppe nicht
  trägt.
* ``GROUPS`` -- 18 Vergleichsgruppen. Das ist die Ranking-Ebene.
* GICS Sub-Industry (127 Werte im Index) -- zu dünn besetzt für ein Ranking,
  aber die richtige Ebene für die Sensitivitätsanalyse.

Zuordnung erfolgt primär über die GICS Sub-Industry und wird durch
``TICKER_OVERRIDES`` korrigiert, wo eine Sub-Industry in sich uneinheitlich
ist. Jeder Override ist begründet -- ohne Begründung kein Override.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Mindestbesetzung einer Gruppe. Unterhalb davon ist eine Rangnormalisierung
# innerhalb der Gruppe nicht mehr sinnvoll interpretierbar: bei n = 12 beträgt
# die kleinste Rangdifferenz schon 8 Perzentilpunkte.
MIN_GROUP_SIZE = 12


@dataclass(frozen=True)
class Archetype:
    """Wo der dominante Fußabdruck physisch entsteht."""

    key: str
    label: str
    locus: str
    consequence: str


ARCHETYPES: dict[str, Archetype] = {
    a.key: a
    for a in [
        Archetype(
            "A1",
            "Prozess- und Verbrennungsemissionen vor Ort",
            "Scope 1 aus eigenen Anlagen (Feuerung, Chemie, Kalzinierung, Prozessgase)",
            "Einzige Gruppe, in der EPA GHGRP und Climate TRACE die Kennzahl direkt "
            "und unabhängig belegen. CO2-Intensität ist hier die Hauptkennzahl.",
        ),
        Archetype(
            "A2",
            "Mobile Verbrennung",
            "Scope 1 aus Flotten: Kerosin, Schiffsdiesel, Diesel, Traktion",
            "Physische Leistungseinheit statt Umsatz als Bezugsgröße "
            "(Tonnenkilometer, Passagierkilometer, Bettennächte).",
        ),
        Archetype(
            "A3",
            "Nutzungsphase der verkauften Produkte",
            "Scope 3 Kategorie 11, oft 80 bis 90 Prozent des Gesamtausstoßes",
            "Eigener Scope 1 ist hier nahezu irrelevant. Aussagekräftig sind "
            "Produktflottenwerte (g CO2/km, Verbrauch je Flugstunde) und die "
            "Portfolioumstellung, nicht die Werksemission.",
        ),
        Archetype(
            "A4",
            "Vorgelagerte Lieferkette",
            "Scope 3 Kategorie 1: Agrarrohstoffe, Grundstoffe, Auftragsfertigung",
            "Werte sind unzuverlässig (Schätzung, Doppelzählung). Deshalb als "
            "Abdeckungs- und Governance-Merkmal messen: Lieferantenprogramm, "
            "Entwaldungspolitik, Wasser- und Materialintensität.",
        ),
        Archetype(
            "A5",
            "Eingekaufte Elektrizität für Anlagen und Flächen",
            "Scope 2 aus Rechenzentren, Netzen, Gebäuden, Filialen",
            "Vergleichbar über Energieintensität je Fläche bzw. je Rechenlast, "
            "Erneuerbaren-Anteil und Beschaffungsqualität (24/7 vs. Zertifikate).",
        ),
        Archetype(
            "A6",
            "Finanzierte und versicherte Emissionen",
            "Scope 3 Kategorie 15; laut CDP über 99 Prozent des Fußabdrucks",
            "Der eigene Betrieb ist Messrauschen. Relevant sind Portfoliokennzahlen "
            "(PCAF), Sektor-Exposure und Ausschluss- bzw. Engagement-Politik.",
        ),
    ]
}


@dataclass(frozen=True)
class Group:
    """Eine Vergleichsgruppe: Mitglieder, Materialität, Datenlage."""

    key: str
    label: str
    archetype: str
    rationale: str
    material: tuple[str, ...]
    denominator: str
    level: str
    coverage: str
    sub_industries: tuple[str, ...] = ()
    tiers: tuple[str, ...] = field(default=())


GROUPS: tuple[Group, ...] = (
    Group(
        key="G01",
        label="Fossile Energiewirtschaft",
        archetype="A1",
        rationale=(
            "Der Fußabdruck steckt im Produkt, nicht im Betrieb. Trotzdem ist die "
            "betriebliche Seite gut messbar und trennscharf: Methanschlupf und "
            "Abfackelung unterscheiden Förderer um Faktoren, während ihre "
            "Produktemissionen fast identisch sind."
        ),
        material=(
            "Methanintensität der Förderung",
            "Abfackelungsrate",
            "Scope-1-Intensität je Barrel Öläquivalent",
            "Reserven-Exposure (stranded assets)",
            "Investitionsanteil in emissionsarme Energie",
        ),
        denominator="Barrel Öläquivalent bzw. verarbeitete Menge, nicht Umsatz "
        "(Umsatz schwankt mit dem Ölpreis und verzerrt Zeitreihen)",
        level="hoch",
        coverage="hoch: EPA GHGRP und Climate TRACE erfassen Anlagen dieser Gruppe "
        "praktisch vollständig",
        sub_industries=(
            "Integrated Oil & Gas",
            "Oil & Gas Exploration & Production",
            "Oil & Gas Refining & Marketing",
            "Oil & Gas Storage & Transportation",
            "Oil & Gas Equipment & Services",
        ),
        tiers=("Förderung", "Midstream", "Raffination", "Ausrüster"),
    ),
    Group(
        key="G02",
        label="Versorger & Umweltinfrastruktur",
        archetype="A1",
        rationale=(
            "Regulierte Netzmonopole mit eigener Verbrennung. Der Erzeugungsmix "
            "erklärt fast die gesamte Streuung, deshalb ist er die Kennzahl und "
            "nicht der Umsatz. Abfall- und Wasserwirtschaft steht hier, weil "
            "Deponiemethan derselben Logik folgt: eigene Anlage, behördlich "
            "gemeldet, physisch messbar."
        ),
        material=(
            "CO2-Intensität je erzeugter MWh",
            "Kohleanteil an der Erzeugung und Stilllegungsplan",
            "Deponiemethan und Gasverwertungsquote",
            "Anteil erneuerbarer Kapazität am Zubau",
            "Netzverluste bzw. Wasserverluste",
        ),
        denominator="MWh Erzeugung, Tonne Abfall, Kubikmeter Wasser",
        level="hoch",
        coverage="hoch: EPA GHGRP deckt Kraftwerke und Deponien über der "
        "25 000-Tonnen-Schwelle ab",
        sub_industries=(
            "Electric Utilities",
            "Multi-Utilities",
            "Independent Power Producers & Energy Traders",
            "Gas Utilities",
            "Water Utilities",
        ),
        tiers=("Stromerzeuger", "Mehrspartenversorger", "Wasser", "Abfall"),
    ),
    Group(
        key="G03",
        label="Rohstoff- & Prozessindustrie",
        archetype="A1",
        rationale=(
            "Chemie, Zement, Stahl, Papier: ein Teil der Emissionen ist chemisch "
            "unvermeidbar (Kalzinierung, Reduktion) und nicht durch Grünstrom zu "
            "beseitigen. Diese Gruppe darf man nur gegen sich selbst messen, sonst "
            "bestraft das Modell Physik statt Verhalten."
        ),
        material=(
            "Scope-1-Intensität je Tonne Produkt",
            "Energieintensität der Prozesse",
            "Wasserentnahme in Wasserstressgebieten",
            "Gefährlicher Abfall und Luftschadstoffe",
            "Anteil Sekundär- bzw. Rezyklatmaterial",
        ),
        denominator="Tonne Produkt (Umsatz je Tonne schwankt mit Rohstoffpreisen)",
        level="hoch",
        coverage="hoch: klassische GHGRP-Melder",
        sub_industries=(
            "Specialty Chemicals",
            "Commodity Chemicals",
            "Industrial Gases",
            "Fertilizers & Agricultural Chemicals",
            "Construction Materials",
            "Steel",
            "Copper",
            "Gold",
            "Paper & Plastic Packaging Products & Materials",
            "Metal, Glass & Plastic Containers",
        ),
        tiers=("Chemie", "Baustoffe", "Metalle & Bergbau", "Papier & Verpackung"),
    ),
    Group(
        key="G04",
        label="Transport & Logistik",
        archetype="A2",
        rationale=(
            "Flottenbetreiber: Fluggesellschaften, Reedereien, Bahnen, "
            "Speditionen. Der Treibstoffverbrauch ist der Fußabdruck, und er ist "
            "je Leistungseinheit direkt vergleichbar. Kreuzfahrtreedereien stehen "
            "hier und nicht bei den Hotels: ein Schiff ist ein Verbrennungsmotor "
            "mit Betten."
        ),
        material=(
            "Treibstoffintensität je Tonnen- bzw. Passagierkilometer",
            "Flottenalter und -effizienz",
            "Anteil alternativer Treibstoffe (SAF, LNG, Elektrifizierung)",
            "Luftschadstoffe und Schwefelgehalt (Schifffahrt)",
            "Arbeitssicherheit",
        ),
        denominator="Tonnenkilometer, verfügbare Sitzkilometer, Bettennächte",
        level="mittel",
        coverage="mittel: Climate TRACE modelliert Luft- und Seeverkehr, "
        "EPA erfasst ortsfeste Anlagen nur teilweise",
        sub_industries=(
            "Passenger Airlines",
            "Air Freight & Logistics",
            "Rail Transportation",
            "Cargo Ground Transportation",
        ),
        tiers=("Luftfahrt", "Schifffahrt", "Schiene", "Straße"),
    ),
    Group(
        key="G05",
        label="Fahrzeug-, Luftfahrt- & Wehrtechnik",
        archetype="A3",
        rationale=(
            "Langlebige Investitionsgüter, deren Emissionen beim Kunden "
            "entstehen. Ein Autohersteller mit sauberer Fabrik und "
            "Verbrennerflotte ist nicht nachhaltig; die Werksemission zu ranken "
            "wäre hier das klassische Fehlmaß."
        ),
        material=(
            "Flottenemissionswert der verkauften Produkte (g CO2/km, kg/Flugstunde)",
            "Anteil emissionsfreier Antriebe am Absatz",
            "Materialintensität und Recyclingfähigkeit",
            "Lücke zwischen Reduktionsversprechen und Ist-Entwicklung",
            "Arbeitssicherheit in der Fertigung",
        ),
        denominator="verkaufte Einheit bzw. Produktflotte, nicht Umsatz",
        level="niedrig",
        coverage="keine kostenlose Quelle für die Nutzungsphase; Flottenwerte "
        "nur aus Unternehmensberichten und Zulassungsstatistiken",
        sub_industries=(
            "Aerospace & Defense",
            "Automobile Manufacturers",
            "Automotive Parts & Equipment",
        ),
        tiers=("Automobil", "Zivile Luftfahrt", "Verteidigung", "Zulieferer"),
    ),
    Group(
        key="G06",
        label="Investitionsgüter & Bauwirtschaft",
        archetype="A3",
        rationale=(
            "Maschinen-, Elektro- und Bauindustrie. Diskrete Fertigung mit "
            "moderatem eigenem Ausstoß, relevanter Vorkette (Stahl, Kupfer) und "
            "Wirkung über die Effizienz des verkauften Geräts. Bauträger und "
            "Bauunternehmen stehen hier, weil ihr Hebel ebenfalls im Gebauten "
            "liegt, nicht im eigenen Betrieb."
        ),
        material=(
            "Scope-1- und Scope-2-Intensität der Fertigung",
            "Energieeffizienz bzw. Emissionsvermeidung des verkauften Produkts",
            "Anteil Umsatz aus Effizienz- und Elektrifizierungslösungen",
            "Eingebundener Kohlenstoff (Beton, Stahl) bei Bau und Bauträgern",
            "Arbeitssicherheit",
        ),
        denominator="Umsatz (bereinigt) je Segment; bei Bauträgern je Wohneinheit",
        level="mittel",
        coverage="mittel: einzelne Werke in GHGRP, Produktkennzahlen nur aus "
        "Berichten",
        sub_industries=(
            "Industrial Machinery & Supplies & Components",
            "Construction Machinery & Heavy Transportation Equipment",
            "Agricultural & Farm Machinery",
            "Electrical Components & Equipment",
            "Heavy Electrical Equipment",
            "Building Products",
            "Construction & Engineering",
            "Trading Companies & Distributors",
            "Homebuilding",
            "Industrial Conglomerates",
        ),
        tiers=("Maschinenbau", "Elektrotechnik", "Bauprodukte", "Bau & Bauträger"),
    ),
    Group(
        key="G07",
        label="Halbleiter & Elektronikfertigung",
        archetype="A4",
        rationale=(
            "Die Gruppe mit der größten internen Spreizung und deshalb die "
            "wichtigste Tier-Unterscheidung: ein Fab-Betreiber trägt Prozessgase "
            "(hohes GWP), gigantischen Strom- und Wasserbedarf selbst; ein "
            "Fabless-Designer und ein Markenhersteller ohne eigene Fertigung "
            "haben denselben Fußabdruck in der Vorkette. Wer beide auf einer "
            "Skala misst, belohnt Auslagerung."
        ),
        material=(
            "Scope-1- und Scope-2-Intensität (nur Fab-Betreiber)",
            "Prozessgase mit hohem Treibhauspotenzial (PFC, SF6, NF3)",
            "Wasserentnahme und Wiederverwendungsquote",
            "Auftragsfertigungs-Programm und Lieferanten-Energiepolitik (Fabless)",
            "Produktenergieeffizienz und Elektroschrott-Rücknahme",
        ),
        denominator="Wafer-Startfläche bzw. Umsatz; Tier getrennt normalisieren",
        level="gemischt",
        coverage="Fab-Betreiber mittel (US-Werke in GHGRP), Fabless und Markenhersteller "
        "niedrig -- Climate TRACE erfasst diesen Sektor nicht",
        sub_industries=(
            "Semiconductors",
            "Semiconductor Materials & Equipment",
            "Electronic Components",
            "Electronic Manufacturing Services",
            "Electronic Equipment & Instruments",
            "Technology Hardware, Storage & Peripherals",
            "Communications Equipment",
        ),
        tiers=(
            "Fab-Betreiber",
            "Fabless",
            "Ausrüstung & Material",
            "Geräte & Markenhardware",
        ),
    ),
    Group(
        key="G08",
        label="Nahrungsmittel, Getränke & Tabak",
        archetype="A4",
        rationale=(
            "Agrarvorkette dominiert: Landnutzung, Methan aus Tierhaltung, "
            "Düngemittel, Wasser. Wasserverbrauch ist hier existenziell und für "
            "ein Softwarehaus bedeutungslos -- das Lehrbuchbeispiel für "
            "Materialität."
        ),
        material=(
            "Wasserentnahme, gewichtet nach Wasserstress am Standort",
            "Landnutzungs- und Entwaldungspolitik der Beschaffung",
            "Verpackungsmaterial und Rezyklatanteil",
            "Lebensmittelverluste",
            "Scope-1-/2-Intensität der Verarbeitung",
        ),
        denominator="Tonne bzw. Hektoliter Produkt; Umsatz nur als Ersatzgröße",
        level="mittel",
        coverage="mittel: Verarbeitungswerke teils in GHGRP, Agrarvorkette "
        "kostenlos nicht belastbar",
        sub_industries=(
            "Packaged Foods & Meats",
            "Soft Drinks & Non-alcoholic Beverages",
            "Agricultural Products & Services",
            "Distillers & Vintners",
            "Brewers",
            "Tobacco",
        ),
        tiers=("Verarbeitung", "Getränke", "Agrarhandel", "Tabak"),
    ),
    Group(
        key="G09",
        label="Markenkonsumgüter (Non-Food)",
        archetype="A4",
        rationale=(
            "Haushalt, Körperpflege, Bekleidung, Schuhe: eigene Fertigung klein, "
            "Wirkung in Auftragsfertigung, Chemie, Textilfärberei und "
            "Verpackung. Sozialkennzahlen der Lieferkette sind hier nicht "
            "Beiwerk, sondern das Hauptrisiko."
        ),
        material=(
            "Lieferanten-Audits und Arbeitsbedingungen in der Vorkette",
            "Wasser- und Chemikalieneinsatz der Auftragsfertigung",
            "Materialherkunft und Rezyklatanteil",
            "Verpackung und Rücknahme",
            "Scope-1-/2-Intensität der eigenen Standorte",
        ),
        denominator="Umsatz; Einheiten nur segmentweise vergleichbar",
        level="niedrig",
        coverage="niedrig: keine Anlagendaten, Auswertung aus Berichten "
        "(HuggingFace-Korpus) und Auditlisten",
        sub_industries=(
            "Household Products",
            "Personal Care Products",
            "Apparel, Accessories & Luxury Goods",
            "Footwear",
            "Leisure Products",
            "Consumer Electronics",
        ),
        tiers=("Haushalt & Pflege", "Bekleidung & Schuhe", "Freizeitgüter"),
    ),
    Group(
        key="G10",
        label="Handel, Distribution & Gastronomie",
        archetype="A4",
        rationale=(
            "Fläche, Kühlung, Sortiment. Der größte eigene Hebel sind "
            "Kältemittelverluste -- eine Kennzahl, die in Gesamtscores meist "
            "untergeht, obwohl sie bei Lebensmittelhändlern zweistellige "
            "Prozentanteile des Scope 1 ausmacht. Gastronomie steht hier, weil "
            "Beschaffung und Kühlung dieselbe Struktur haben."
        ),
        material=(
            "Kältemittelverluste (CO2-Aequivalent je Filiale bzw. Fläche)",
            "Energieintensität je Quadratmeter Verkaufs- und Lagerfläche",
            "Emissionen der eigenen Auslieferungsflotte",
            "Lebensmittel- und Verpackungsabfall",
            "Beschaffungspolitik für kritische Rohstoffe",
        ),
        denominator="Quadratmeter Fläche bzw. Filialzahl, zusätzlich Umsatz",
        level="niedrig",
        coverage="niedrig bis mittel: Kältemittel nur aus Berichten, "
        "Verteilzentren teils in GHGRP",
        sub_industries=(
            "Consumer Staples Merchandise Retail",
            "Food Retail",
            "Food Distributors",
            "Broadline Retail",
            "Home Improvement Retail",
            "Apparel Retail",
            "Automotive Retail",
            "Other Specialty Retail",
            "Computer & Electronics Retail",
            "Homefurnishing Retail",
            "Distributors",
            "Health Care Distributors",
            "Restaurants",
        ),
        tiers=("Lebensmittelhandel", "Fachhandel", "Distribution", "Gastronomie"),
    ),
    Group(
        key="G11",
        label="Pharma, Biotech & Medizintechnik",
        archetype="A4",
        rationale=(
            "Wirkstoffproduktion ist Feinchemie mit Lösemittel- und "
            "Sonderabfallproblem; Medizintechnik ist diskrete Fertigung mit "
            "Einwegprodukten und Sterilisationschemie (Ethylenoxid). Gemeinsam "
            "ist die regulierte Produktsicherheit als Governance-Achse."
        ),
        material=(
            "Scope-1-/2-Intensität der Produktion",
            "Gefährlicher Abfall und Lösemittelbilanz",
            "Wirkstoffeinträge in Gewässer",
            "Sterilisationsemissionen und Einwegmaterialanteil",
            "Produktsicherheit und Rückrufe",
        ),
        denominator="Umsatz; bei Wirkstoffherstellern zusätzlich Tonne Wirkstoff",
        level="mittel",
        coverage="mittel: Chemieanlagen teils in GHGRP, Entsorgungsdaten in "
        "US-Behördenregistern",
        sub_industries=(
            "Pharmaceuticals",
            "Biotechnology",
            "Life Sciences Tools & Services",
            "Health Care Equipment",
            "Health Care Supplies",
        ),
        tiers=("Pharma", "Biotech", "Labortechnik", "Medizingeräte"),
    ),
    Group(
        key="G12",
        label="Gesundheitsversorgung, Kostenträger & klinische Dienste",
        archetype="A5",
        rationale=(
            "Kliniken, Labore, Dialyse, Auftragsforschung, Krankenversicherer. "
            "Kein Produkt, keine "
            "Fabrik: der Fußabdruck ist Gebäudeenergie plus Narkosegase, und "
            "bei den Kostenträgern liegt er faktisch im Kapitalanlageportfolio. "
            "Die Gruppe braucht deshalb eine eigene Kennzahlenwahl."
        ),
        material=(
            "Energieintensität je Quadratmeter Klinik- und Laborfläche",
            "Narkose- und Kältegase",
            "Medizinischer Sonderabfall",
            "Kapitalanlage-Exposure der Versicherer (analog PCAF)",
            "Patientensicherheit und Datenschutz",
        ),
        denominator="Quadratmeter bzw. Belegungstag; bei Versicherern Prämienvolumen",
        level="niedrig",
        coverage="niedrig: praktisch keine kostenlose Anlagendatenquelle",
        sub_industries=(
            "Managed Health Care",
            "Health Care Services",
            "Health Care Facilities",
            "Health Care Technology",
        ),
        tiers=("Kostenträger", "Leistungserbringer", "Labore & Forschung"),
    ),
    Group(
        key="G13",
        label="Software & digitale Plattformen",
        archetype="A5",
        rationale=(
            "Anlagenarm: kein eigenes Rechenzentrum, kein Werk. Der Fußabdruck "
            "ist eingekaufte Cloud-Leistung, Büroenergie und Dienstreisen -- also "
            "fast vollständig Scope 3. Genau hier sind Gesamtscores am "
            "irreführendsten, weil eine niedrige absolute Emission wie Leistung "
            "aussieht, obwohl sie Geschäftsmodell ist."
        ),
        material=(
            "Emissionen eingekaufter Cloud-Leistung (Scope 3 Kat. 1)",
            "Büroenergie je Mitarbeitendem und Dienstreisen",
            "Datenschutz und Datensicherheit",
            "Humankapital: Fluktuation, Löhne, Diversität",
            "Governance: Aktionärsrechte, Stimmrechtsstruktur, Vergütung",
        ),
        denominator="Mitarbeitende (die einzige belastbare physische Bezugsgröße "
        "in dieser Gruppe)",
        level="niedrig",
        coverage="niedrig: weder EPA noch Climate TRACE erfassen diese Gruppe; "
        "Governance- und Sozialkennzahlen aus SEC-Einreichungen",
        sub_industries=(
            "Application Software",
            "Systems Software",
            "IT Consulting & Other Services",
            "Technology Distributors",
            "Interactive Home Entertainment",
            "Specialized Consumer Services",
            "Passenger Ground Transportation",
        ),
        tiers=("Unternehmenssoftware", "Marktplätze & Plattformen", "IT-Dienste"),
    ),
    Group(
        key="G14",
        label="Rechenzentren, Netze & Funktürme",
        archetype="A5",
        rationale=(
            "Betreiber physischer digitaler Infrastruktur: Hyperscaler, "
            "Telekommunikation, Rechenzentrums- und Funkturm-REITs. Sie sind "
            "Großverbraucher von Strom und Kühlwasser und damit untereinander "
            "hervorragend vergleichbar -- aber nicht mit anlagenarmer Software. "
            "Dass GICS Microsoft und einen 300-Personen-Softwareanbieter in "
            "dieselbe Sub-Industry legt, ist der teuerste Vergleichsfehler im "
            "Technologiesektor."
        ),
        material=(
            "Energieverbrauch und Effizienz (PUE) der Rechenzentren",
            "Anteil erneuerbarer Energie und Beschaffungsqualität "
            "(stundenscharf vs. bilanziell)",
            "Wasserverbrauch der Kühlung, gewichtet nach Wasserstress",
            "Notstrom-Scope-1 (Diesel) und Kältemittel",
            "Elektroschrott und Hardware-Lebensdauer",
        ),
        denominator="MWh Verbrauch bzw. installierte Kapazität (MW), "
        "nicht Umsatz",
        level="mittel",
        coverage="mittel: Verbrauch aus Unternehmensberichten belastbar, "
        "Emissionsfaktoren aus Netzdaten ableitbar",
        sub_industries=(
            "Interactive Media & Services",
            "Internet Services & Infrastructure",
            "Integrated Telecommunication Services",
            "Wireless Telecommunication Services",
            "Cable & Satellite",
            "Data Center REITs",
            "Telecom Tower REITs",
        ),
        tiers=("Hyperscaler", "Telekommunikation", "Rechenzentrums-Vermieter"),
    ),
    Group(
        key="G15",
        label="Transaktions- & Informationsdienstleister",
        archetype="A5",
        rationale=(
            "Zahlungsverkehr, Börsen, Ratings, Datenanbieter. Sie sehen wie "
            "Finanzunternehmen aus, tragen aber kein Kreditportfolio: es gibt "
            "keine finanzierten Emissionen zu messen. Ihr Fußabdruck ist "
            "Rechenzentrumsstrom, ihr Hauptrisiko ist Governance -- bei "
            "Ratingagenturen und Indexanbietern zusätzlich der "
            "Interessenkonflikt, den sie selbst bewerten."
        ),
        material=(
            "Energieintensität der Transaktionsinfrastruktur",
            "Anteil erneuerbarer Energie",
            "Datensicherheit und Systemverfügbarkeit",
            "Governance und Interessenkonflikte",
            "Humankapital",
        ),
        denominator="Transaktionsvolumen bzw. Mitarbeitende",
        level="niedrig",
        coverage="niedrig: keine Anlagendaten",
        sub_industries=(
            "Transaction & Payment Processing Services",
            "Financial Exchanges & Data",
            "Data Processing & Outsourced Services",
            "Research & Consulting Services",
        ),
        tiers=("Zahlungsverkehr", "Marktinfrastruktur", "Daten & Ratings"),
    ),
    Group(
        key="G16",
        label="Banken, Versicherer & Vermögensverwalter",
        archetype="A6",
        rationale=(
            "Die einzige Gruppe, in der eigene Emissionen strukturell "
            "bedeutungslos sind: laut CDP liegen über 99 Prozent im Portfolio. "
            "Eine Bank nach Büroenergie zu ranken ist die sauberste "
            "Ausblendung, die ein ESG-Score anbieten kann -- sie misst "
            "Klimaanlagen statt Kreditbücher."
        ),
        material=(
            "Finanzierte Emissionen nach PCAF (Kredit- und Anlagebuch)",
            "Exposure gegenüber fossiler Förderung und Kohleverstromung",
            "Versicherungstechnisches Exposure (Underwriting fossiler Projekte)",
            "Stimmrechtsausübung und Engagement-Politik",
            "Governance: Vergütung, Aufsichtsstruktur, Fehlverhaltensfälle",
        ),
        denominator="Bilanzsumme, verwaltetes Vermögen, Prämienvolumen",
        level="niedrig",
        coverage="niedrig: PCAF-Werte nur aus freiwilligen Berichten; "
        "Stimmrechtsdaten aus SEC N-PX öffentlich",
        sub_industries=(
            "Diversified Banks",
            "Regional Banks",
            "Investment Banking & Brokerage",
            "Asset Management & Custody Banks",
            "Consumer Finance",
            "Property & Casualty Insurance",
            "Life & Health Insurance",
            "Multi-line Insurance",
            "Reinsurance",
            "Multi-Sector Holdings",
        ),
        tiers=("Banken", "Versicherer", "Vermögensverwalter", "Konsumentenkredit"),
    ),
    Group(
        key="G17",
        label="Immobilien & Gebäudebetrieb",
        archetype="A5",
        rationale=(
            "Bestandshalter und Betreiber von Fläche: REITs, Hotelbetreiber, "
            "Casinoresorts. Vergleichbar über Energie je Quadratmeter -- eine "
            "Kennzahl, die es in dieser Gruppe tatsächlich flächendeckend gibt "
            "(GRESB, Zertifizierungen), anders als in den meisten anderen."
        ),
        material=(
            "Energieintensität je Quadratmeter (kWh/m2)",
            "Anteil zertifizierter Fläche und Sanierungsquote",
            "Eingebundener Kohlenstoff bei Neubau",
            "Wasserverbrauch und Klimarisiko-Exposure der Standorte",
            "Kältemittel",
        ),
        denominator="Quadratmeter bzw. Zimmer, nicht Umsatz",
        level="mittel",
        coverage="mittel: Flächen- und Verbrauchsdaten in REIT-Berichten "
        "vergleichsweise standardisiert",
        sub_industries=(
            "Multi-Family Residential REITs",
            "Single-Family Residential REITs",
            "Retail REITs",
            "Office REITs",
            "Industrial REITs",
            "Health Care REITs",
            "Self-Storage REITs",
            "Hotel & Resort REITs",
            "Timber REITs",
            "Other Specialized REITs",
            "Real Estate Services",
            "Casinos & Gaming",
        ),
        tiers=("Wohnen", "Gewerbe", "Beherbergung", "Spezial"),
    ),
    Group(
        key="G18",
        label="Medien & unternehmensnahe Dienste",
        archetype="A5",
        rationale=(
            "Inhalte, Werbung, Personal, Versicherungsmakler, Facility-Dienste. "
            "Anlagenarm wie G13, aber ohne Cloud-Kostentreiber; der Fußabdruck "
            "sind Produktionen, Veranstaltungen, Fuhrparks und Büros. Eigene "
            "Gruppe, weil ihre relevanten Achsen sozial und governancebezogen "
            "sind -- nicht energetisch."
        ),
        material=(
            "Büroenergie und Fuhrpark bzw. Produktionsemissionen",
            "Dienstreisen und Veranstaltungslogistik",
            "Humankapital: Arbeitsbedingungen, Fluktuation, Löhne",
            "Governance: Stimmrechtsstruktur, Unabhängigkeit des Aufsichtsrats",
            "Integrität der Inhalte bzw. Beratungsunabhängigkeit",
        ),
        denominator="Mitarbeitende",
        level="niedrig",
        coverage="niedrig: keine Anlagendaten, Auswertung aus Berichten",
        sub_industries=(
            "Movies & Entertainment",
            "Advertising",
            "Broadcasting",
            "Publishing",
            "Human Resource & Employment Services",
            "Diversified Support Services",
            "Insurance Brokers",
            "Environmental & Facilities Services",
        ),
        tiers=("Medien & Inhalte", "Werbung", "Personal & Beratung", "Facility"),
    ),
)

GROUPS_BY_KEY: dict[str, Group] = {g.key: g for g in GROUPS}

# Sub-Industry -> Gruppe. Aus GROUPS abgeleitet, damit es nur eine Wahrheit gibt.
SUB_INDUSTRY_MAP: dict[str, str] = {
    sub: g.key for g in GROUPS for sub in g.sub_industries
}

# Wo eine GICS Sub-Industry in sich uneinheitlich ist, entscheidet der Ticker.
# Jeder Eintrag: (Zielgruppe, Begründung). Ohne Begründung kein Override.
TICKER_OVERRIDES: dict[str, tuple[str, str]] = {
    # "Hotels, Resorts & Cruise Lines" vereint drei unvereinbare Profile.
    "CCL": ("G04", "Kreuzfahrt: Schiffsdiesel, mobile Verbrennung statt Gebäude"),
    "RCL": ("G04", "Kreuzfahrt: Schiffsdiesel, mobile Verbrennung statt Gebäude"),
    "NCLH": ("G04", "Kreuzfahrt: Schiffsdiesel, mobile Verbrennung statt Gebäude"),
    "MAR": ("G17", "Hotelbetrieb: Fußabdruck ist Gebäudeenergie je Zimmer"),
    "HLT": ("G17", "Hotelbetrieb: Fußabdruck ist Gebäudeenergie je Zimmer"),
    "ABNB": ("G13", "Plattform ohne eigene Immobilien"),
    "BKNG": ("G13", "Buchungsplattform ohne eigene Immobilien"),
    "EXPE": ("G13", "Buchungsplattform ohne eigene Immobilien"),
    # Hyperscaler: eigene Rechenzentren, nicht anlagenarme Software.
    "MSFT": ("G14", "Betreibt eigene Hyperscale-Rechenzentren"),
    "ORCL": ("G14", "Betreibt eigene Cloud-Rechenzentren (OCI)"),
    "RDDT": ("G13", "Plattform auf eingekaufter Cloud, kein eigenes Rechenzentrum"),
    "EBAY": ("G13", "Marktplatz ohne eigenes Warenlager und Fuhrpark"),
    # Konglomerate nach dominanter physischer Tätigkeit.
    "DD": ("G03", "Chemieproduktion, kein diversifizierter Industriebetrieb"),
    "VLTO": ("G06", "Hersteller von Wasser- und Analysetechnik, kein Entsorger"),
    "WM": ("G02", "Deponiemethan und Sammelflotte: eigene Scope-1-Anlagen"),
    "RSG": ("G02", "Deponiemethan und Sammelflotte: eigene Scope-1-Anlagen"),
    # Gesundheitswesen: Produkt vs. Versorgung.
    "SOLV": ("G11", "Hersteller von Medizinprodukten, keine Software"),
    "VEEV": ("G13", "Branchensoftware, kein Leistungserbringer"),
    "IQV": (
        "G12",
        "Klinische Auftragsforschung und Gesundheitsdaten: Materialität ist "
        "Patientendatenschutz und Studienethik, nicht Produktion",
    ),
    # Finanz: Portfoliorisiko vs. reines Dienstleistungsgeschäft.
    "CBRE": ("G18", "Vermittlung und Verwaltung ohne eigenen Bestand"),
    "CSGP": ("G13", "Datenplattform, kein Immobilienbestand"),
    # Leidos ist IT-Dienstleister im Verteidigungsumfeld, kein Fertiger.
    "LDOS": ("G13", "IT-Dienstleistung, keine Wehrtechnikfertigung"),
}

# Sub-Industries, die GICS so heterogen definiert, dass es keine sinnvolle
# Standardgruppe gibt: hier entscheidet ausschließlich der Ticker. Die
# Validierung verlangt, dass jedes Mitglied einen Override hat.
SPLIT_ONLY: frozenset[str] = frozenset({"Hotels, Resorts & Cruise Lines"})

# Firmen, deren Zuordnung strittig bleibt. Der Sensitivitätslauf variiert sie
# über die genannten Gruppen; die Notiz sagt, worin der Streit besteht. Kippt
# eine Rangaussage an einer dieser Firmen, ist sie keine Aussage über die Firma,
# sondern über die Gruppenwahl.
CONTESTED: dict[str, tuple[tuple[str, ...], str]] = {
    "BRK.B": (
        ("G16", "G02", "G04"),
        "Konglomerat: Versicherer, aber Eigentümer einer Güterbahn und mehrerer "
        "Stromversorger. Keine Gruppe beschreibt die Firma zutreffend.",
    ),
    "AMZN": (
        ("G10", "G14"),
        "Handel und Logistik dominieren den physischen Fußabdruck, AWS den "
        "Stromverbrauch. Beide Gruppen sind vertretbar.",
    ),
    "MSFT": (
        ("G14", "G13"),
        "Erlös ist Software, Fußabdruck ist Rechenzentrum.",
    ),
    "ORCL": (("G14", "G13"), "Wie MSFT: Softwareerlös, Rechenzentrumsbetrieb."),
    "FSLR": (
        ("G07", "G02"),
        "Fertigt Solarmodule wie ein Halbleiterwerk, verkauft aber "
        "Erzeugungskapazität.",
    ),
    "UBER": (
        ("G13", "G04"),
        "Vermittelt Fahrten ohne eigene Flotte: Emissionen entstehen bei "
        "Fahrern (Scope 3), nicht im eigenen Betrieb.",
    ),
    "DASH": (("G13", "G10"), "Plattform mit Lieferlogistik ohne eigene Flotte."),
    "IRM": (
        ("G17", "G14"),
        "Überwiegend Archivflächen, wachsendes Rechenzentrumsgeschäft.",
    ),
    "CVS": (
        ("G12", "G10"),
        "Krankenversicherer und Apothekenkette mit mehreren tausend Filialen.",
    ),
    "IQV": (("G12", "G11", "G13"), "Auftragsforschung, Gesundheitsdaten, Software."),
    "DD": (("G03", "G06"), "Nach mehreren Abspaltungen zwischen Chemie und Technik."),
    "MMM": (("G06", "G03"), "Mischkonzern mit erheblichem Chemieanteil."),
    "HON": (("G06", "G05"), "Industrietechnik mit Luftfahrtsparte."),
    "LDOS": (("G13", "G05"), "IT-Dienstleister im Verteidigungsumfeld."),
    "CTAS": (
        ("G18", "G09"),
        "Dienstleister, dessen Fußabdruck aus industrieller Wäscherei stammt "
        "(Wasser, Energie) -- untypisch für seine Gruppe.",
    ),
}

def assign(df: pd.DataFrame) -> pd.DataFrame:
    """Ordnet Konstituenten einer Vergleichsgruppe und einem Archetyp zu.

    Erwartet die Spalten ``ticker`` und ``gics_sub_industry``. Ergänzt
    ``peer_group``, ``peer_label``, ``archetype`` sowie ``assign_reason``,
    damit jede Zuordnung im Ergebnis begründet bleibt.
    """
    missing = {"ticker", "gics_sub_industry"} - set(df.columns)
    if missing:
        raise KeyError(f"Spalten fehlen: {sorted(missing)}")

    known = set(SUB_INDUSTRY_MAP) | set(SPLIT_ONLY)
    unmapped = sorted(set(df["gics_sub_industry"]) - known)
    if unmapped:
        raise ValueError(
            "Nicht zugeordnete GICS Sub-Industries -- Mapping ergänzen: "
            + ", ".join(unmapped)
        )

    out = df.copy()
    out["peer_group"] = out["gics_sub_industry"].map(SUB_INDUSTRY_MAP)
    out["assign_reason"] = "GICS Sub-Industry"

    hit = out["ticker"].isin(TICKER_OVERRIDES)
    out.loc[hit, "peer_group"] = out.loc[hit, "ticker"].map(
        lambda t: TICKER_OVERRIDES[t][0]
    )
    out.loc[hit, "assign_reason"] = out.loc[hit, "ticker"].map(
        lambda t: TICKER_OVERRIDES[t][1]
    )

    out["peer_label"] = out["peer_group"].map(lambda k: GROUPS_BY_KEY[k].label)
    out["archetype"] = out["peer_group"].map(lambda k: GROUPS_BY_KEY[k].archetype)
    out["archetype_label"] = out["archetype"].map(lambda a: ARCHETYPES[a].label)
    out["contested"] = out["ticker"].isin(CONTESTED)
    return out


def validate(assigned: pd.DataFrame) -> list[str]:
    """Prüft die Zuordnung. Gibt die Liste der Befunde zurück, leer = sauber."""
    problems: list[str] = []
    open_rows = assigned[assigned["peer_group"].isna()]
    if not open_rows.empty:
        problems.append(
            "Ohne Gruppe: " + ", ".join(sorted(open_rows["ticker"]))
            + " -- entweder Sub-Industry ins Mapping aufnehmen oder "
            "Ticker-Override ergänzen"
        )
    for sub in SPLIT_ONLY:
        rows = assigned[assigned["gics_sub_industry"] == sub]
        ohne = sorted(set(rows["ticker"]) - set(TICKER_OVERRIDES))
        if ohne:
            problems.append(
                f"Sub-Industry '{sub}' ist als SPLIT_ONLY markiert, aber ohne "
                f"Override: {', '.join(ohne)}"
            )

    sizes = assigned["peer_group"].value_counts()
    for key in GROUPS_BY_KEY:
        n = int(sizes.get(key, 0))
        if n < MIN_GROUP_SIZE:
            problems.append(
                f"{key} ({GROUPS_BY_KEY[key].label}) hat nur {n} Mitglieder, "
                f"Mindestgröße ist {MIN_GROUP_SIZE}"
            )
    for key, (alts, _note) in CONTESTED.items():
        unknown = [a for a in alts if a not in GROUPS_BY_KEY]
        if unknown:
            problems.append(f"CONTESTED[{key}] nennt unbekannte Gruppen: {unknown}")

    # Ein Override, der nichts ändert, ist irreführende Dokumentation: die
    # Firma gehört dann in CONTESTED, nicht in TICKER_OVERRIDES.
    for ticker, (target, _reason) in TICKER_OVERRIDES.items():
        rows = assigned[assigned["ticker"] == ticker]
        if rows.empty:
            continue
        default = SUB_INDUSTRY_MAP.get(rows.iloc[0]["gics_sub_industry"])
        if default == target:
            problems.append(
                f"Override {ticker} -> {target} ändert nichts (GICS-Standard ist "
                "schon diese Gruppe)"
            )
    return problems
