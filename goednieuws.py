# -*- coding: utf-8 -*-
# DraveGoedNieuws - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""goednieuws.py - DraveGoedNieuws: alleen nieuws waar je blij van wordt, groot en duidelijk, en Leon leest het voor.

Bronnen: NU.nl Goed nieuws, Goednieuws.nl, NOS Opmerkelijk (met doemfilter), en Engelse goed-nieuwssites
(Good News Network, Positive News, Reasons to be Cheerful, The Optimist Daily), die je op je eigen pc kunt laten vertalen.
"""
import json
import os
import sys
import threading
import time

from PyQt6.QtCore import QObject, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QSizePolicy,
                             QListWidgetItem, QMainWindow, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget)

import bronnen
import leon
import vertaal

VERSIE = "0.1"
NAAM = "DraveGoedNieuws"


def app_map():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def bron_map():
    return getattr(sys, "_MEIPASS", app_map())


DATA = os.path.join(app_map(), "DraveGoedNieuws-data")          # naast de app (dus op D:, niet op C:)
os.makedirs(DATA, exist_ok=True)

KLEUR = dict(nl="#46c86e", en="#5aa0ff")


def stijl(f):
    """Stylesheet met tekstgrootte-factor f (1.0 = normaal)."""
    p = lambda n: "%dpt" % round(n * f)
    vink = os.path.join(bron_map(), "assets", "vink.svg").replace("\\", "/")
    return """
