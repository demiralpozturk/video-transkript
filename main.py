# -*- coding: utf-8 -*-
"""Video Transkript — giriş noktası.

  VideoTranskript.exe [dosya/klasör ...]          arayüzü açar (dosyalar listeye eklenir)
  VideoTranskript.exe --selftest [--model tiny] [--rapor yol] [dosya]
                                                  pencere açmadan uçtan uca deneme
  VideoTranskript.exe --ekran-goruntusu KLASÖR [dosya]
                                                  her adımın ekran görüntüsünü alır (geliştirme)
"""
import argparse
import os
import sys
import tempfile
import threading
import time
import traceback

import app_info
from deneme import ornek_ses_uret

def _konsola_baglan():
    """Pencereli exe'de --selftest çıktısı için çağıran konsola bağlanmayı dener."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            k32 = ctypes.windll.kernel32
            eski = k32.GetConsoleOutputCP()
            k32.SetConsoleOutputCP(65001)
            import atexit
            atexit.register(k32.SetConsoleOutputCP, eski)
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = sys.stdout
            return
    except Exception:
        pass
    sys.stdout = sys.stdout or open(os.devnull, "w", encoding="utf-8")
    sys.stderr = sys.stderr or sys.stdout


def selftest(argv):
    import motor

    p = argparse.ArgumentParser(prog="VideoTranskript --selftest")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--model", default="small")
    p.add_argument("--rapor", default=os.path.join(motor.veri_klasoru(), "selftest.log"))
    p.add_argument("--klasor", default="")
    p.add_argument("dosya", nargs="?")
    a = p.parse_args(argv)

    satirlar = []

    def yaz(s=""):
        satirlar.append(s)
        try:
            print(s, flush=True)
        except Exception:
            pass

    basarili = False
    try:
        klasor = a.klasor or tempfile.mkdtemp(prefix="vt_selftest_")
        os.makedirs(klasor, exist_ok=True)
        if a.dosya:
            dosya = os.path.abspath(a.dosya)
        else:
            dosya = os.path.join(klasor, "deneme_kaydi.wav")
            ses = ornek_ses_uret(dosya)
            yaz(f"Deneme sesi üretildi ({ses}): {dosya}")
        yaz(f"{app_info.APP_NAME} {app_info.VERSION} self-test · model={a.model}")

        class Yazici(motor.Olaylar):
            def asama(self, metin, belirsiz=False):
                yaz(f"  · {metin}")

            def indirme(self, indirilen, toplam):
                pass

            def bilgi(self, dil, olasilik, sure_s):
                yaz(f"  · Süre {motor.sure(sure_s)} · dil {dil} ({olasilik:.0%})")

            def segment(self, sira, bas, son, metin):
                yaz(f"  [{motor.sure(bas)} → {motor.sure(son)}] {metin}")

            def dosya_bitti(self, sira, sonuc):
                yaz(f"  = {sonuc.durum} · {sonuc.segment} segment · {sonuc.isleme:.1f} sn {sonuc.mesaj}")

        ayar = motor.Ayarlar(model=a.model, dil="tr", cikti_klasoru=klasor, atla=False)
        t0 = time.monotonic()
        sonuc = motor.calistir([dosya], ayar, Yazici(), threading.Event())[0]
        yaz(f"Toplam süre: {time.monotonic() - t0:.1f} sn")

        hatalar = []
        if sonuc.durum != "bitti":
            hatalar.append(f"durum {sonuc.durum}: {sonuc.mesaj}")
        for tur, yol in sonuc.ciktilar.items():
            if not os.path.isfile(yol) or os.path.getsize(yol) == 0:
                hatalar.append(f"{tur} çıktısı yok/boş: {yol}")
            else:
                yaz(f"  çıktı {tur}: {yol} ({os.path.getsize(yol)} bayt)")
        srt = sonuc.ciktilar.get("srt")
        if srt and os.path.isfile(srt):
            seg = motor.srt_oku(srt)
            if not seg:
                hatalar.append("SRT okunamadı")
        txt = sonuc.ciktilar.get("txt")
        if txt and os.path.isfile(txt) and not a.dosya:
            icerik = open(txt, encoding="utf-8").read().lower()
            beklenen = ["merhaba", "deneme", "transkript", "türkçe", "altyazı", "internet"]
            bulunan = [k for k in beklenen if k in icerik]
            yaz(f"  beklenen kelimeler: {len(bulunan)}/{len(beklenen)} bulundu {bulunan}")
            if len(bulunan) < 3:
                hatalar.append("transkript beklenen kelimeleri içermiyor")
        # Kaldığı yerden devam: ikinci çalıştırma dosyayı atlamalı.
        ayar2 = motor.Ayarlar(model=a.model, dil="tr", cikti_klasoru=klasor, atla=True)
        ikinci = motor.calistir([dosya], ayar2, motor.Olaylar(), threading.Event())[0]
        yaz(f"  devam testi: ikinci çalıştırma → {ikinci.durum}")
        if ikinci.durum != "atlandi":
            hatalar.append("kaldığı yerden devam çalışmadı")
        # Eksik çıktı tamamlama: .vtt silinince transkript etmeden geri gelmeli.
        vtt = sonuc.ciktilar.get("vtt")
        if vtt and os.path.isfile(vtt):
            os.remove(vtt)
            ucuncu = motor.calistir([dosya], ayar2, motor.Olaylar(), threading.Event())[0]
            yaz(f"  tamamlama testi: .vtt silindi → {ucuncu.durum}")
            if ucuncu.durum != "tamamlandi" or not os.path.isfile(vtt):
                hatalar.append("eksik çıktı tamamlama çalışmadı")
        if hatalar:
            yaz("SONUÇ: BAŞARISIZ")
            for h in hatalar:
                yaz("  - " + h)
        else:
            yaz("SONUÇ: BAŞARILI")
            basarili = True
    except Exception:
        yaz("SONUÇ: BAŞARISIZ (istisna)")
        yaz(traceback.format_exc())
    try:
        os.makedirs(os.path.dirname(os.path.abspath(a.rapor)), exist_ok=True)
        with open(a.rapor, "w", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")
    except Exception:
        pass
    return 0 if basarili else 1


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        _konsola_baglan()
        sys.exit(selftest(argv))
    if "--ekran-goruntusu" in argv:
        _konsola_baglan()
        from arayuz import ekran_goruntuleri
        i = argv.index("--ekran-goruntusu")
        hedef = argv[i + 1]
        kalan = argv[:i] + argv[i + 2:]
        sys.exit(ekran_goruntuleri(hedef, kalan[0] if kalan else None))
    from arayuz import calistir_arayuz
    sys.exit(calistir_arayuz([x for x in argv if not x.startswith("--")]))


if __name__ == "__main__":
    main()
