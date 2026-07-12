#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sorties IA Saint-Dizier & Lac du Der — robot sans IA.
Collecte des événements de Saint-Dizier et des villes à ~30 min (agendas saint-dizier.fr, lacduder.com, jds.fr), scoring par
mots-clés selon le profil pondéré, fusion avec les activités permanentes
vérifiées, puis génération de docs/metz.ics (4 activités par soir, 7 jours).

Exécuté chaque nuit par GitHub Actions. Aucune clé, aucune IA.
Usage local : python build_agenda.py [--offline]
"""

import json, re, sys, hashlib, unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

OFFLINE = "--offline" in sys.argv
RACINE = Path(__file__).parent
SORTIE = RACINE / "docs" / "der.ics"

# ------------------------------------------------- filtres (sans profil) ----
# Pas de filtrage par centres d'intérêt : on garde tout ce qui est daté,
# dans le rayon (~30 min) et sous le budget.
EXCLUSIONS = ["reims", "troyes", "chaumont", "nancy", "metz", "epernay",
              "chalons-en-champagne", "verdun", "langres", "sedan", "nogent",
              "enfant 3", "sponsorise", "annule"]
BUDGET_MAX = 50
MAX_EVENEMENTS_WEB = 8   # plafond de sécurité par soir (au-delà, tri par heure)
MIN_PAR_SOIR = 4         # complété par les activités permanentes si besoin
NB_SEMAINES = 2          # semaine en cours + semaine suivante

def sans_accents(s: str) -> str:
    return unicodedata.normalize("NFD", (s or "").lower()).encode("ascii", "ignore").decode()

def score(texte: str, permanent: bool) -> int:
    """Score /20 : proximité x1 + originalité x2 + adapté x3 + social x4 (+ véracité)."""
    t = sans_accents(texte)
    proximite = min(4, sum(p for m, p in MOTS_INTERETS.items() if m in t))
    adapte = min(2, sum(1 for m, p in MOTS_INTERETS.items() if p >= 3 and m in t))
    social = min(2, sum(1 for m in MOTS_SOCIAL if m in t))
    originalite = min(2, sum(1 for m in MOTS_ORIGINALITE if m in t) + (0 if permanent else 1))
    veracite = 2 if permanent else 1        # les permanentes sont vérifiées à la main
    total = proximite * 1 + originalite * 2 + adapte * 3 + social * 4 + veracite
    return max(6, min(20, total))

def exclu(texte: str) -> bool:
    t = sans_accents(texte)
    if any(m in t for m in EXCLUSIONS):
        return True
    prix = re.search(r"(\d+)\s*(?:€|euros)", t)
    return bool(prix and int(prix.group(1)) > BUDGET_MAX)

# ------------------------------------------------------------- collecte -----
def collecter_flux() -> list[dict]:
    """Événements datés depuis les sources web. Chaque source est optionnelle."""
    if OFFLINE:
        return []
    events, erreurs = [], []
    import requests
    from bs4 import BeautifulSoup
    UA = {"User-Agent": "AgendaIA-perso"}

    # Sources HTML : (url, base pour liens relatifs)
    SOURCES = [
        # Mairie de Saint-Dizier (agenda officiel)
        ("https://www.saint-dizier.fr/actualites-et-sorties/agenda/", "https://www.saint-dizier.fr"),
        # Office de tourisme du Lac du Der (Vitry, Montier, Éclaron, Giffaumont…)
        ("https://www.lacduder.com/sorganiser/agenda/tout-lagenda/", "https://www.lacduder.com"),
        # Agrégateur JDS
        ("https://www.jds.fr/saint-dizier/agenda/", "https://www.jds.fr"),
        # Les 3 Scènes : Les Fuseaux + Théâtre de Saint-Dizier + La Forgerie (Wassy)
        ("https://les3scenes.saint-dizier.fr/", "https://les3scenes.saint-dizier.fr"),
        # Agenda Culturel 52 : fiches datées Fuseaux et Théâtre
        ("https://52.agendaculturel.fr/les-fuseaux", "https://52.agendaculturel.fr"),
        ("https://52.agendaculturel.fr/theatre/saint-dizier/", "https://52.agendaculturel.fr"),
        # Alentoor : agrège aussi les concerts et soirées des bars locaux
        ("https://www.alentoor.fr/saint-dizier/agenda", "https://www.alentoor.fr"),
    ]
    for url, base in SOURCES:
        try:
            html = requests.get(url, timeout=20, headers=UA).text
            soup = BeautifulSoup(html, "html.parser")
            vus = set()
            for a in soup.find_all("a", href=True):
                titre = a.get_text(" ", strip=True)
                if not titre or len(titre) < 8 or titre in vus:
                    continue
                parent = a.find_parent()
                bloc = parent.get_text(" ", strip=True)[:400] if parent else titre
                d = extraire_date(bloc)
                if not d or exclu(bloc):
                    continue
                vus.add(titre)
                h = re.search(r"\b(\d{1,2})\s*h\s*(\d{2})?\b", sans_accents(bloc))
                start = f"{int(h.group(1)):02d}:{h.group(2) or '00'}" if h else None
                href = a["href"]
                lien = href if href.startswith("http") else base + href
                events.append({
                    "name": titre[:80], "date": d, "start": start, "end": None,
                    "place": "Voir fiche (Saint-Dizier / Lac du Der)", "address": "",
                    "url": lien, "price": "voir fiche", "permanent": False,
                    "verify": start is None,
                    "why": f"Événement daté repéré sur {base.split('//')[1]} — recouper l'horaire sur la fiche.",
                })
        except Exception as ex:
            erreurs.append(f"{base}: {ex}")

    if erreurs:
        print("Sources en échec (non bloquant):", "; ".join(erreurs))
    return events

MOIS_FR = {m: i + 1 for i, m in enumerate(
    ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
     "aout", "septembre", "octobre", "novembre", "decembre"])}

def extraire_date(texte: str):
    """Trouve une date française (ex: '17 juillet' ou '17/07/2026') dans un texte."""
    t = sans_accents(texte)
    auj = date.today()
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MOIS_FR) + r")(?:\s+(\d{4}))?", t)
    if m:
        j, mois = int(m.group(1)), MOIS_FR[m.group(2)]
        annee = int(m.group(3)) if m.group(3) else auj.year
        try:
            d = date(annee, mois, j)
            return d if d >= auj else None
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return d if d >= auj else None
        except ValueError:
            return None
    return None

def evenement_depuis_article(e, d, texte) -> dict:
    h = re.search(r"\b(\d{1,2})h(\d{2})?\b", sans_accents(texte))
    start = f"{int(h.group(1)):02d}:{h.group(2) or '00'}" if h else None
    return {"name": e.get("title", "Événement")[:80], "date": d,
            "start": start, "end": None,
            "place": "Metz", "address": "57000 Metz", "url": e.get("link", ""),
            "price": "voir article", "permanent": False,
            "verify": start is None,
            "why": "Repéré via tout-metz.com — recouper l'horaire sur l'article."}

# ------------------------------------------------------- planification ------
def charger_permanentes() -> list[dict]:
    data = json.loads((RACINE / "activites_permanentes.json").read_text(encoding="utf-8"))
    return data["activites"]

def cadrer_horaire(start: str, end: str, jour: date):
    """Retourne (start, end) décalés au seuil (17h30 semaine / 8h week-end), ou None si impossible."""
    limite = "08:00" if jour.weekday() >= 5 else "17:30"
    start, end = start or "20:00", end or None
    if start >= limite:
        return start, end
    if end and end > limite:
        return limite, end
    return None

def planifier(events_web: list[dict]) -> dict[date, list[dict]]:
    """Exhaustif : TOUS les événements web datés du jour (jusqu'à
    MAX_EVENEMENTS_WEB, triés par heure). Les activités permanentes ne font
    que compléter jusqu'à MIN_PAR_SOIR, sans répétition dans la semaine."""
    lundi = date.today() - timedelta(days=date.today().weekday())
    permanentes = charger_permanentes()
    planning: dict[date, list[dict]] = {}

    for s_ in range(NB_SEMAINES):
        jours = [lundi + timedelta(days=7 * s_ + i) for i in range(7)]
        deja_utilise: set[str] = set()

        # 1. Tous les événements web du jour
        for jour in jours:
            retenus, noms = [], set()
            for ev in sorted([e for e in events_web if e["date"] == jour],
                             key=lambda e: e["start"] or "20:00"):
                if ev["name"] in noms:
                    continue
                cadre = cadrer_horaire(ev["start"], ev["end"], jour)
                if not cadre:
                    continue
                retenus.append({**ev, "start": cadre[0], "end": cadre[1] or "22:00"})
                noms.add(ev["name"])
                if len(retenus) >= MAX_EVENEMENTS_WEB:
                    break
            planning[jour] = retenus

        # 2. Compléter les soirs creux avec les permanentes (round-robin)
        for _passe in range(MIN_PAR_SOIR):
            for jour in jours:
                if len(planning[jour]) >= MIN_PAR_SOIR:
                    continue
                noms_du_jour = {e["name"] for e in planning[jour]}
                for p in permanentes:
                    if (jour.weekday() not in p["days"] or p["name"] in deja_utilise
                            or p["name"] in noms_du_jour):
                        continue
                    if p.get("from") and jour.isoformat() < p["from"]:
                        continue
                    if p.get("to") and jour.isoformat() > p["to"]:
                        continue
                    cadre = cadrer_horaire(p["start"], p.get("end"), jour)
                    if not cadre:
                        continue
                    planning[jour].append({**p, "date": jour, "start": cadre[0],
                                           "end": cadre[1] or cadre[0], "permanent": True})
                    deja_utilise.add(p["name"])
                    break

    return {j: sorted(evts, key=lambda c: c["start"]) for j, evts in planning.items()}

