# -*- coding: utf-8 -*-
# DraveGoedNieuws - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""vertaal.py - Engels naar Nederlands, helemaal op je eigen pc (Argos-model, CTranslate2).

Het model (ongeveer 72 MB) wordt één keer gedownload naar de data-map naast de app (dus niet op C:).
Vertalingen worden bewaard, zodat hetzelfde bericht nooit twee keer vertaald hoeft te worden.
"""
import hashlib
import json
import os
import re
import ssl
import threading
import urllib.request
import zipfile

MODEL_URL = "https://argos-net.com/v1/translate-en_nl-1_8.argosmodel"
MODEL_MAP = "translate-en_nl-1_8"


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class Vertaler:
    def __init__(self, data):
        self.data = data
        self.map = os.path.join(data, "vertaalmodel")
        self.cache_pad = os.path.join(data, "vertalingen.json")
        self._tr = self._sp = None
        self._lock = threading.Lock()
        try:
            with open(self.cache_pad, encoding="utf-8") as f:
                self.cache = json.load(f)
        except Exception:
            self.cache = {}

    def model_aanwezig(self):
        return os.path.exists(os.path.join(self.map, MODEL_MAP, "model", "model.bin"))

    def download(self, voortgang=None):
        """Downloadt het model (eenmalig). voortgang(fractie) wordt tussendoor aangeroepen."""
        os.makedirs(self.map, exist_ok=True)
        tijdelijk = os.path.join(self.map, "model.download")
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "DraveGoedNieuws/0.1 (Dravenlock)"})
        with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r, open(tijdelijk, "wb") as f:
            totaal = int(r.headers.get("Content-Length") or 0)
            klaar = 0
            while True:
                blok = r.read(1 << 16)
                if not blok:
                    break
                f.write(blok)
                klaar += len(blok)
                if voortgang and totaal:
                    voortgang(klaar / totaal)
        with zipfile.ZipFile(tijdelijk) as z:
            for n in z.namelist():
                if "/stanza/" not in n:                       # stanza is niet nodig: wij knippen zelf de zinnen
                    z.extract(n, self.map)
        os.remove(tijdelijk)

    def _laad(self):
        if self._tr is None:
            import ctranslate2
            import sentencepiece
            basis = os.path.join(self.map, MODEL_MAP)
            self._tr = ctranslate2.Translator(os.path.join(basis, "model"), device="cpu",
                                              inter_threads=1, intra_threads=max(1, (os.cpu_count() or 2) // 2))
            self._sp = sentencepiece.SentencePieceProcessor(model_file=os.path.join(basis, "sentencepiece.model"))

    @staticmethod
    def zinnen(tekst):
        delen = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“‘(])", tekst.strip())
        return [d for d in delen if d.strip()]

    def vertaal(self, tekst):
        tekst = (tekst or "").strip()
        if not tekst:
            return ""
        sleutel = hashlib.md5(tekst.encode("utf-8")).hexdigest()
        if sleutel in self.cache:
            return self.cache[sleutel]
        with self._lock:
            self._laad()
            zinnen = self.zinnen(tekst)
            tokens = [self._sp.encode(z, out_type=str) for z in zinnen]
            uit = self._tr.translate_batch(tokens, beam_size=2, max_decoding_length=256)
            nl = " ".join(self._sp.decode(u.hypotheses[0]) for u in uit)
            nl = nl.replace("▁", " ").strip()
            self.cache[sleutel] = nl
            return nl

    def bewaar(self):
        try:
            with open(self.cache_pad, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception:
            pass
