# -*- coding: utf-8 -*-
# DraveGoedNieuws - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""bronnen.py - goed nieuws ophalen uit open RSS-feeds.

Nederlands: NU.nl Goed nieuws, Goednieuws.nl en NOS Opmerkelijk (met een doemfilter).
Engels: Good News Network, Positive News, Reasons to be Cheerful, The Optimist Daily (kan vertaald worden).
"""
import email.utils
import hashlib
import html
import json
import os
import re
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET

AGENT = "DraveGoedNieuws/0.1 (Dravenlock; persoonlijk gebruik)"

BRONNEN = [
    # sleutel, naam, url, taal, filter (True = alleen doorlaten wat door het doemfilter komt)
    ("goednieuws", "Goednieuws.nl", "https://www.goednieuws.nl/feed/", "nl", False),
    ("nu", "NU.nl Goed nieuws", "https://www.nu.nl/rss/Goed-Nieuws", "nl", False),
    ("nos", "NOS Opmerkelijk", "https://feeds.nos.nl/nosnieuwsopmerkelijk", "nl", True),
    ("gnn", "Good News Network", "https://www.goodnewsnetwork.org/feed/", "en", False),
    ("positive", "Positive News", "https://www.positive.news/feed/", "en", False),
    ("cheerful", "Reasons to be Cheerful", "https://reasonstobecheerful.world/feed/", "en", False),
    ("optimist", "The Optimist Daily", "https://www.optimistdaily.com/feed/", "en", False),
]

# Doemfilter voor het gewone nieuws: een bericht met een van deze woorden komt er nooit door.
DOEM = ("oorlog", "dood", "doden", "dode", "overleden", "omgekomen", "gedood", "moord", "vermoord", "steek", "schiet",
        "beschoten", "aanslag", "terreur", "explosie", "bom", "brand", "ramp", "crash", "ongeluk", "gewond", "slachtoffer",
        "misbruik", "verkracht", "aangehouden", "arrestatie", "verdachte", "celstraf", "rechter", "rechtszaak", "fraude",
        "oplichting", "crisis", "tekort", "ontslag", "faillissement", "failliet", "bezuinig", "staking", "protest",
        "rellen", "geweld", "raket", "drone", "leger", "militair", "gijzel", "vermist", "ziekte", "virus", "kanker",
        "zelfmoord", "vermissing", "vast in", "cel", "ms", "raadsel", "wrak", "honger", "vluchteling", "inval", "bedreig", "hack", "datalek", "storing", "noodweer", "overstroming",
        "aardbeving", "hitte", "droogte", "inflatie", "duurder", "boete", "waarschuw", "zorgen", "angst", "trump",
        "poetin", "israël", "gaza", "oekraïne", "rusland", "iran", "hamas", "stikstof", "sanctie", "verlies",
        "vogelgriep", "geruimd", "ruimen", "miljardair", "rijkste", "vertrek", "hypotheek", "fundering", "uitstoot",
        "stoot", "schuld", "armoede", "dakloos", "politie", "justitie", "kabinet", "minister", "verkiezing", "partij",
        "beurs", "aandeel", "koers", "prijs", "kosten", "belasting", "ziek", "pijn", "letsel", "gevaar", "risico",
        "niet mee", "weigert", "stopt", "verdwijnt", "sluit", "dicht", "probleem", "klacht", "kritiek", "ruzie")
# ...en het moet minstens één van deze vrolijke woorden hebben.
GOED = ("gered", "redding", "geboren", "baby", "jarig", "jubileum", "feest", "viert", "record", "gewonnen", "winnaar",
        "kampioen", "goud", "medaille", "ontdekt", "ontdekking", "uitvinding", "doorbraak", "geopend", "opening", "nieuw park",
        "natuur", "dieren", "dier", "hond", "kat", "vogel", "zeehond", "bever", "otter", "ooievaar", "panda", "olifant",
        "vrijwilliger", "helpt", "helpen", "hulp", "cadeau", "vriendschap", "liefde", "trouwen", "getrouwd", "hereniging",
        "herenigd", "terug na", "teruggevonden", "hersteld", "herstel", "genezen", "beter", "schoner", "groener", "zonne",
        "bomen", "bos", "planten", "tuin", "museum", "concert", "muziek", "kunst", "festival", "sinterklaas", "kerst",
        "100 jaar", "honderd", "eerste keer", "voor het eerst", "succes", "lukt", "geslaagd", "dank", "bedankt", "glimlach",
        "vrolijk", "blij", "mooi", "prachtig", "bijzonder", "unieke", "noorderlicht", "sterren", "ruimte", "maan")


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL = _ctx()


def haal(url, tijd=20):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/rss+xml, application/xml, */*"})
    with urllib.request.urlopen(req, timeout=tijd, context=SSL) as r:
        return r.read()


def schoon(t):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t or "", flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"The post .{0,200} appeared first on .{0,80}\.?$", "", t.strip(), flags=re.S)
    t = re.sub(r"\[(…|\.\.\.)\]|Continue reading.*$|Lees verder.*$", "", t, flags=re.S)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def kort(t, n=700):
    if len(t) <= n:
        return t
    stuk = t[:n]
    eind = max(stuk.rfind(". "), stuk.rfind("! "), stuk.rfind("? "))
    return (stuk[:eind + 1] if eind > n * 0.4 else stuk.rsplit(" ", 1)[0] + "...").strip()


def _tijd(s):
    try:
        return email.utils.parsedate_to_datetime(s).timestamp()
    except Exception:
        return time.time()


def _plaatje(it, inhoud):
    ns = {"media": "http://search.yahoo.com/mrss/"}
    for tag in ("media:content", "media:thumbnail"):
        for m in it.findall(tag, ns):
            u = m.get("url")
            if u and (m.get("medium") in (None, "image") or re.search(r"\.(jpe?g|png|webp)", u, re.I)):
                return u
    enc = it.find("enclosure")
    if enc is not None and (enc.get("type") or "").startswith("image"):
        return enc.get("url")
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)", inhoud or "")
    return m.group(1) if m else ""


DOEM_RX = re.compile(r"\b(" + "|".join(re.escape(w) for w in DOEM) + ")", re.I)
GOED_RX = re.compile(r"\b(" + "|".join(re.escape(w) for w in GOED) + ")", re.I)


def og_plaatje(url):
    """Het hoofdplaatje van een artikel (og:image), voor berichten waar de feed er geen bij geeft."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 " + AGENT})
        with urllib.request.urlopen(req, timeout=12, context=SSL) as r:
            kop = r.read(300000).decode("utf-8", "replace")
        m = re.search(r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)', kop) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image', kop)
        return html.unescape(m.group(1)) if m else ""
    except Exception:
        return ""