# ---------------------------------------------------------------- ICS -------
def esc(s: str) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

VTZ = """BEGIN:VTIMEZONE\r\nTZID:Europe/Paris\r\nBEGIN:DAYLIGHT\r\nTZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\nTZNAME:CEST\r\nDTSTART:19700329T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\nEND:DAYLIGHT\r\nBEGIN:STANDARD\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\nTZNAME:CET\r\nDTSTART:19701025T030000\r\nRRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\nEND:STANDARD\r\nEND:VTIMEZONE"""

def generer_ics(planning: dict[date, list[dict]]) -> str:
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DerSortiesIA-robot//FR",
         "CALSCALE:GREGORIAN", "X-WR-CALNAME:IA Der", "X-WR-TIMEZONE:Europe/Paris",
         "X-APPLE-CALENDAR-COLOR:#007AFF", VTZ]
    from datetime import timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for jour, evts in planning.items():
        ymd = jour.strftime("%Y%m%d")
        for i, ev in enumerate(evts, 1):
            hm = lambda t: t.replace(":", "") + "00"
            fin = ev["end"] if ev.get("end") and ev["end"] > ev["start"] else ev["start"]
            desc = (f"Budget : {ev.get('price','?')}\n"
                    f"{ev.get('why','')}\n{ev.get('url','')}")
            L += ["BEGIN:VEVENT",
                  f"UID:der-ia-{ymd}-{i}@gengiscard.github.io",
                  f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID=Europe/Paris:{ymd}T{hm(ev['start'])}",
                  f"DTEND;TZID=Europe/Paris:{ymd}T{hm(fin)}",
                  f"SUMMARY:{esc(ev['name'])}{' (À CONFIRMER)' if ev.get('verify') else ''}",
                  f"LOCATION:{esc(', '.join(filter(None, [ev.get('place'), ev.get('address')])))}",
                  f"DESCRIPTION:{esc(desc)}"]
            if ev.get("url"):
                L.append(f"URL:{ev['url']}")
            L += ["CATEGORIES:IA", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"

# ---------------------------------------------------------------- main ------
if __name__ == "__main__":
    events_web = collecter_flux()
    print(f"{len(events_web)} événement(s) daté(s) collecté(s) sur le web.")
    planning = planifier(events_web)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(generer_ics(planning), encoding="utf-8")
    total = sum(len(v) for v in planning.values())
    print(f"OK — {total} activités écrites dans {SORTIE}")
    for jour, evts in planning.items():
        print(" ", jour.strftime("%a %d/%m"), "→", " | ".join(f"{e['start']} {e['name'][:44]}" for e in evts))
    
