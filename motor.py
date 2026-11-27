# -*- coding: utf-8 -*-
"""Transkript motoru — arayüzden bağımsız.

faster-whisper (CPU, int8) ile video/ses dosyalarını yazıya döker.
Eski komut satırı sürümüyle (transkript.py) aynı ayarlar ve aynı çıktı adları:
  <ad>.txt          düz metin
  <ad>_zamanli.txt  [HH:MM:SS] metin
  <ad>.srt          altyazı
  <ad>.vtt          web altyazısı (yeni)
Kaldığı yerden devam: seçili çıktıların hepsi varsa dosya atlanır. Çıktılar önce
.part olarak yazılır, iş bitince yerine konur; yarım kalan iş iz bırakmaz.
"""
import fnmatch
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app_info import APP_ID, VERSION

UZANTILAR = (
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
)

CIKTI_TURLERI = {
    "txt": ("Düz metin", ".txt"),
    "zamanli": ("Zaman damgalı metin", "_zamanli.txt"),
    "srt": ("Altyazı (SRT)", ".srt"),
    "vtt": ("Web altyazısı (VTT)", ".vtt"),
}


@dataclass(frozen=True)
class ModelBilgi:
    ad: str
    etiket: str
    aciklama: str
    boyut_mb: int
    repo: str


MODELLER = [
    ModelBilgi("tiny", "Çok hızlı", "En hızlı, doğruluğu düşük. Kısa denemeler için.", 75,
               "Systran/faster-whisper-tiny"),
    ModelBilgi("base", "Hızlı", "Hafif ve hızlı; temiz kayıtlarda yeterli.", 145,
               "Systran/faster-whisper-base"),
    ModelBilgi("small", "Dengeli · önerilen", "Hız ve doğruluk dengesi. Varsayılan model.", 484,
               "Systran/faster-whisper-small"),
    ModelBilgi("medium", "Doğru", "Daha doğru, ama 2–3 kat yavaş.", 1530,
               "Systran/faster-whisper-medium"),
    ModelBilgi("large-v3-turbo", "Çok doğru · turbo", "Büyük modelin hızlandırılmış sürümü.", 1620,
               "mobiuslabsgmbh/faster-whisper-large-v3-turbo"),
    ModelBilgi("large-v3", "En doğru", "En yüksek doğruluk, en yavaş.", 3090,
               "Systran/faster-whisper-large-v3"),
]
MODEL_HARITASI = {m.ad: m for m in MODELLER}

DILLER = [
    ("tr", "Türkçe"), ("auto", "Otomatik algıla"), ("en", "İngilizce"), ("de", "Almanca"),
    ("ar", "Arapça"), ("ru", "Rusça"), ("fr", "Fransızca"), ("es", "İspanyolca"),
    ("it", "İtalyanca"), ("fa", "Farsça"), ("az", "Azerbaycan Türkçesi"), ("zh", "Çince"),
]

_IZINLI = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


class Iptal(Exception):
    """Kullanıcı işi iptal etti."""


# ---------------------------------------------------------------- yardımcılar

def sure(s):
    s = max(0, int(s or 0))
    h, r = divmod(s, 3600)
    m, s2 = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s2:02d}"


def _zaman(s, ayirici):
    s = max(0.0, float(s))
    ms = int(round((s - int(s)) * 1000))
    tam = int(s)
    if ms == 1000:
        tam, ms = tam + 1, 0
    h, r = divmod(tam, 3600)
    m, s2 = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s2:02d}{ayirici}{ms:03d}"


def srt_zaman(s):
    return _zaman(s, ",")


def vtt_zaman(s):
    return _zaman(s, ".")


def boyut_yaz(bayt):
    if bayt is None:
        return "—"
    for birim in ("B", "KB", "MB", "GB"):
        if bayt < 1024 or birim == "GB":
            return f"{bayt:.0f} {birim}" if birim == "B" else f"{bayt:.1f} {birim}"
        bayt /= 1024
    return "—"


def veri_klasoru():
    taban = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    k = os.path.join(taban, APP_ID)
    os.makedirs(k, exist_ok=True)
    return k


