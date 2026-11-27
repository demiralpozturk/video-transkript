# -*- coding: utf-8 -*-
"""assets/icon.png + assets/icon.ico üretir (exe simgesi). Kullanım: python araclar/ikon_uret.py"""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from ikon import ikon_ciz  # noqa: E402


def pil(boyut):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    ikon_ciz(boyut).save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main():
    QGuiApplication(sys.argv)
    hedef = os.path.join(KOK, "assets")
    os.makedirs(hedef, exist_ok=True)
    buyuk = pil(256)
    buyuk.save(os.path.join(hedef, "icon.png"))
    boyutlar = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    kareler = {b: pil(b) for b in boyutlar}
    kareler[256].save(os.path.join(hedef, "icon.ico"), format="ICO",
                      sizes=[(b, b) for b in boyutlar],
                      append_images=[kareler[b] for b in boyutlar if b != 256])
    print("assets/icon.png, assets/icon.ico üretildi")


if __name__ == "__main__":
    main()
