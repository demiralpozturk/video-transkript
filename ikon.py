# -*- coding: utf-8 -*-
"""Uygulama simgesi: ses dalgası → metin satırları (QPainter ile çizilir)."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap


def ikon_ciz(boyut: int) -> QPixmap:
    pm = QPixmap(boyut, boyut)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = boyut / 256.0

    # Zemin: yuvarlatılmış kare, indigo → mor degrade
    zemin = QRectF(8 * s, 8 * s, 240 * s, 240 * s)
    g = QLinearGradient(zemin.topLeft(), zemin.bottomRight())
    g.setColorAt(0.0, QColor("#4F46E5"))
    g.setColorAt(1.0, QColor("#9333EA"))
    yol = QPainterPath()
    yol.addRoundedRect(zemin, 56 * s, 56 * s)
    p.fillPath(yol, g)

    # Hafif parlama
    parlama = QLinearGradient(zemin.topLeft(), zemin.center())
    parlama.setColorAt(0.0, QColor(255, 255, 255, 46))
    parlama.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(yol, parlama)

    # Ses dalgası (sol)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    cubuklar = [44, 92, 132, 76, 108]
    genislik = 15 * s
    x = 40 * s
    merkez = 128 * s
    for h in cubuklar:
        hh = h * s
        p.drawRoundedRect(QRectF(x, merkez - hh / 2, genislik, hh), genislik / 2, genislik / 2)
        x += 23 * s

    # Metin satırları (sağ)
    satirlar = [(158, 92, 66), (158, 121, 48), (158, 150, 58)]
    for i, (sx, sy, uz) in enumerate(satirlar):
        renk = QColor(255, 255, 255, 255 if i == 0 else 200)
        p.setBrush(renk)
        p.drawRoundedRect(QRectF(sx * s, sy * s, uz * s, 14 * s), 7 * s, 7 * s)
    p.end()
    return pm