def model_klasoru():
    return os.path.join(veri_klasoru(), "models")


def dosyalari_topla(yollar):
    """Dosya ve klasör yollarından desteklenen medya dosyalarının listesini çıkarır."""
    liste, gorulen = [], set()
    for y in yollar:
        y = os.path.abspath(str(y).strip().strip('"'))
        adaylar = []
        if os.path.isdir(y):
            for kok, _, adlar in os.walk(y):
                for ad in sorted(adlar):
                    if ad.lower().endswith(UZANTILAR):
                        adaylar.append(os.path.join(kok, ad))
        elif os.path.isfile(y) and y.lower().endswith(UZANTILAR):
            adaylar.append(y)
        for a in adaylar:
            anahtar = os.path.normcase(a)
            if anahtar not in gorulen:
                gorulen.add(anahtar)
                liste.append(a)
    return liste


def medya_suresi(yol):
    try:
        import av
        with av.open(yol) as kap:
            if kap.duration:
                return kap.duration / 1_000_000
            akis = next((s for s in kap.streams if s.type == "audio"), None)
            if akis is not None and akis.duration and akis.time_base:
                return float(akis.duration * akis.time_base)
    except Exception:
        return None
    return None


def ses_coz(yol, ilerleme=None, iptal=None):
    """Dosyadan sesi 16 kHz mono float32 olarak çıkarır (PyAV sürümünden bağımsız)."""
    import av
    import numpy as np
    parcalar = []
    with av.open(yol) as kap:
        akis = next((s for s in kap.streams if s.type == "audio"), None)
        if akis is None:
            raise ValueError("Bu dosyada ses kanalı yok.")
        toplam = kap.duration / 1_000_000 if kap.duration else None
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        son = 0.0
        for paket in kap.demux(akis):
            if iptal is not None and iptal.is_set():
                raise Iptal()
            try:
                kareler = paket.decode()
            except Exception:
                continue
            for kare in kareler:
                for k in rs.resample(kare):
                    parcalar.append(k.to_ndarray().reshape(-1))
                if ilerleme and toplam and kare.time is not None:
                    t = time.monotonic()
                    if t - son > 0.15:
                        son = t
                        ilerleme(max(0.0, min(kare.time / toplam, 1.0)))
        for k in rs.resample(None):
            parcalar.append(k.to_ndarray().reshape(-1))
    if not parcalar:
        raise ValueError("Ses çözülemedi (dosyada ses yok ya da bozuk).")
    if ilerleme:
        ilerleme(1.0)
    return np.concatenate(parcalar).astype(np.float32) / 32768.0


# ---------------------------------------------------------------- model