def is_goed(titel, tekst, streng=False):
    """Geen enkel doemwoord (begin van een woord) in kop of tekst. Streng: ook een vrolijk woord in de kop."""
    if DOEM_RX.search(titel + " " + tekst):
        return False
    return bool(GOED_RX.search(titel)) if streng else True


def lees_feed(bron):
    sleutel, naam, url, taal, filter_ = bron
    wortel = ET.fromstring(haal(url))
    uit = []
    for it in wortel.iter("item"):
        titel = schoon(it.findtext("title") or "")
        link = (it.findtext("link") or "").strip()
        inhoud = it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
        samen = schoon(it.findtext("description") or "") or schoon(inhoud)
        if len(samen) < 160 and inhoud:
            meer = schoon(inhoud)
            if len(meer) > len(samen):
                samen = meer
        if not titel or not link:
            continue
        if filter_ and not is_goed(titel, samen):
            continue
        uit.append(dict(id=hashlib.md5(link.encode()).hexdigest()[:16], bron=sleutel, bronnaam=naam, taal=taal,
                        titel=titel, tekst=kort(samen), link=link, plaatje=_plaatje(it, inhoud),
                        tijd=_tijd(it.findtext("pubDate") or "")))
    return uit


def haal_alles(cache_map, bronnen=None, melden=None):
    """Alle bronnen ophalen. Lukt een bron niet, dan wordt de vorige keer gebruikt (uit de cache)."""
    os.makedirs(cache_map, exist_ok=True)
    alles, fout = [], []
    for b in BRONNEN:
        if bronnen is not None and b[0] not in bronnen:
            continue
        pad = os.path.join(cache_map, "bron_%s.json" % b[0])
        try:
            lijst = lees_feed(b)
            with open(pad, "w", encoding="utf-8") as f:
                json.dump(lijst, f, ensure_ascii=False)
        except Exception as e:
            fout.append(b[1])
            try:
                with open(pad, encoding="utf-8") as f:
                    lijst = json.load(f)
            except Exception:
                lijst = []
        alles += lijst
        if melden:
            melden(b[1])
    gezien, uniek = set(), []
    for a in sorted(alles, key=lambda a: -a["tijd"]):
        k = a["titel"].lower()[:60]
        if k not in gezien:
            gezien.add(k)
            uniek.append(a)
    return uniek, fout