* { font-family: 'Segoe UI'; color: #e2e2ec; }
QMainWindow, QWidget#basis, QDialog, QScrollArea, QWidget#lezer { background: #0a0810; }
QLabel#titel { font-size: %(t)s; font-weight: 700; }
QLabel#kop { font-size: %(kop)s; font-weight: 800; color: #fafaff; }
QLabel#info { font-size: %(info)s; color: #ffde3c; }
QLabel#tekst { font-size: %(tekst)s; line-height: 150%%; color: #e8e6f0; }
QLabel#klein { font-size: %(klein)s; color: #9a96aa; }
QLabel#melding { background: #14301e; border: 2px solid #46c86e; border-radius: 10px; padding: 8px 12px;
                 font-size: %(klein)s; color: #c8f0d4; }
QPushButton { background: #18122a; border: 2px solid #9a5ae6; border-radius: 12px; padding: 9px 15px;
              font-size: %(knop)s; font-weight: 600; }
QPushButton:hover { border-color: #ffde3c; }
QPushButton:checked { background: #9a5ae6; color: #0a0810; border-color: #ffde3c; }
QPushButton#groot { font-size: %(groot)s; padding: 12px 20px; background: #9a5ae6; color: #0a0810; border-color: #ffde3c; }
QPushButton#rood { font-size: %(groot)s; padding: 12px 20px; background: #c83a3a; color: #ffffff; border-color: #e2e2ec; }
QComboBox { background: #fafaff; color: #0a0810; border: 3px solid #ffde3c; border-radius: 10px; padding: 7px 10px;
            font-size: %(knop)s; }
QComboBox QAbstractItemView { background: #fafaff; color: #0a0810; font-size: %(knop)s; }
QListWidget { background: #0f0b1a; border: 2px solid #46307a; border-radius: 12px; }
QListWidget::item { border-bottom: 1px solid #241a3a; }
QListWidget::item:selected { background: #2c1d50; }
QCheckBox { font-size: %(knop)s; spacing: 12px; }
QCheckBox::indicator { width: 30px; height: 30px; border: 3px solid #ffde3c; border-radius: 7px; background: #18122a; }
QCheckBox::indicator:checked { background: #ffde3c; image: url(%(vink)s); }
QProgressBar { border: 2px solid #46307a; border-radius: 8px; background: #18122a; height: 18px; text-align: center; }
QProgressBar::chunk { background: #46c86e; border-radius: 6px; }
""" % dict(t=p(26), kop=p(24), info=p(14), tekst=p(17), klein=p(12), knop=p(14), groot=p(18), vink=vink)


def wanneer(t):
    d = time.time() - t
    if d < 3600:
        return "net binnen"
    if d < 86400 and time.localtime(t).tm_mday == time.localtime().tm_mday:
        return "vandaag %s" % time.strftime("%H:%M", time.localtime(t))
    if d < 2 * 86400:
        return "gisteren"
    if d < 14 * 86400:
        return "%d dagen geleden" % int(d // 86400)
    return time.strftime("%d-%m-%Y", time.localtime(t))


def groet():
    u = time.localtime().tm_hour
    return "Goedemorgen" if u < 12 else ("Goedemiddag" if u < 18 else "Goedenavond")


class Signalen(QObject):
    nieuws = pyqtSignal(object, object)
    stap = pyqtSignal(str)
    vertaald = pyqtSignal(str)
    model = pyqtSignal(float)
    model_klaar = pyqtSignal(bool)
    geluid = pyqtSignal(int, str)          # nummer van de beurt, pad (leeg = klaar)
    plaatje = pyqtSignal(str, str)         # bericht-id, url


class Kaart(QWidget):
    """Een bericht in de lijst: plaatje, bron, kop en het begin van de tekst."""

    def __init__(self, a, f, kop, tekst):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(12)
        self.plaat = QLabel()
        self.plaat.setFixedSize(round(132 * f), round(88 * f))
        self.plaat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plaat.setStyleSheet("background: #1c1530; border-radius: 10px; font-size: %dpt;" % round(26 * f))
        self.plaat.setText("☀")
        lay.addWidget(self.plaat, 0, Qt.AlignmentFlag.AlignTop)
        tl = QVBoxLayout()
        tl.setSpacing(4)
        tl.setAlignment(Qt.AlignmentFlag.AlignTop)
        boven = QHBoxLayout()
        b = QLabel(a["bronnaam"])
        b.setStyleSheet("color: #0a0810; background: %s; border-radius: 6px; padding: 1px 8px; font-size: %dpt; font-weight: 700;"
                        % (KLEUR.get(a["taal"], "#9a5ae6"), round(10 * f)))
        b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        boven.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        w = QLabel(wanneer(a["tijd"]))
        w.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        w.setStyleSheet("color: #9a96aa; font-size: %dpt;" % round(11 * f))
        boven.addWidget(w)
        boven.addStretch(1)
        tl.addLayout(boven)
        self.kop = QLabel(kop)
        self.kop.setWordWrap(True)
        self.kop.setMinimumWidth(10)
        self.kop.setStyleSheet("font-size: %dpt; font-weight: 700;" % round(15 * f))
        tl.addWidget(self.kop)
        self.tekst = QLabel(tekst[:150] + ("..." if len(tekst) > 150 else ""))
        self.tekst.setVisible(bool(tekst))
        self.tekst.setWordWrap(True)
        self.tekst.setMinimumWidth(10)
        self.tekst.setStyleSheet("color: #b8b4c8; font-size: %dpt;" % round(12 * f))
        tl.addWidget(self.tekst)
        lay.addLayout(tl, 1)


class Venster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(NAAM)
        ico = os.path.join(bron_map(), "assets", "icon.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        self.inst = {"vertalen": True, "groot": 1.0, "filter": "alles", "bewaard": [], "gelezen": [], "gevraagd": False}
        try:
            with open(os.path.join(DATA, "instellingen.json"), encoding="utf-8") as f:
                self.inst.update(json.load(f))
        except Exception:
            pass
        self.sig = Signalen()
        self.sig.nieuws.connect(self.nieuws_binnen)
        self.sig.stap.connect(lambda t: self.status.setText("Ophalen: %s..." % t))
        self.sig.vertaald.connect(self.vertaling_binnen)
        self.sig.model.connect(lambda x: (self.voortgang.show(), self.voortgang.setValue(int(x * 100))))
        self.sig.model_klaar.connect(self.model_klaar)
        self.sig.geluid.connect(self.geluid_binnen)
        self.sig.plaatje.connect(self.og_binnen)
        self.vt = vertaal.Vertaler(DATA)
        self.net = QNetworkAccessManager(self)
        self.plaat_cache, self.plaat_wacht = {}, {}
        self.alles, self.zicht, self.nu = [], [], None
        self.toon_origineel = set()
        self.beurt = 0                 # elke nieuwe voorleesopdracht krijgt een nummer; oude geluiden worden genegeerd
        self.rij, self.radio, self.radio_i = [], False, 0
        self.wacht_op = 0

        basis = QWidget()
        basis.setObjectName("basis")
        self.setCentralWidget(basis)
        hoofd = QVBoxLayout(basis)
        hoofd.setContentsMargins(18, 14, 18, 12)
        boven = QHBoxLayout()
        logo = QLabel()
        png = os.path.join(bron_map(), "assets", "logo.png")
        if os.path.exists(png):
            logo.setPixmap(QPixmap(png).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        boven.addWidget(logo)
        self.titel = QLabel(NAAM)
        self.titel.setObjectName("titel")
        boven.addWidget(self.titel)
        boven.addStretch(1)
        self.radioknop = QPushButton("📻  Lees alles voor")
        self.radioknop.setObjectName("groot")
        self.radioknop.clicked.connect(self.wissel_radio)
        boven.addWidget(self.radioknop)
        self.ververs = QPushButton("⟳  Vernieuwen")
        self.ververs.clicked.connect(self.haal)
        boven.addWidget(self.ververs)
        kl = QPushButton("A−")
        kl.setToolTip("Tekst kleiner")
        kl.clicked.connect(lambda: self.zet_groot(-0.1))
        boven.addWidget(kl)
        gr = QPushButton("A+")
        gr.setToolTip("Tekst groter")
        gr.clicked.connect(lambda: self.zet_groot(0.1))
        boven.addWidget(gr)
        hoofd.addLayout(boven)

        rij2 = QHBoxLayout()
        self.filter = QComboBox()
        for code, naam in (("alles", "Al het goede nieuws"), ("nl", "Uit Nederland"), ("en", "Uit de wereld"),
                           ("bewaard", "★ Bewaard")):
            self.filter.addItem(naam, code)
        self.filter.setCurrentIndex(max(0, self.filter.findData(self.inst.get("filter", "alles"))))
        self.filter.currentIndexChanged.connect(self.toon_lijst)
        rij2.addWidget(self.filter, 2)
        self.vertaalvak = QCheckBox("Berichten uit de wereld vertalen naar het Nederlands")
        self.vertaalvak.setChecked(self.inst.get("vertalen", True))
        self.vertaalvak.toggled.connect(self.zet_vertalen)
        rij2.addWidget(self.vertaalvak, 3)
        hoofd.addLayout(rij2)
        self.voortgang = QProgressBar()
        self.voortgang.setFormat("Vertaalmodel downloaden: %p%")
        self.voortgang.hide()
        hoofd.addWidget(self.voortgang)

        midden = QHBoxLayout()
        self.lijst = QListWidget()
        self.lijst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lijst.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.lijst.currentRowChanged.connect(self.kies)
        midden.addWidget(self.lijst, 5)
        # lezer rechts
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: 2px solid #46307a; border-radius: 12px; }")
        lezer = QWidget()
        lezer.setObjectName("lezer")
        ll = QVBoxLayout(lezer)
        ll.setContentsMargins(18, 16, 18, 16)
        ll.setSpacing(12)
        self.grootplaat = QLabel()
        self.grootplaat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grootplaat.setFixedHeight(320)
        self.grootplaat.setStyleSheet("background: #120d20; border-radius: 14px; font-size: 72pt;")
        self.grootplaat.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.grootplaat.setText("☀")
        ll.addWidget(self.grootplaat)
        self.kop = QLabel("Kies een bericht")
        self.kop.setObjectName("kop")
        self.kop.setWordWrap(True)
        ll.addWidget(self.kop)
        self.info = QLabel("")
        self.info.setObjectName("info")
        self.info.setWordWrap(True)
        ll.addWidget(self.info)
        knoppen = QHBoxLayout()
        self.leesknop = QPushButton("▶  Lees voor")
        self.leesknop.setObjectName("groot")
        self.leesknop.clicked.connect(self.lees_stop)
        knoppen.addWidget(self.leesknop, 2)
        self.origknop = QPushButton("🔤 Origineel")
        self.origknop.setToolTip("Wisselen tussen de vertaling en de Engelse tekst")
        self.origknop.clicked.connect(self.wissel_origineel)
        knoppen.addWidget(self.origknop, 1)
        self.bewaarknop = QPushButton("☆ Bewaren")
        self.bewaarknop.clicked.connect(self.wissel_bewaar)
        knoppen.addWidget(self.bewaarknop, 1)
        self.siteknop = QPushButton("🌐 Hele artikel")
        self.siteknop.setToolTip("Open het hele artikel op de website")
        self.siteknop.clicked.connect(lambda: self.nu and QDesktopServices.openUrl(QUrl(self.nu["link"])))
        knoppen.addWidget(self.siteknop, 1)
        ll.addLayout(knoppen)
        self.tekst = QLabel("")
        self.tekst.setObjectName("tekst")
        self.tekst.setWordWrap(True)
        self.tekst.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.tekst.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        ll.addWidget(self.tekst)
        ll.addStretch(1)
        self.scroll.setWidget(lezer)
        midden.addWidget(self.scroll, 6)
        hoofd.addLayout(midden, 1)
        self.melding = QLabel("")
        self.melding.setObjectName("melding")
        self.melding.setWordWrap(True)
        self.melding.hide()
        hoofd.addWidget(self.melding)
        self.status = QLabel("")
        self.status.setObjectName("klein")
        hoofd.addWidget(self.status)
        voet = QLabel("Bronnen: NU.nl · Goednieuws.nl · NOS · Good News Network · Positive News · Reasons to be Cheerful · "
                      "The Optimist Daily  ·  Stem: Leon  ·  %s %s - Dravenlock (Roger & Claudio)" % (NAAM, VERSIE))
        voet.setObjectName("klein")
        voet.setWordWrap(True)
        hoofd.addWidget(voet)

        self.uit = QAudioOutput()
        self.uit.setVolume(1.0)
        self.speler = QMediaPlayer()
        self.speler.setAudioOutput(self.uit)
        self.speler.mediaStatusChanged.connect(self.speler_status)
        self.resize(1500, 920)
        self.pas_stijl()
        self.knoppen_bij()
        QTimer.singleShot(200, self.haal)
        self.klok = QTimer(self)
        self.klok.timeout.connect(self.haal)
        self.klok.start(30 * 60 * 1000)                 # elk half uur vanzelf vernieuwen

    # ------------------------------------------------------------ algemeen
    def bewaar(self):
        try:
            with open(os.path.join(DATA, "instellingen.json"), "w", encoding="utf-8") as f:
                json.dump(self.inst, f, ensure_ascii=False)
        except Exception:
            pass

    def pas_stijl(self):
        QApplication.instance().setStyleSheet(stijl(self.inst["groot"]))

    def zet_groot(self, d):
        self.inst["groot"] = round(min(1.8, max(0.8, self.inst["groot"] + d)), 2)
        self.bewaar()
        self.pas_stijl()
        self.toon_lijst()
        self.status.setText("Tekstgrootte: %d%%" % round(self.inst["groot"] * 100))

    def meld(self, t, sec=8):
        self.melding.setText(t)
        self.melding.show()
        QTimer.singleShot(sec * 1000, self.melding.hide)

    # ------------------------------------------------------------ nieuws
    def haal(self):
        self.ververs.setEnabled(False)
        self.status.setText("Het goede nieuws wordt opgehaald...")
        threading.Thread(target=self._haal, daemon=True).start()

    def _haal(self):
        try:
            alles, fout = bronnen.haal_alles(os.path.join(DATA, "cache"), melden=self.sig.stap.emit)
        except Exception:
            alles, fout = [], ["alle bronnen"]
        self.sig.nieuws.emit(alles, fout)

    def nieuws_binnen(self, alles, fout):
        self.ververs.setEnabled(True)
        self.alles = alles
        n = len(alles)
        self.status.setText("%d berichten. Klik op een bericht om het te lezen." % n if n else "Geen nieuws gevonden. Is er internet?")
        if fout:
            self.meld("Niet bereikbaar: %s. Daarvan zie je het nieuws van de vorige keer." % ", ".join(fout))
        self.toon_lijst()
        zonder = [a for a in alles if not a.get("plaatje")][:40]
        for a in zonder:
            a["_og"] = True
        threading.Thread(target=lambda: [self.sig.plaatje.emit(a["id"], bronnen.og_plaatje(a["link"])) for a in zonder],
                         daemon=True).start()
        if self.inst.get("vertalen") and any(a["taal"] == "en" for a in alles):
            self.start_vertalen()

    def tekst_van(self, a):
        """(kop, tekst, taal) zoals hij getoond en voorgelezen wordt."""
        if a["taal"] == "en" and self.inst.get("vertalen") and a["id"] not in self.toon_origineel:
            k = self.vt.cache.get(self._sl(a["titel"]))
            t = self.vt.cache.get(self._sl(a["tekst"])) if a["tekst"].strip() else ""
            if k and t is not None:
                return k, t, "nl"
        return a["titel"], a["tekst"], a["taal"]

    @staticmethod
    def _sl(t):
        import hashlib
        return hashlib.md5((t or "").strip().encode("utf-8")).hexdigest()

    def toon_lijst(self, *_):
        code = self.filter.currentData() or "alles"
        self.inst["filter"] = code
        self.bewaar()
        if code == "bewaard":
            ids = [b["id"] for b in self.inst["bewaard"]]
            bekend = {a["id"]: a for a in self.alles}
            self.zicht = [bekend.get(b["id"], b) for b in self.inst["bewaard"]]
        else:
            self.zicht = [a for a in self.alles if code == "alles" or a["taal"] == code]
        oud = self.nu["id"] if self.nu else None
        self.lijst.blockSignals(True)
        self.lijst.clear()
        f = self.inst["groot"]
        kies = -1
        for i, a in enumerate(self.zicht):
            kop, tekst, _ = self.tekst_van(a)
            it = QListWidgetItem()
            k = Kaart(a, f, kop, tekst)
            self.lijst.addItem(it)
            self.lijst.setItemWidget(it, k)
            self.maat(it, k)
            if a.get("plaatje"):
                self.laad_plaat(a["plaatje"], k.plaat, 132 * f, 88 * f)
            if a["id"] == oud:
                kies = i
        self.lijst.blockSignals(False)
        if not self.zicht:
            self.status.setText("Nog niets bewaard: klik op ☆ Bewaren bij een bericht." if code == "bewaard" else
                                "Geen berichten.")
        if kies >= 0:
            self.lijst.setCurrentRow(kies)
        elif self.zicht and not self.radio:
            self.lijst.setCurrentRow(0)

    def maat(self, it, k):
        b = max(300, self.lijst.viewport().width() - 6)
        k.resize(b, 10)
        h = k.layout().totalHeightForWidth(b) if k.layout().hasHeightForWidth() else k.sizeHint().height()
        it.setSizeHint(QSize(b, max(h, k.plaat.height() + 20)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self)
            self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._herschaal)
        self._rt.start(250)

    def _herschaal(self):
        for i in range(self.lijst.count()):
            it = self.lijst.item(i)
            k = self.lijst.itemWidget(it)
            if k:
                self.maat(it, k)
        if self.nu and self.nu.get("plaatje"):
            self.laad_plaat(self.nu["plaatje"], self.grootplaat, max(300, self.grootplaat.width()), 320)
        self.hoogtes()

    def kies(self, rij):
        if not (0 <= rij < len(self.zicht)):
            return
        a = self.zicht[rij]
        if not self.radio and self.nu is not a:
            self.stop_lezen()
        self.nu = a
        self.toon_bericht()

    def toon_bericht(self):
        a = self.nu
        if not a:
            return
        kop, tekst, taal = self.tekst_van(a)
        self.kop.setText(kop)
        vertaald = a["taal"] == "en" and taal == "nl"
        extra = "  ·  vertaald uit het Engels" if vertaald else ("  ·  Engelstalig" if a["taal"] == "en" else "")
        self.info.setText("%s  ·  %s%s" % (a["bronnaam"], wanneer(a["tijd"]), extra))
        self.tekst.setText(tekst + "\n\nWil je meer lezen? Klik op 🌐 Hele artikel.")
        self.grootplaat.setPixmap(QPixmap())
        self.grootplaat.setText("☀")
        if a.get("plaatje"):
            self.laad_plaat(a["plaatje"], self.grootplaat, max(300, self.grootplaat.width()), 320)
        elif not a.get("_og"):
            a["_og"] = True
            threading.Thread(target=lambda: self.sig.plaatje.emit(a["id"], bronnen.og_plaatje(a["link"])), daemon=True).start()
        self.knoppen_bij()
        self.hoogtes()
        self.scroll.verticalScrollBar().setValue(0)

    def hoogtes(self):
        """Lange koppen en teksten krijgen hun volle hoogte (anders knipt Qt ze soms af)."""
        b = max(200, self.scroll.viewport().width() - 40)
        for lb in (self.kop, self.info, self.tekst):
            lb.setMinimumHeight(lb.heightForWidth(b))

    def og_binnen(self, aid, url):
        if not url:
            return
        for i, a in enumerate(self.zicht):
            if a["id"] == aid:
                a["plaatje"] = url
                it = self.lijst.item(i)
                k = self.lijst.itemWidget(it) if it else None
                if k:
                    f = self.inst["groot"]
                    self.laad_plaat(url, k.plaat, 132 * f, 88 * f)
                if self.nu is a:
                    self.laad_plaat(url, self.grootplaat, max(300, self.grootplaat.width()), 320)
                break

    def knoppen_bij(self):
        a = self.nu
        en = bool(a) and a["taal"] == "en" and self.inst.get("vertalen")
        self.origknop.setVisible(en)
        if a:
            self.origknop.setText("🔤 Vertaling" if a["id"] in self.toon_origineel else "🔤 Origineel")
            self.bewaarknop.setText("★ Bewaard" if any(b["id"] == a["id"] for b in self.inst["bewaard"]) else "☆ Bewaren")
        bezig = self.speler.playbackState() == QMediaPlayer.PlaybackState.PlayingState or self.wacht_op
        self.leesknop.setText("■  Stop" if bezig and not self.radio else "▶  Lees voor")
        self.leesknop.setObjectName("rood" if bezig and not self.radio else "groot")
        self.leesknop.setStyle(self.leesknop.style())
        self.radioknop.setText("■  Stop" if self.radio else "📻  Lees alles voor")
        self.radioknop.setObjectName("rood" if self.radio else "groot")
        self.radioknop.setStyle(self.radioknop.style())

    def wissel_origineel(self):
        if not self.nu:
            return
        self.toon_origineel ^= {self.nu["id"]}
        self.stop_lezen()
        self.toon_bericht()
        rij = self.lijst.currentRow()
        it = self.lijst.item(rij)
        if it:
            k = self.lijst.itemWidget(it)
            kop, tekst, _ = self.tekst_van(self.nu)
            k.kop.setText(kop)
            k.tekst.setText(tekst[:150] + ("..." if len(tekst) > 150 else ""))

    def wissel_bewaar(self):
        a = self.nu
        if not a:
            return
        if any(b["id"] == a["id"] for b in self.inst["bewaard"]):
            self.inst["bewaard"] = [b for b in self.inst["bewaard"] if b["id"] != a["id"]]
        else:
            self.inst["bewaard"].insert(0, dict(a))
        self.bewaar()
        self.knoppen_bij()
        if self.filter.currentData() == "bewaard":
            self.toon_lijst()

    # ------------------------------------------------------------ plaatjes
    def laad_plaat(self, url, label, w, h):
        w, h = int(w), int(h)
        if url in self.plaat_cache:
            pm = self.plaat_cache[url]
            if pm:
                self._zet_plaat(label, pm, w, h)
            return
        self.plaat_wacht.setdefault(url, []).append((label, w, h))
        if len(self.plaat_wacht[url]) > 1:
            return
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, bronnen.AGENT)
        antw = self.net.get(req)
        antw.finished.connect(lambda a=antw, u=url: self.plaat_binnen(a, u))

    def plaat_binnen(self, antw, url):
        pm = QPixmap()
        ok = pm.loadFromData(bytes(antw.readAll()))
        antw.deleteLater()
        if ok and pm.width() > 900:
            pm = pm.scaledToWidth(900, Qt.TransformationMode.SmoothTransformation)
        self.plaat_cache[url] = pm if ok else None
        for label, w, h in self.plaat_wacht.pop(url, []):
            if ok:
                self._zet_plaat(label, pm, w, h)

    @staticmethod
    def _zet_plaat(label, pm, w, h):
        try:
            # vullen en netjes bijsnijden, zodat het vakje mooi vol is
            s = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            x, y = max(0, (s.width() - w) // 2), max(0, (s.height() - h) // 2)
            label.setPixmap(s.copy(x, y, min(w, s.width()), min(h, s.height())))
        except RuntimeError:
            pass

    # ------------------------------------------------------------ vertalen
    def zet_vertalen(self, v):
        self.inst["vertalen"] = v
        self.bewaar()
        if v:
            self.start_vertalen()
        self.toon_lijst()
        self.toon_bericht()

    def start_vertalen(self):
        if not self.vt.model_aanwezig():
            if not self.inst.get("gevraagd"):
                self.vraag_model()
            return
        if getattr(self, "_vertaalt", False):
            return
        self._vertaalt = True
        threading.Thread(target=self._vertaal_alles, daemon=True).start()

    def vraag_model(self):
        self.inst["gevraagd"] = True
        self.bewaar()
        d = QDialog(self)
        d.setWindowTitle("Vertalen")
        lay = QVBoxLayout(d)
        t = QLabel("Om berichten uit de wereld naar het Nederlands te vertalen, is één keer een vertaalmodel nodig "
                   "(ongeveer 72 MB).\n\nHet komt in de map naast de app. Daarna vertaalt alles op je eigen pc, "
                   "zonder internet-AI.\n\nNu downloaden?")
        t.setWordWrap(True)
        t.setMinimumWidth(560)
        t.setStyleSheet("font-size: %dpt;" % round(15 * self.inst["groot"]))
        lay.addWidget(t)
        kn = QHBoxLayout()
        ja = QPushButton("Ja, downloaden")
        ja.setObjectName("groot")
        ja.clicked.connect(d.accept)
        nee = QPushButton("Nee, Engels laten")
        nee.clicked.connect(d.reject)
        kn.addWidget(ja)
        kn.addWidget(nee)
        lay.addLayout(kn)
        if d.exec():
            self.status.setText("Vertaalmodel downloaden...")
            threading.Thread(target=self._download, daemon=True).start()
        else:
            self.vertaalvak.setChecked(False)

    def _download(self):
        try:
            self.vt.download(self.sig.model.emit)
            self.sig.model_klaar.emit(True)
        except Exception:
            self.sig.model_klaar.emit(False)

    def model_klaar(self, ok):
        self.voortgang.hide()
        if ok:
            self.meld("Het vertaalmodel staat klaar. De berichten uit de wereld worden nu vertaald.", 6)
            self.start_vertalen()
        else:
            self.inst["gevraagd"] = False
            self.meld("Het vertaalmodel downloaden lukte niet. Probeer het later opnieuw (vinkje uit en weer aan).")

    def _vertaal_alles(self):
        try:
            # eerst wat je nu ziet, daarna de rest
            lijst = [a for a in self.zicht if a["taal"] == "en"] + [a for a in self.alles if a["taal"] == "en"]
            klaar = set()
            for a in lijst:
                if a["id"] in klaar:
                    continue
                klaar.add(a["id"])
                nieuw = self._sl(a["titel"]) not in self.vt.cache or self._sl(a["tekst"]) not in self.vt.cache
                self.vt.vertaal(a["titel"])
                self.vt.vertaal(a["tekst"])
                if nieuw:
                    self.sig.vertaald.emit(a["id"])
            self.vt.bewaar()
        finally:
            self._vertaalt = False

    def vertaling_binnen(self, aid):
        for i, a in enumerate(self.zicht):
            if a["id"] == aid:
                it = self.lijst.item(i)
                k = self.lijst.itemWidget(it) if it else None
                if k:
                    kop, tekst, _ = self.tekst_van(a)
                    k.kop.setText(kop)
                    k.tekst.setText(tekst[:150] + ("..." if len(tekst) > 150 else ""))
                    self.maat(it, k)
                if self.nu is a:
                    self.toon_bericht()
                break

    # ------------------------------------------------------------ voorlezen
    def spreek(self, stukken):
        """stukken = lijst (tekst, taal) of ('#bel', None). Leon maakt ze op de achtergrond, wij spelen ze af."""
        self.beurt += 1
        b = self.beurt
        self.rij = []
        self.wacht_op = len(stukken)
        self.speler.stop()
        threading.Thread(target=self._maak, args=(b, stukken), daemon=True).start()
        self.knoppen_bij()

    def _maak(self, b, stukken):
        for tekst, taal in stukken:
            if b != self.beurt:
                return
            if tekst == "#bel":
                pad = leon.belletje(os.path.join(DATA, "leon", "belletje.wav"))
            else:
                pad = leon.maak(tekst, os.path.join(DATA, "leon"), taal or "nl") or ""
            self.sig.geluid.emit(b, pad or "#fout")

    def geluid_binnen(self, b, pad):
        if b != self.beurt:
            return
        self.wacht_op -= 1
        if pad == "#fout":
            if leon.status == "geen":
                self.meld("Leon kan nu niet praten (de stem kon niet geladen worden).")
                self.stop_lezen()
            return
        self.rij.append(pad)
        if self.speler.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.volgende_geluid()

    def volgende_geluid(self):
        if self.rij:
            p = self.rij.pop(0)
            self.speler.setSource(QUrl.fromLocalFile(p))
            self.speler.play()
        elif not self.wacht_op:
            if self.radio:
                QTimer.singleShot(500, self.radio_volgende)
            self.knoppen_bij()

    def speler_status(self, st):
        if st in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            self.volgende_geluid()

    def stukken_van(self, a, met_bron=False):
        kop, tekst, taal = self.tekst_van(a)
        uit = []
        if met_bron:
            uit.append(("Van %s." % a["bronnaam"], "nl"))
        uit.append((kop + ".", taal))
        uit += [(z, taal) for z in leon.zinnen(tekst)]
        return uit

    def lees_stop(self):
        bezig = self.speler.playbackState() == QMediaPlayer.PlaybackState.PlayingState or self.wacht_op
        if bezig or self.radio:
            self.stop_lezen()
        elif self.nu:
            if leon.status != "klaar":
                self.status.setText("Leon maakt zich klaar, een paar tellen...")
            self.spreek(self.stukken_van(self.nu))

    def stop_lezen(self):
        self.beurt += 1
        self.rij, self.wacht_op = [], 0
        self.speler.stop()
        self.radio = False
        self.knoppen_bij()

    def wissel_radio(self):
        if self.radio:
            self.stop_lezen()
            return
        if not self.zicht:
            return
        self.stop_lezen()
        self.radio = True
        self.radio_i = max(0, self.lijst.currentRow())
        n = len(self.zicht)
        intro = [("%s! Hier is het goede nieuws. Ik heb %d vrolijke berichten voor je." % (groet(), n), "nl"), ("#bel", None)]
        self.lijst.setCurrentRow(self.radio_i)
        self.spreek(intro + self.stukken_van(self.zicht[self.radio_i], met_bron=True))

    def radio_volgende(self):
        if not self.radio:
            return
        self.radio_i += 1
        if self.radio_i >= len(self.zicht):
            self.spreek([("#bel", None), ("Dat was het goede nieuws. Fijne dag!", "nl")])
            self.radio = False
            self.knoppen_bij()
            return
        self.lijst.setCurrentRow(self.radio_i)
        self.spreek([("#bel", None)] + self.stukken_van(self.zicht[self.radio_i], met_bron=True))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self.lees_stop()
        elif e.key() == Qt.Key.Key_Escape:
            self.stop_lezen()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.stop_lezen()
        self.vt.bewaar()
        self.bewaar()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(NAAM)
    app.setFont(QFont("Segoe UI", 12))
    v = Venster()
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