def _hf_onbellek_klasorleri():
    k = []
    if os.environ.get("HF_HUB_CACHE"):
        k.append(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        k.append(os.path.join(os.environ["HF_HOME"], "hub"))
    k.append(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
    return k


def _tam_mi(klasor):
    return all(os.path.isfile(os.path.join(klasor, a)) for a in ("model.bin", "config.json", "tokenizer.json"))


def model_yolu(ad):
    """Model indirilmişse klasörünü döndürür, yoksa None."""
    bilgi = MODEL_HARITASI.get(ad)
    if bilgi is None:
        return None
    kendi = os.path.join(model_klasoru(), ad)
    if os.path.isfile(os.path.join(kendi, ".tamam")) and _tam_mi(kendi):
        return kendi
    # Daha önce komut satırı sürümüyle indirilmiş model varsa onu kullan (tekrar indirme).
    org, isim = bilgi.repo.split("/", 1)
    for onbellek in _hf_onbellek_klasorleri():
        anlik = os.path.join(onbellek, f"models--{org}--{isim}", "snapshots")
        if os.path.isdir(anlik):
            for surum in sorted(os.listdir(anlik), reverse=True):
                yol = os.path.join(anlik, surum)
                if _tam_mi(yol):
                    return yol
    return None


def _istek(url, zaman_asimi=60):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{VERSION}"})
    return urllib.request.urlopen(req, timeout=zaman_asimi)


def _repo_dosyalari(repo):
    try:
        with _istek(f"https://huggingface.co/api/models/{repo}/tree/main", 30) as r:
            veri = json.loads(r.read().decode("utf-8"))
        dosyalar = []
        for d in veri:
            if d.get("type") != "file":
                continue
            yol = d.get("path", "")
            if any(fnmatch.fnmatch(yol, d_) for d_ in _IZINLI):
                boyut = (d.get("lfs") or {}).get("size") or d.get("size")
                dosyalar.append((yol, boyut))
        if any(y == "model.bin" for y, _ in dosyalar):
            return dosyalar
    except Exception:
        pass
    return [("config.json", None), ("preprocessor_config.json", None), ("tokenizer.json", None),
            ("vocabulary.txt", None), ("model.bin", None)]


def model_indir(ad, ilerleme=None, iptal=None):
    """Modeli %LOCALAPPDATA%\\VideoTranskript\\models\\<ad> altına indirir."""
    bilgi = MODEL_HARITASI[ad]
    hedef = os.path.join(model_klasoru(), ad)
    os.makedirs(hedef, exist_ok=True)
    dosyalar = _repo_dosyalari(bilgi.repo)
    toplam = sum(b for _, b in dosyalar if b) or bilgi.boyut_mb * 1024 * 1024
    indirilen = 0
    son = 0.0
    for isim, boyut in dosyalar:
        son_yol = os.path.join(hedef, isim)
        if os.path.isfile(son_yol) and boyut and os.path.getsize(son_yol) == boyut:
            indirilen += boyut
            continue
        try:
            yanit = _istek(f"https://huggingface.co/{bilgi.repo}/resolve/main/{isim}")
        except urllib.error.HTTPError as e:
            if e.code == 404 and isim != "model.bin":
                continue
            raise
        with yanit, open(son_yol + ".part", "wb") as f:
            while True:
                if iptal is not None and iptal.is_set():
                    raise Iptal()
                parca = yanit.read(1 << 20)
                if not parca:
                    break
                f.write(parca)
                indirilen += len(parca)
                t = time.monotonic()
                if ilerleme and t - son > 0.1:
                    son = t
                    ilerleme(indirilen, max(toplam, indirilen))
        os.replace(son_yol + ".part", son_yol)
    if not _tam_mi(hedef):
        raise RuntimeError("Model dosyaları eksik indi; internet bağlantısını kontrol edip tekrar deneyin.")
    open(os.path.join(hedef, ".tamam"), "w").close()
    if ilerleme:
        ilerleme(toplam, toplam)
    return hedef


_model_onbellek = {}


def model_yukle(yol):
    if yol not in _model_onbellek:
        from faster_whisper import WhisperModel
        _model_onbellek.clear()
        _model_onbellek[yol] = WhisperModel(yol, device="cpu", compute_type="int8",
                                           cpu_threads=os.cpu_count() or 4)
    return _model_onbellek[yol]


# ---------------------------------------------------------------- iş

@dataclass
class Ayarlar:
    model: str = "small"
    dil: str = "tr"
    ciktilar: tuple = ("txt", "zamanli", "srt", "vtt")
    cikti_klasoru: str = ""   # boş = dosyanın yanına (eski davranış)
    atla: bool = True          # kaldığı yerden devam
    hassas: bool = False       # beam 5: daha doğru, daha yavaş


@dataclass
class DosyaSonucu:
    yol: str
    durum: str = "bekliyor"    # bitti | atlandi | tamamlandi | hata | iptal
    mesaj: str = ""
    sure: float = 0.0          # medya süresi (sn)
    isleme: float = 0.0        # harcanan süre (sn)
    segment: int = 0
    ciktilar: dict = field(default_factory=dict)


class Olaylar:
    """Motorun bildirdiği olaylar. Arayüz ya da self-test bunları doldurur."""

    def asama(self, metin, belirsiz=False): pass
    def indirme(self, indirilen, toplam): pass
    def dosya_basladi(self, sira, yol): pass
    def ses_ilerleme(self, oran): pass
    def bilgi(self, dil, olasilik, sure_s): pass
    def segment(self, sira, bas, son, metin): pass
    def ilerleme(self, islenen, toplam, gecen, kalan, hiz): pass
    def dosya_bitti(self, sira, sonuc): pass


def cikti_yollari(yol, ayarlar):
    ad = os.path.splitext(os.path.basename(yol))[0]
    klasor = ayarlar.cikti_klasoru or os.path.dirname(os.path.abspath(yol))
    taban = os.path.join(klasor, ad)
    return {t: taban + CIKTI_TURLERI[t][1] for t in CIKTI_TURLERI if t in ayarlar.ciktilar}


def yapilmis_mi(yol, ayarlar):
    yollar = cikti_yollari(yol, ayarlar)
    return bool(yollar) and all(os.path.isfile(p) for p in yollar.values())


def _srt_yolu(yol, ayarlar):
    ad = os.path.splitext(os.path.basename(yol))[0]
    klasor = ayarlar.cikti_klasoru or os.path.dirname(os.path.abspath(yol))
    return os.path.join(klasor, ad + ".srt")


def tamamlanabilir_mi(yol, ayarlar):
    """Altyazı (.srt) zaten var ama başka çıktı eksikse: yeniden transkript etmeden tamamlanır."""
    return os.path.isfile(_srt_yolu(yol, ayarlar)) and not yapilmis_mi(yol, ayarlar)


_SRT_ZAMAN = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def srt_oku(yol):
    with open(yol, encoding="utf-8-sig") as f:
        bloklar = re.split(r"\n\s*\n", f.read().replace("\r\n", "\n").strip())
    segmentler = []
    for blok in bloklar:
        satirlar = blok.split("\n")
        for i, s in enumerate(satirlar):
            m = _SRT_ZAMAN.search(s)
            if m:
                g = [int(x) for x in m.groups()]
                bas = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                son = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                metin = " ".join(x.strip() for x in satirlar[i + 1:] if x.strip())
                if metin:
                    segmentler.append((bas, son, metin))
                break
    return segmentler


class _Yazici:
    """Seçili çıktıları .part dosyalarına yazar; bitir() ile yerine koyar."""

    def __init__(self, yollar):
        self.yollar = yollar
        self.dosyalar = {}
        self.n = 0
        for tur, yol in yollar.items():
            os.makedirs(os.path.dirname(yol), exist_ok=True)
            self.dosyalar[tur] = open(yol + ".part", "w", encoding="utf-8")
        if "vtt" in self.dosyalar:
            self.dosyalar["vtt"].write("WEBVTT\n\n")

    def yaz(self, bas, son, metin):
        self.n += 1
        d = self.dosyalar
        if "txt" in d:
            d["txt"].write(metin + "\n")
        if "zamanli" in d:
            d["zamanli"].write(f"[{sure(bas)}] {metin}\n")
        if "srt" in d:
            d["srt"].write(f"{self.n}\n{srt_zaman(bas)} --> {srt_zaman(son)}\n{metin}\n\n")
        if "vtt" in d:
            d["vtt"].write(f"{vtt_zaman(bas)} --> {vtt_zaman(son)}\n{metin}\n\n")
        for f in d.values():
            f.flush()

    def kapat(self):
        for f in self.dosyalar.values():
            try:
                f.close()
            except Exception:
                pass

    def bitir(self):
        self.kapat()
        # .srt en son yerine konur: eski sürümde ".srt varsa = tamamlandı" anlamına geliyordu.
        for tur in sorted(self.yollar, key=lambda t: t == "srt"):
            os.replace(self.yollar[tur] + ".part", self.yollar[tur])

    def iptal(self):
        self.kapat()
        for yol in self.yollar.values():
            try:
                os.remove(yol + ".part")
            except OSError:
                pass


def _tamamla(yol, ayarlar, sonuc):
    """Var olan .srt'den eksik çıktıları üretir (yeniden transkript etmeden)."""
    segmentler = srt_oku(_srt_yolu(yol, ayarlar))
    eksik = {t: p for t, p in cikti_yollari(yol, ayarlar).items() if not os.path.isfile(p)}
    yazici = _Yazici(eksik)
    try:
        for bas, son, metin in segmentler:
            yazici.yaz(bas, son, metin)
        yazici.bitir()
    except BaseException:
        yazici.iptal()
        raise
    sonuc.segment = len(segmentler)
    sonuc.sure = segmentler[-1][1] if segmentler else 0.0
    sonuc.durum = "tamamlandi"
    sonuc.mesaj = "Var olan altyazıdan eksik çıktılar üretildi"


def _isle(sira, yol, model, ayarlar, olaylar, iptal, sonuc):
    t0 = time.monotonic()
    olaylar.asama("Ses çıkarılıyor…")
    ses = ses_coz(yol, olaylar.ses_ilerleme, iptal)
    ses_suresi = len(ses) / 16000
    olaylar.asama("Yazıya dökülüyor…")
    dil = None if ayarlar.dil == "auto" else ayarlar.dil
    segs, info = model.transcribe(
        ses, language=dil, beam_size=5 if ayarlar.hassas else 1, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=False,
    )
    toplam = info.duration or ses_suresi or 1.0
    sonuc.sure = toplam
    olaylar.bilgi(info.language, info.language_probability, toplam)
    olaylar.ilerleme(0.0, toplam, 0.0, 0.0, 0.0)
    yazici = _Yazici(cikti_yollari(yol, ayarlar))
    t1 = time.monotonic()
    try:
        for s in segs:
            if iptal is not None and iptal.is_set():
                raise Iptal()
            metin = s.text.strip()
            if not metin:
                continue
            yazici.yaz(s.start, s.end, metin)
            gecen = time.monotonic() - t1
            islenen = min(s.end, toplam)
            hiz = islenen / gecen if gecen > 0 else 0.0
            kalan = (toplam - islenen) / hiz if hiz > 0 else 0.0
            olaylar.segment(yazici.n, s.start, s.end, metin)
            olaylar.ilerleme(islenen, toplam, gecen, kalan, hiz)
        yazici.bitir()
    except BaseException:
        yazici.iptal()
        raise
    gecen = time.monotonic() - t1
    olaylar.ilerleme(toplam, toplam, gecen, 0.0, toplam / gecen if gecen > 0 else 0.0)
    sonuc.segment = yazici.n
    sonuc.isleme = time.monotonic() - t0
    sonuc.durum = "bitti"


def calistir(dosyalar, ayarlar, olaylar=None, iptal=None):
    """Toplu işi çalıştırır; her dosya için DosyaSonucu döndürür."""
    olaylar = olaylar or Olaylar()
    sonuclar = [DosyaSonucu(yol=y) for y in dosyalar]
    model = None
    for sira, (yol, sonuc) in enumerate(zip(dosyalar, sonuclar)):
        sonuc.ciktilar = cikti_yollari(yol, ayarlar)
        if iptal is not None and iptal.is_set():
            sonuc.durum, sonuc.mesaj = "iptal", "İptal edildi"
            olaylar.dosya_bitti(sira, sonuc)
            continue
        olaylar.dosya_basladi(sira, yol)
        try:
            if not os.path.isfile(yol):
                raise FileNotFoundError("Dosya bulunamadı")
            if ayarlar.atla and yapilmis_mi(yol, ayarlar):
                sonuc.durum, sonuc.mesaj = "atlandi", "Daha önce yapılmış"
            elif ayarlar.atla and tamamlanabilir_mi(yol, ayarlar):
                _tamamla(yol, ayarlar, sonuc)
            else:
                if model is None:
                    mpath = model_yolu(ayarlar.model)
                    if mpath is None:
                        olaylar.asama(f"Model indiriliyor: {ayarlar.model} (yalnızca ilk sefer)")
                        mpath = model_indir(ayarlar.model, olaylar.indirme, iptal)
                    olaylar.asama("Model yükleniyor…", True)
                    model = model_yukle(mpath)
                _isle(sira, yol, model, ayarlar, olaylar, iptal, sonuc)
        except Iptal:
            sonuc.durum, sonuc.mesaj = "iptal", "İptal edildi"
        except Exception as e:  # dosya bazında hata: diğerlerine devam
            sonuc.durum, sonuc.mesaj = "hata", str(e) or e.__class__.__name__
        olaylar.dosya_bitti(sira, sonuc)
    return sonuclar
