# -*- coding: utf-8 -*-
"""Video Transkript — PySide6 arayüzü.

Adımlar: 1 Dosya seç → 2 Ayarlar → 3 Transkript → 4 Sonuç
Ağır iş (model indirme/yükleme, ses çözme, transkript) ayrı iş parçacığında çalışır.
"""
import html
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPalette,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
                               QScrollArea, QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

import app_info
import motor
from ikon import ikon_ciz

# ------------------------------------------------------------------ tema

TEMALAR = {
    "acik": dict(bg="#F5F6FA", yuzey="#FFFFFF", yuzey2="#F0F2F8", kenar="#E2E5EE", yazi="#1A1D29",
                 soluk="#6B7183", vurgu="#5B54E8", vurgu2="#8B5CF6", vurgu_yazi="#FFFFFF", basari="#15A34A",
                 uyari="#D97706", tehlike="#DC2626", akis="#F7F8FC", secim="#E9E8FD", iz="#E6E8F0",
                 kenar_koyu="#B9BED0"),
    "koyu": dict(bg="#0E1016", yuzey="#161922", yuzey2="#1C202B", kenar="#272B38", yazi="#E8EAF0",
                 soluk="#98A0B3", vurgu="#7B74FF", vurgu2="#A78BFA", vurgu_yazi="#FFFFFF", basari="#22C55E",
                 uyari="#F59E0B", tehlike="#F87171", akis="#11141B", secim="#2A2850", iz="#242836",
                 kenar_koyu="#4A5066"),
}


def _ui_gorselleri(r):
    """QSS'in kullandığı küçük görselleri (tik, ok) üretir; yolları döndürür."""
    klasor = os.path.join(motor.veri_klasoru(), "ui")
    os.makedirs(klasor, exist_ok=True)
    isaret = os.path.join(klasor, "isaret.png")
    ok = os.path.join(klasor, f"ok_{r['yazi'].strip('#')}.png")
    if not os.path.isfile(isaret):
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#FFFFFF"), 4.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(8, 16.5), QPointF(13.5, 22), QPointF(24, 10.5)])
        p.end()
        pm.save(isaret)
    if not os.path.isfile(ok):
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(r["soluk"]), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])
        p.end()
        pm.save(ok)
    return isaret.replace("\\", "/"), ok.replace("\\", "/")


def stil_sayfasi(r):
    r = dict(r)
    r["isaret"], r["ok"] = _ui_gorselleri(r)
    return f"""
    QWidget {{ color: {r['yazi']}; }}
    QMainWindow, QDialog, QWidget#kok {{ background: {r['bg']}; }}
    QWidget#ustBar {{ background: {r['yuzey']}; border-bottom: 1px solid {r['kenar']}; }}
    QWidget#altBar {{ background: {r['yuzey']}; border-top: 1px solid {r['kenar']}; }}
    QFrame[kart="true"] {{ background: {r['yuzey']}; border: 1px solid {r['kenar']}; border-radius: 14px; }}
    QFrame[chip="true"] {{ background: {r['yuzey2']}; border: 1px solid {r['kenar']}; border-radius: 12px; }}
    QLabel {{ background: transparent; }}
    QLabel[rol="baslik"] {{ font-size: 18pt; font-weight: 700; }}
    QLabel[rol="altbaslik"] {{ color: {r['soluk']}; font-size: 10pt; }}
    QLabel[rol="bolum"] {{ font-size: 12.5pt; font-weight: 650; }}
    QLabel[rol="soluk"] {{ color: {r['soluk']}; }}
    QLabel[rol="kucuk"] {{ color: {r['soluk']}; font-size: 8.5pt; }}
    QLabel[rol="chipDeger"] {{ font-size: 15pt; font-weight: 700; }}
    QLabel[rol="chipAd"] {{ color: {r['soluk']}; font-size: 8.5pt; }}
    QLabel[rol="basari"] {{ color: {r['basari']}; }}
    QLabel[rol="tehlike"] {{ color: {r['tehlike']}; }}
    QLabel[rol="vurgu"] {{ color: {r['vurgu']}; font-weight: 600; }}
    QPushButton {{
        background: {r['yuzey']}; border: 1px solid {r['kenar']}; border-radius: 10px;
        padding: 8px 16px; font-weight: 600;
    }}
    QPushButton:hover {{ border-color: {r['vurgu']}; }}
    QPushButton:pressed {{ background: {r['yuzey2']}; }}
    QPushButton:disabled {{ color: {r['soluk']}; background: {r['yuzey2']}; border-color: {r['kenar']}; }}
    QPushButton[tur="birincil"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {r['vurgu']}, stop:1 {r['vurgu2']});
        color: {r['vurgu_yazi']}; border: none; padding: 10px 22px;
    }}
    QPushButton[tur="birincil"]:hover {{ background: {r['vurgu']}; }}
    QPushButton[tur="birincil"]:disabled {{ background: {r['iz']}; color: {r['soluk']}; }}
    QPushButton[tur="tehlike"] {{ color: {r['tehlike']}; border-color: {r['tehlike']}; }}
    QPushButton[tur="duz"] {{ background: transparent; border: none; color: {r['soluk']}; padding: 6px 10px; }}
    QPushButton[tur="duz"]:hover {{ color: {r['vurgu']}; }}
    QProgressBar {{
        background: {r['iz']}; border: none; border-radius: 6px; height: 12px; text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 6px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {r['vurgu']}, stop:1 {r['vurgu2']});
    }}
    QTreeWidget, QListWidget {{
        background: {r['yuzey']}; border: 1px solid {r['kenar']}; border-radius: 10px; padding: 4px;
        alternate-background-color: {r['yuzey2']}; outline: none;
    }}
    QTreeWidget::item {{ padding: 6px 4px; border: none; }}
    QTreeWidget::item:selected {{ background: {r['secim']}; color: {r['yazi']}; }}
    QHeaderView::section {{
        background: transparent; color: {r['soluk']}; border: none; border-bottom: 1px solid {r['kenar']};
        padding: 6px 4px; font-weight: 600;
    }}
    QPlainTextEdit {{
        background: {r['akis']}; border: 1px solid {r['kenar']}; border-radius: 10px; padding: 8px;
        selection-background-color: {r['secim']}; selection-color: {r['yazi']};
    }}
    QComboBox, QLineEdit {{
        background: {r['yuzey']}; border: 1px solid {r['kenar']}; border-radius: 8px; padding: 6px 10px;
        min-height: 20px;
    }}
    QComboBox:hover, QLineEdit:focus {{ border-color: {r['vurgu']}; }}
    QComboBox QAbstractItemView {{ background: {r['yuzey']}; border: 1px solid {r['kenar']};
        selection-background-color: {r['secim']}; selection-color: {r['yazi']}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {r['kenar']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {r['kenar']}; border-radius: 4px; min-width: 30px; }}
    QRadioButton, QCheckBox {{ spacing: 9px; background: transparent; }}
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 16px; height: 16px; border: 2px solid {r['kenar_koyu']}; background: {r['yuzey']};
    }}
    QRadioButton::indicator {{ border-radius: 10px; }}
    QCheckBox::indicator {{ border-radius: 6px; }}
    QRadioButton::indicator:hover, QCheckBox::indicator:hover {{ border-color: {r['vurgu']}; }}
    QRadioButton::indicator:checked {{
        border-color: {r['vurgu']};
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
            stop:0 {r['vurgu']}, stop:0.42 {r['vurgu']}, stop:0.52 {r['yuzey']}, stop:1 {r['yuzey']});
    }}
    QCheckBox::indicator:checked {{ background: {r['vurgu']}; border-color: {r['vurgu']}; image: url({r['isaret']}); }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url({r['ok']}); width: 12px; height: 12px; }}
    QSplitter::handle {{ background: transparent; }}
    QToolTip {{ background: {r['yuzey']}; color: {r['yazi']}; border: 1px solid {r['kenar']}; padding: 4px; }}
    """


def palet(r):
    p = QPalette()
    p.setColor(QPalette.Window, QColor(r["bg"]))
    p.setColor(QPalette.WindowText, QColor(r["yazi"]))
    p.setColor(QPalette.Base, QColor(r["yuzey"]))
    p.setColor(QPalette.AlternateBase, QColor(r["yuzey2"]))
    p.setColor(QPalette.Text, QColor(r["yazi"]))
    p.setColor(QPalette.Button, QColor(r["yuzey"]))
    p.setColor(QPalette.ButtonText, QColor(r["yazi"]))
    p.setColor(QPalette.Highlight, QColor(r["vurgu"]))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.PlaceholderText, QColor(r["soluk"]))
    p.setColor(QPalette.Link, QColor(r["vurgu"]))
    p.setColor(QPalette.ToolTipBase, QColor(r["yuzey"]))
    p.setColor(QPalette.ToolTipText, QColor(r["yazi"]))
    return p


def _rol(w, rol):
    w.setProperty("rol", rol)
    return w


def _etiket(metin, rol=None, kelime_kaydir=False):
    e = QLabel(metin)
    if rol:
        e.setProperty("rol", rol)
    if kelime_kaydir:
        e.setWordWrap(True)
    return e


def _dugme(metin, tur=None, ipucu=None):
    b = QPushButton(metin)
    if tur:
        b.setProperty("tur", tur)
    if ipucu:
        b.setToolTip(ipucu)
    b.setCursor(Qt.PointingHandCursor)
    return b


def _kart():
    f = QFrame()
    f.setProperty("kart", True)
    return f


def _yeniden_stille(w):
    w.style().unpolish(w)
    w.style().polish(w)


def _tema_ikonu(tur, renk):
    """Tema düğmesi simgesi: sistem = yarım daire, açık = güneş, koyu = ay."""
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(renk)
    if tur == "acik":
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(15, 15, 18, 18))
        p.setPen(QPen(c, 3.4, Qt.SolidLine, Qt.RoundCap))
        import math
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(24 + 14 * math.cos(a), 24 + 14 * math.sin(a)),
                       QPointF(24 + 20 * math.cos(a), 24 + 20 * math.sin(a)))
    elif tur == "koyu":
        from PySide6.QtGui import QPainterPath
        dis = QPainterPath()
        dis.addEllipse(QRectF(6, 6, 36, 36))
        ic = QPainterPath()
        ic.addEllipse(QRectF(17, 0, 32, 32))
        p.fillPath(dis.subtracted(ic), c)
    else:
        p.setPen(QPen(c, 3.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(7, 7, 34, 34))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPie(QRectF(7, 7, 34, 34), 90 * 16, 180 * 16)
    p.end()
    return QIcon(pm)


def _klasorde_goster(yol):
    try:
        if os.path.exists(yol):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(yol)])
        else:
            os.startfile(os.path.dirname(yol))
    except Exception:
        pass


def _metin_oku(sonuc):
    for tur in ("zamanli", "txt", "srt", "vtt"):
        yol = sonuc.ciktilar.get(tur)
        if yol and os.path.isfile(yol):
            try:
                with open(yol, encoding="utf-8-sig") as f:
                    return f.read()
            except Exception:
                pass
    return ""


def _duz_metin(sonuc):
    yol = sonuc.ciktilar.get("txt")
    if yol and os.path.isfile(yol):
        with open(yol, encoding="utf-8-sig") as f:
            return f.read()
    srt = sonuc.ciktilar.get("srt")
    if srt and os.path.isfile(srt):
        return "\n".join(m for _, _, m in motor.srt_oku(srt))
    return _metin_oku(sonuc)


# ------------------------------------------------------------------ bileşenler

class AdimCubugu(QWidget):
    """1 Dosya seç → 2 Ayarlar → 3 Transkript → 4 Sonuç"""

    tiklandi = Signal(int)
    ADLAR = ["Dosya seç", "Ayarlar", "Transkript", "Sonuç"]

    def __init__(self):
        super().__init__()
        self.aktif = 0
        self.tiklanabilir = set()
        self.renkler = TEMALAR["acik"]
        self.setMinimumHeight(74)
        self.setMouseTracking(True)

    def ayarla(self, aktif, tiklanabilir=()):
        self.aktif = aktif
        self.tiklanabilir = set(tiklanabilir)
        self.update()

    def _merkezler(self):
        kenar = 70
        g = max(self.width() - 2 * kenar, 1)
        return [kenar + g * i / (len(self.ADLAR) - 1) for i in range(len(self.ADLAR))]

    def paintEvent(self, _):
        r = self.renkler
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        merkezler = self._merkezler()
        y = 24.0
        yaricap = 15.0
        for i in range(len(merkezler) - 1):
            renk = QColor(r["vurgu"]) if i < self.aktif else QColor(r["kenar"])
            p.setPen(QPen(renk, 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(merkezler[i] + yaricap + 6, y), QPointF(merkezler[i + 1] - yaricap - 6, y))
        yazi_font = QFont(self.font())
        for i, x in enumerate(merkezler):
            daire = QRectF(x - yaricap, y - yaricap, 2 * yaricap, 2 * yaricap)
            if i < self.aktif:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(r["vurgu"]))
                p.drawEllipse(daire)
                p.setPen(QPen(QColor("#FFFFFF"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(x - 6, y), QPointF(x - 1.5, y + 4.5), QPointF(x + 6.5, y - 4.5)])
            elif i == self.aktif:
                halka = QColor(r["vurgu"])
                halka.setAlpha(60)
                p.setPen(Qt.NoPen)
                p.setBrush(halka)
                p.drawEllipse(daire.adjusted(-5, -5, 5, 5))
                p.setBrush(QColor(r["vurgu"]))
                p.drawEllipse(daire)
                p.setPen(QColor("#FFFFFF"))
                f = QFont(yazi_font)
                f.setBold(True)
                p.setFont(f)
                p.drawText(daire, Qt.AlignCenter, str(i + 1))
            else:
                p.setPen(QPen(QColor(r["kenar"]), 2))
                p.setBrush(QColor(r["yuzey"]))
                p.drawEllipse(daire)
                p.setPen(QColor(r["soluk"]))
                f = QFont(yazi_font)
                f.setBold(True)
                p.setFont(f)
                p.drawText(daire, Qt.AlignCenter, str(i + 1))
            f = QFont(yazi_font)
            f.setBold(i == self.aktif)
            p.setFont(f)
            p.setPen(QColor(r["yazi"] if i <= self.aktif else r["soluk"]))
            p.drawText(QRectF(x - 80, y + yaricap + 8, 160, 22), Qt.AlignHCenter | Qt.AlignTop,
                       f"{i + 1}. {self.ADLAR[i]}")
        p.end()

    def _adim_at(self, pos):
        for i, x in enumerate(self._merkezler()):
            if abs(pos.x() - x) < 60 and pos.y() < 70:
                return i
        return None

    def mouseMoveEvent(self, e):
        i = self._adim_at(e.position())
        self.setCursor(Qt.PointingHandCursor if i in self.tiklanabilir else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        i = self._adim_at(e.position())
        if i in self.tiklanabilir:
            self.tiklandi.emit(i)


class SurukleAlani(QFrame):
    """Kesikli kenarlı sürükle-bırak alanı (tıklayınca dosya seçici açılır)."""

    tiklandi = Signal()

    def __init__(self):
        super().__init__()
        self.renkler = TEMALAR["acik"]
        self.vurgulu = False
        self.setMinimumHeight(170)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Tıklayın ya da dosyaları buraya sürükleyin")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.tiklandi.emit()

    def enterEvent(self, e):
        self.vurgulu = True
        self.update()

    def leaveEvent(self, e):
        self.vurgulu = False
        self.update()

    def paintEvent(self, _):
        r = self.renkler
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alan = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        zemin = QColor(r["secim"] if self.vurgulu else r["yuzey"])
        p.setBrush(zemin)
        kalem = QPen(QColor(r["vurgu"] if self.vurgulu else r["kenar"]), 2, Qt.DashLine)
        kalem.setDashPattern([5, 4])
        p.setPen(kalem)
        p.drawRoundedRect(alan, 16, 16)
        # yukarı ok + tepsi
        cx, cy = alan.center().x(), alan.top() + 52
        p.setPen(QPen(QColor(r["vurgu"]), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(cx, cy - 18), QPointF(cx, cy + 10))
        p.drawPolyline([QPointF(cx - 11, cy - 7), QPointF(cx, cy - 18), QPointF(cx + 11, cy - 7)])
        p.drawPolyline([QPointF(cx - 22, cy + 6), QPointF(cx - 22, cy + 18), QPointF(cx + 22, cy + 18),
                        QPointF(cx + 22, cy + 6)])
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() + 2.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(r["yazi"]))
        p.drawText(QRectF(alan.left(), cy + 30, alan.width(), 28), Qt.AlignCenter,
                   "Videoları veya ses dosyalarını buraya sürükleyip bırakın")
        f2 = QFont(self.font())
        p.setFont(f2)
        p.setPen(QColor(r["soluk"]))
        p.drawText(QRectF(alan.left(), cy + 58, alan.width(), 22), Qt.AlignCenter,
                   "ya da tıklayıp seçin · MP4, MKV, MOV, AVI, MP3, WAV, M4A, OGG… · klasör de olur")
        p.end()


class Chip(QFrame):
    def __init__(self, ad, deger="—"):
        super().__init__()
        self.setProperty("chip", True)
        l = QVBoxLayout(self)
        l.setContentsMargins(14, 10, 14, 10)
        l.setSpacing(2)
        self.deger = _etiket(deger, "chipDeger")
        l.addWidget(_etiket(ad, "chipAd"))
        l.addWidget(self.deger)

    def yaz(self, metin):
        self.deger.setText(metin)


# ------------------------------------------------------------------ iş parçacıkları

class SureOkuyucu(QThread):
    okundu = Signal(str, float, float)  # yol, süre (sn, -1 = bilinmiyor), boyut (bayt)

    def __init__(self, yollar):
        super().__init__()
        self.yollar = list(yollar)

    def run(self):
        for y in self.yollar:
            s = motor.medya_suresi(y)
            try:
                b = float(os.path.getsize(y))
            except OSError:
                b = -1.0
            self.okundu.emit(y, -1.0 if s is None else float(s), b)


class IsParcacigi(QThread):
    asamaS = Signal(str, bool)
    indirmeS = Signal(float, float)
    dosyaBasladiS = Signal(int, str)
    sesS = Signal(float)
    bilgiS = Signal(str, float, float)
    segmentS = Signal(int, float, float, str)
    ilerlemeS = Signal(float, float, float, float, float)
    dosyaBittiS = Signal(int, object)
    bittiS = Signal(object, str)

    def __init__(self, dosyalar, ayarlar):
        super().__init__()
        self.dosyalar = list(dosyalar)
        self.ayarlar = ayarlar
        self.iptal = threading.Event()

    def run(self):
        is_ = self

        class Kopru(motor.Olaylar):
            def asama(self, metin, belirsiz=False): is_.asamaS.emit(metin, belirsiz)
            def indirme(self, indirilen, toplam): is_.indirmeS.emit(float(indirilen), float(toplam))
            def dosya_basladi(self, sira, yol): is_.dosyaBasladiS.emit(sira, yol)
            def ses_ilerleme(self, oran): is_.sesS.emit(float(oran))
            def bilgi(self, dil, olasilik, sure_s): is_.bilgiS.emit(str(dil), float(olasilik), float(sure_s))
            def segment(self, sira, bas, son, metin): is_.segmentS.emit(sira, float(bas), float(son), metin)
            def ilerleme(self, *a): is_.ilerlemeS.emit(*[float(x) for x in a])
            def dosya_bitti(self, sira, sonuc): is_.dosyaBittiS.emit(sira, sonuc)

        try:
            sonuclar = motor.calistir(self.dosyalar, self.ayarlar, Kopru(), self.iptal)
            self.bittiS.emit(sonuclar, "")
        except Exception:
            self.bittiS.emit([], traceback.format_exc())


# ------------------------------------------------------------------ hakkında

class HakkindaPenceresi(QDialog):
    def __init__(self, ust, renkler):
        super().__init__(ust)
        self.setWindowTitle(f"Hakkında — {app_info.APP_NAME}")
        self.setMinimumWidth(460)
        l = QVBoxLayout(self)
        l.setContentsMargins(28, 26, 28, 22)
        l.setSpacing(10)
        ust_satir = QHBoxLayout()
        ikon = QLabel()
        ikon.setPixmap(ikon_ciz(128).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        ust_satir.addWidget(ikon)
        bilgi = QVBoxLayout()
        bilgi.addWidget(_etiket(app_info.APP_NAME, "baslik"))
        bilgi.addWidget(_etiket(f"Sürüm {app_info.VERSION}", "soluk"))
        ust_satir.addLayout(bilgi, 1)
        ust_satir.setSpacing(16)
        l.addLayout(ust_satir)
        l.addWidget(_etiket(app_info.DESCRIPTION, kelime_kaydir=True))

        kart = _kart()
        kl = QVBoxLayout(kart)
        kl.setContentsMargins(16, 14, 16, 14)
        kl.addWidget(_etiket(f"{app_info.CREATOR_ROLE}: <b>{app_info.CREATOR}</b>"))
        baglantilar = _etiket(baglanti_html(renkler, ayirici="<br>"))
        baglantilar.setOpenExternalLinks(True)
        baglantilar.setTextInteractionFlags(Qt.TextBrowserInteraction)
        kl.addWidget(baglantilar)
        l.addWidget(kart)

        l.addWidget(_etiket(
            "Ses dosyaları bilgisayarınızdan dışarı çıkmaz; yalnızca ilk kullanımda yapay zekâ modeli indirilir.\n"
            "Teknoloji: faster-whisper / CTranslate2 (MIT), OpenAI Whisper modelleri (MIT), Qt for Python (LGPL).",
            "kucuk", True))
        kapat = _dugme("Kapat", "birincil")
        kapat.clicked.connect(self.accept)
        alt = QHBoxLayout()
        alt.addStretch(1)
        alt.addWidget(kapat)
        l.addLayout(alt)


def baglanti_html(renkler, ayirici=" · "):
    v = renkler["vurgu"]
    parcalar = [f'<a style="color:{v};text-decoration:none" href="{app_info.GITHUB}">GitHub</a>']
    if app_info.LINKEDIN:
        parcalar.append(f'<a style="color:{v};text-decoration:none" href="{app_info.LINKEDIN}">LinkedIn</a>')
    if app_info.EMAIL:
        parcalar.append(f'<a style="color:{v};text-decoration:none" href="mailto:{app_info.EMAIL}">'
                        f'{html.escape(app_info.EMAIL)}</a>')
    return ayirici.join(parcalar)


# ------------------------------------------------------------------ ana pencere

DURUM_METNI = {
    "hazir": ("Hazır", "soluk"),
    "yapilmis": ("Yapılmış · atlanacak", "basari"),
    "tamamlanacak": ("Altyazı var · eksikler tamamlanacak", "basari"),
    "bekliyor": ("Bekliyor", "soluk"),
    "isleniyor": ("İşleniyor…", "vurgu"),
    "bitti": ("✓ Bitti", "basari"),
    "atlandi": ("↷ Atlandı (zaten yapılmış)", "soluk"),
    "tamamlandi": ("✓ Eksikler tamamlandı", "basari"),
    "hata": ("✕ Hata", "tehlike"),
    "iptal": ("⊘ İptal edildi", "soluk"),
}


class AnaPencere(QMainWindow):
    def __init__(self, ayar_dosyasi=None):
        super().__init__()
        self.ayarlar_kayit = QSettings(ayar_dosyasi or os.path.join(motor.veri_klasoru(), "ayarlar.ini"),
                                       QSettings.IniFormat)
        self.dosyalar = []
        self.sureler = {}
        self.boyutlar = {}
        self.okuyucular = []
        self.is_ = None
        self.sonuclar = []
        self.adim = 0
        self.tema_secimi = self.ayarlar_kayit.value("tema", "sistem")
        self.renkler = TEMALAR["acik"]
        self.is_basladi = 0.0
        self.son_hiz = 0.0
        self.dosya_kalan = 0.0
        self.segment_sayisi = 0
        self.aktif_sira = -1
        self.akis_otomatik = True

        self.setWindowTitle(app_info.APP_NAME)
        self.setWindowIcon(QIcon(ikon_ciz(256)))
        self.setAcceptDrops(True)
        self.resize(1120, 760)
        self.setMinimumSize(940, 640)

        kok = QWidget()
        kok.setObjectName("kok")
        self.setCentralWidget(kok)
        dikey = QVBoxLayout(kok)
        dikey.setContentsMargins(0, 0, 0, 0)
        dikey.setSpacing(0)
        dikey.addWidget(self._ust_bar())

        govde = QVBoxLayout()
        govde.setContentsMargins(28, 14, 28, 16)
        govde.setSpacing(10)
        self.adimlar = AdimCubugu()
        self.adimlar.tiklandi.connect(self._adim_tiklandi)
        govde.addWidget(self.adimlar)
        self.yigin = QStackedWidget()
        self.yigin.addWidget(self._sayfa_dosya())
        self.yigin.addWidget(self._sayfa_ayarlar())
        self.yigin.addWidget(self._sayfa_transkript())
        self.yigin.addWidget(self._sayfa_sonuc())
        govde.addWidget(self.yigin, 1)
        dikey.addLayout(govde, 1)
        dikey.addWidget(self._alt_bar())

        self.saat = QTimer(self)
        self.saat.setInterval(1000)
        self.saat.timeout.connect(self._saat_tik)

        self._ayarlari_yukle()
        self.tema_uygula()
        self.adima_git(0)
        QApplication.styleHints().colorSchemeChanged.connect(lambda *_: self.tema_uygula())

    # ---------------------------------------------------------- çubuklar
    def _ust_bar(self):
        w = QWidget()
        w.setObjectName("ustBar")
        l = QHBoxLayout(w)
        l.setContentsMargins(24, 14, 20, 14)
        l.setSpacing(14)
        ikon = QLabel()
        ikon.setPixmap(ikon_ciz(128).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        l.addWidget(ikon)
        yazi = QVBoxLayout()
        yazi.setSpacing(0)
        baslik = _etiket(app_info.APP_NAME, "baslik")
        yazi.addWidget(baslik)
        yazi.addWidget(_etiket(app_info.DESCRIPTION, "altbaslik"))
        l.addLayout(yazi, 1)
        imza = QVBoxLayout()
        imza.setSpacing(0)
        e = _etiket(f"{app_info.CREATOR_ROLE}: <b>{app_info.CREATOR}</b>", "soluk")
        e.setAlignment(Qt.AlignRight)
        imza.addWidget(e)
        l.addLayout(imza)
        self.github_btn = _dugme("GitHub", "duz", app_info.GITHUB)
        self.github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(app_info.GITHUB)))
        l.addWidget(self.github_btn)
        if app_info.LINKEDIN:
            self.linkedin_btn = _dugme("LinkedIn", "duz", app_info.LINKEDIN)
            self.linkedin_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(app_info.LINKEDIN)))
            l.addWidget(self.linkedin_btn)
        self.tema_btn = _dugme("", "duz", "Tema: sistem / açık / koyu")
        self.tema_btn.clicked.connect(self._tema_degistir)
        l.addWidget(self.tema_btn)
        hk = _dugme("Hakkında", None)
        hk.clicked.connect(self.hakkinda)
        l.addWidget(hk)
        return w

    def _alt_bar(self):
        w = QWidget()
        w.setObjectName("altBar")
        l = QHBoxLayout(w)
        l.setContentsMargins(24, 8, 24, 8)
        sol = _etiket(f"{app_info.APP_NAME} v{app_info.VERSION} · yerel yapay zekâ · ses internete gönderilmez",
                      "kucuk")
        l.addWidget(sol)
        l.addStretch(1)
        self.alt_baglanti = _etiket("", "kucuk")
        self.alt_baglanti.setOpenExternalLinks(True)
        self.alt_baglanti.setTextInteractionFlags(Qt.TextBrowserInteraction)
        l.addWidget(self.alt_baglanti)
        return w

    # ---------------------------------------------------------- sayfa 1
    def _sayfa_dosya(self):
        s = QWidget()
        l = QVBoxLayout(s)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(12)
        self.surukle = SurukleAlani()
        self.surukle.tiklandi.connect(self.dosya_sec)
        l.addWidget(self.surukle)

        butonlar = QHBoxLayout()
        b1 = _dugme("Dosya seç…", None, "Bir veya birden fazla video/ses dosyası seçin")
        b1.clicked.connect(self.dosya_sec)
        b2 = _dugme("Klasör seç…", None, "Klasördeki tüm video/ses dosyalarını ekler (alt klasörler dahil)")
        b2.clicked.connect(self.klasor_sec)
        b3 = _dugme("Masaüstünden seç…", None, "Dosya seçiciyi Masaüstü'nde açar")
        b3.clicked.connect(lambda: self.dosya_sec(masaustu=True))
        for b in (b1, b2, b3):
            butonlar.addWidget(b)
        butonlar.addStretch(1)
        self.temizle_btn = _dugme("Listeyi temizle", "duz")
        self.temizle_btn.clicked.connect(self.listeyi_temizle)
        self.kaldir_btn = _dugme("Seçileni kaldır", "duz")
        self.kaldir_btn.clicked.connect(self.secileni_kaldir)
        butonlar.addWidget(self.kaldir_btn)
        butonlar.addWidget(self.temizle_btn)
        l.addLayout(butonlar)

        self.liste = QTreeWidget()
        self.liste.setHeaderLabels(["Dosya", "Süre", "Boyut", "Durum"])
        self.liste.setRootIsDecorated(False)
        self.liste.setAlternatingRowColors(True)
        self.liste.setSelectionMode(QAbstractItemView.ExtendedSelection)
        h = self.liste.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        l.addWidget(self.liste, 1)

        alt = QHBoxLayout()
        self.liste_ozet = _etiket("Henüz dosya eklenmedi.", "soluk")
        alt.addWidget(self.liste_ozet, 1)
        self.ileri1 = _dugme("İleri: Ayarlar  →", "birincil")
        self.ileri1.clicked.connect(lambda: self.adima_git(1))
        alt.addWidget(self.ileri1)
        l.addLayout(alt)
        return s

    # ---------------------------------------------------------- sayfa 2
    def _sayfa_ayarlar(self):
        s = QWidget()
        dis = QVBoxLayout(s)
        dis.setContentsMargins(0, 0, 0, 0)
        kaydir = QScrollArea()
        kaydir.setWidgetResizable(True)
        ic = QWidget()
        izgara = QGridLayout(ic)
        izgara.setContentsMargins(0, 0, 6, 0)
        izgara.setHorizontalSpacing(14)
        izgara.setVerticalSpacing(14)

        # Model kartı
        mk = _kart()
        ml = QVBoxLayout(mk)
        ml.setContentsMargins(18, 16, 18, 16)
        ml.setSpacing(6)
        ml.addWidget(_etiket("Yapay zekâ modeli", "bolum"))
        ml.addWidget(_etiket("Büyük model daha doğru ama daha yavaştır. Model bir kez indirilir, sonra "
                             "internetsiz çalışır.", "soluk", True))
        self.model_grubu = QButtonGroup(self)
        self.model_durum = {}
        mg = QGridLayout()
        mg.setHorizontalSpacing(14)
        mg.setVerticalSpacing(9)
        mg.setContentsMargins(0, 6, 0, 0)
        for i, m in enumerate(motor.MODELLER):
            rb = QRadioButton(f"{m.etiket}")
            rb.setProperty("model", m.ad)
            rb.setToolTip(f"{m.ad} — {m.aciklama}")
            f = rb.font()
            f.setBold(True)
            rb.setFont(f)
            self.model_grubu.addButton(rb, i)
            aciklama = _etiket(f"{m.ad} · {m.aciklama}", "kucuk")
            aciklama.setToolTip(m.aciklama)
            durum = _etiket("", "kucuk")
            durum.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.model_durum[m.ad] = durum
            mg.addWidget(rb, i, 0)
            mg.addWidget(aciklama, i, 1)
            mg.addWidget(durum, i, 2)
        mg.setColumnStretch(1, 1)
        ml.addLayout(mg)
        ml.addStretch(1)
        izgara.addWidget(mk, 0, 0, 2, 1)

        # Dil + hassas
        dk = _kart()
        dl = QVBoxLayout(dk)
        dl.setContentsMargins(18, 16, 18, 16)
        dl.setSpacing(8)
        dl.addWidget(_etiket("Konuşma dili", "bolum"))
        self.dil = QComboBox()
        for kod, ad in motor.DILLER:
            self.dil.addItem(ad, kod)
        dl.addWidget(self.dil)
        self.hassas = QCheckBox("Hassas mod (daha doğru, yaklaşık 2 kat yavaş)")
        dl.addWidget(self.hassas)
        dl.addStretch(1)
        izgara.addWidget(dk, 0, 1)

        # Çıktılar
        ck = _kart()
        cl = QVBoxLayout(ck)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(6)
        cl.addWidget(_etiket("Çıktı dosyaları", "bolum"))
        self.cikti_kutulari = {}
        aciklamalar = {"txt": "<ad>.txt — sadece metin", "zamanli": "<ad>_zamanli.txt — [00:01:23] metin",
                       "srt": "<ad>.srt — video oynatıcılar için altyazı", "vtt": "<ad>.vtt — web/YouTube altyazısı"}
        cg = QGridLayout()
        cg.setHorizontalSpacing(10)
        cg.setVerticalSpacing(8)
        for i, (tur, (ad, _)) in enumerate(motor.CIKTI_TURLERI.items()):
            cb = QCheckBox(f"{ad}")
            cb.setToolTip(aciklamalar[tur])
            cb.toggled.connect(self._ayar_degisti)
            self.cikti_kutulari[tur] = cb
            cg.addWidget(cb, i, 0)
            e = _etiket(aciklamalar[tur].split(" — ")[0].replace("<", "&lt;").replace(">", "&gt;"), "kucuk")
            e.setToolTip(aciklamalar[tur])
            cg.addWidget(e, i, 1)
        cg.setColumnStretch(1, 1)
        cl.addLayout(cg)
        cl.addStretch(1)
        izgara.addWidget(ck, 1, 1)

        # Konum ve devam
        kk = _kart()
        kl = QVBoxLayout(kk)
        kl.setContentsMargins(18, 16, 18, 16)
        kl.setSpacing(8)
        kl.addWidget(_etiket("Kayıt yeri ve kaldığı yerden devam", "bolum"))
        self.konum_yaninda = QRadioButton("Her dosyanın yanına kaydet (önerilen)")
        self.konum_klasor = QRadioButton("Tek bir klasöre kaydet:")
        self.konum_grubu = QButtonGroup(self)
        self.konum_grubu.addButton(self.konum_yaninda)
        self.konum_grubu.addButton(self.konum_klasor)
        kl.addWidget(self.konum_yaninda)
        satir = QHBoxLayout()
        satir.addWidget(self.konum_klasor)
        self.konum_yolu = QLineEdit()
        self.konum_yolu.setPlaceholderText("Klasör seçin…")
        self.konum_yolu.setReadOnly(True)
        satir.addWidget(self.konum_yolu, 1)
        sec = _dugme("Seç…")
        sec.clicked.connect(self._cikti_klasoru_sec)
        satir.addWidget(sec)
        kl.addLayout(satir)
        self.atla = QCheckBox("Daha önce yapılmış dosyaları atla (toplu işte kaldığı yerden devam eder)")
        kl.addWidget(self.atla)
        for w in (self.konum_yaninda, self.konum_klasor, self.atla):
            w.toggled.connect(self._ayar_degisti)
        izgara.addWidget(kk, 2, 0, 1, 2)
        izgara.setColumnStretch(0, 3)
        izgara.setColumnStretch(1, 2)
        kaydir.setWidget(ic)
        dis.addWidget(kaydir, 1)

        alt = QHBoxLayout()
        geri = _dugme("←  Geri")
        geri.clicked.connect(lambda: self.adima_git(0))
        alt.addWidget(geri)
        self.ayar_ozet = _etiket("", "soluk")
        alt.addWidget(self.ayar_ozet, 1)
        self.baslat = _dugme("Transkripti başlat  ▶", "birincil")
        self.baslat.clicked.connect(self.baslat_is)
        alt.addWidget(self.baslat)
        dis.addLayout(alt)
        self.model_grubu.idToggled.connect(lambda *_: self._ayar_degisti())
        return s

    # ---------------------------------------------------------- sayfa 3
    def _sayfa_transkript(self):
        s = QWidget()
        l = QVBoxLayout(s)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(12)

        kart = _kart()
        kl = QVBoxLayout(kart)
        kl.setContentsMargins(18, 14, 18, 16)
        kl.setSpacing(6)
        ust = QHBoxLayout()
        self.aktif_dosya = _etiket("Hazırlanıyor…", "bolum")
        self.aktif_dosya.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ust.addWidget(self.aktif_dosya, 1)
        self.yuzde = _etiket("", "vurgu")
        self.yuzde.setMinimumWidth(60)
        self.yuzde.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ust.addWidget(self.yuzde)
        kl.addLayout(ust)
        self.asama = _etiket("", "soluk")
        kl.addWidget(self.asama)
        self.dosya_cubugu = QProgressBar()
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setFixedHeight(12)
        kl.addWidget(self.dosya_cubugu)
        genel = QHBoxLayout()
        self.genel_yazi = _etiket("", "kucuk")
        genel.addWidget(self.genel_yazi)
        self.genel_cubugu = QProgressBar()
        self.genel_cubugu.setRange(0, 1000)
        self.genel_cubugu.setFixedHeight(6)
        genel.addWidget(self.genel_cubugu, 1)
        kl.addLayout(genel)
        l.addWidget(kart)

        chipler = QHBoxLayout()
        chipler.setSpacing(10)
        self.c_islenen = Chip("İşlenen / süre")
        self.c_gecen = Chip("Geçen süre")
        self.c_kalan = Chip("Kalan (tahmini)")
        self.c_hiz = Chip("Hız")
        self.c_segment = Chip("Segment")
        for c in (self.c_islenen, self.c_gecen, self.c_kalan, self.c_hiz, self.c_segment):
            chipler.addWidget(c, 1)
        l.addLayout(chipler)

        bolucu = QSplitter(Qt.Horizontal)
        sol = QWidget()
        sl = QVBoxLayout(sol)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(_etiket("Dosya kuyruğu", "soluk"))
        self.kuyruk = QTreeWidget()
        self.kuyruk.setHeaderLabels(["Dosya", "Durum"])
        self.kuyruk.setRootIsDecorated(False)
        self.kuyruk.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.kuyruk.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        sl.addWidget(self.kuyruk, 1)
        sag = QWidget()
        sgl = QVBoxLayout(sag)
        sgl.setContentsMargins(0, 0, 0, 0)
        sgl.addWidget(_etiket("Canlı transkript — her satırın başladığı ve bittiği saniye", "soluk"))
        self.akis = QPlainTextEdit()
        self.akis.setReadOnly(True)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        for aday in ("Cascadia Mono", "Consolas"):
            if aday in QFontDatabase.families():
                mono = QFont(aday)
                break
        mono.setPointSizeF(10)
        self.akis.setFont(mono)
        self.akis.verticalScrollBar().valueChanged.connect(self._akis_kaydirildi)
        sgl.addWidget(self.akis, 1)
        bolucu.addWidget(sol)
        bolucu.addWidget(sag)
        bolucu.setStretchFactor(0, 2)
        bolucu.setStretchFactor(1, 5)
        bolucu.setSizes([300, 760])
        l.addWidget(bolucu, 1)

        alt = QHBoxLayout()
        self.is_ozet = _etiket("", "soluk")
        alt.addWidget(self.is_ozet, 1)
        self.iptal_btn = _dugme("İptal et", "tehlike")
        self.iptal_btn.clicked.connect(self.iptal_et)
        alt.addWidget(self.iptal_btn)
        l.addLayout(alt)
        return s

    # ---------------------------------------------------------- sayfa 4
    def _sayfa_sonuc(self):
        s = QWidget()
        l = QVBoxLayout(s)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(12)
        kart = _kart()
        kl = QHBoxLayout(kart)
        kl.setContentsMargins(20, 16, 20, 16)
        kl.setSpacing(16)
        self.sonuc_ikon = QLabel()
        self.sonuc_ikon.setFixedSize(48, 48)
        kl.addWidget(self.sonuc_ikon)
        yazi = QVBoxLayout()
        yazi.setSpacing(2)
        self.sonuc_baslik = _etiket("Tamamlandı", "baslik")
        self.sonuc_alt = _etiket("", "soluk", True)
        yazi.addWidget(self.sonuc_baslik)
        yazi.addWidget(self.sonuc_alt)
        kl.addLayout(yazi, 1)
        l.addWidget(kart)

        bolucu = QSplitter(Qt.Horizontal)
        self.sonuc_listesi = QTreeWidget()
        self.sonuc_listesi.setHeaderLabels(["Dosya", "Durum", "Süre", "Segment"])
        self.sonuc_listesi.setRootIsDecorated(False)
        self.sonuc_listesi.setAlternatingRowColors(True)
        h = self.sonuc_listesi.header()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.sonuc_listesi.currentItemChanged.connect(self._sonuc_secildi)
        self.sonuc_listesi.itemDoubleClicked.connect(lambda *_: self._metni_ac())
        bolucu.addWidget(self.sonuc_listesi)
        sag = QWidget()
        sl = QVBoxLayout(sag)
        sl.setContentsMargins(0, 0, 0, 0)
        self.onizleme_baslik = _etiket("Önizleme", "soluk")
        sl.addWidget(self.onizleme_baslik)
        self.onizleme = QPlainTextEdit()
        self.onizleme.setReadOnly(True)
        sl.addWidget(self.onizleme, 1)
        bolucu.addWidget(sag)
        bolucu.setSizes([430, 640])
        l.addWidget(bolucu, 1)

        alt = QHBoxLayout()
        self.kopyala_btn = _dugme("Metni kopyala", None, "Seçili dosyanın düz metnini panoya kopyalar")
        self.kopyala_btn.clicked.connect(self._metni_kopyala)
        self.ac_btn = _dugme("Metni aç", None, "Metin dosyasını varsayılan uygulamada açar")
        self.ac_btn.clicked.connect(self._metni_ac)
        self.klasor_btn = _dugme("Klasörü aç", None, "Çıktıların bulunduğu klasörü açar")
        self.klasor_btn.clicked.connect(self._klasoru_ac)
        for b in (self.kopyala_btn, self.ac_btn, self.klasor_btn):
            alt.addWidget(b)
        self.kopyalandi = _etiket("", "basari")
        alt.addWidget(self.kopyalandi)
        alt.addStretch(1)
        yeni = _dugme("Yeni transkript  ↺", "birincil")
        yeni.clicked.connect(self.yeni_is)
        alt.addWidget(yeni)
        l.addLayout(alt)
        return s

    # ---------------------------------------------------------- tema
    def _koyu_mu(self):
        if self.tema_secimi == "koyu":
            return True
        if self.tema_secimi == "acik":
            return False
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def tema_uygula(self):
        self.renkler = TEMALAR["koyu" if self._koyu_mu() else "acik"]
        app = QApplication.instance()
        app.setPalette(palet(self.renkler))
        app.setStyleSheet(stil_sayfasi(self.renkler))
        self.adimlar.renkler = self.renkler
        self.surukle.renkler = self.renkler
        self.adimlar.update()
        self.surukle.update()
        adlar = {"sistem": "Sistem", "acik": "Açık", "koyu": "Koyu"}
        self.tema_btn.setText(adlar.get(self.tema_secimi, "Sistem"))
        self.tema_btn.setIcon(_tema_ikonu(self.tema_secimi, self.renkler["soluk"]))
        self.tema_btn.setIconSize(QSize(16, 16))
        self.alt_baglanti.setText(f"© 2026 · {app_info.CREATOR_ROLE}: <b>{app_info.CREATOR}</b> · "
                                  + baglanti_html(self.renkler))
        self._sonuc_ikonu_ciz()

    def _tema_degistir(self):
        sira = ["sistem", "acik", "koyu"]
        self.tema_secimi = sira[(sira.index(self.tema_secimi) + 1) % 3] if self.tema_secimi in sira else "sistem"
        self.ayarlar_kayit.setValue("tema", self.tema_secimi)
        self.tema_uygula()

    def hakkinda(self):
        HakkindaPenceresi(self, self.renkler).exec()

    # ---------------------------------------------------------- adımlar
    def adima_git(self, i):
        if i == 1 and not self.dosyalar:
            return
        if i == 1:
            self._model_durumlarini_yenile()
            self._ayar_degisti()
        if i == 0:
            self._liste_durumlarini_yenile()
        self.adim = i
        self.yigin.setCurrentIndex(i)
        calisiyor = self.is_ is not None
        if calisiyor:
            tiklanabilir = ()
        elif i == 3:
            tiklanabilir = (0, 1)
        else:
            tiklanabilir = tuple(x for x in (0, 1) if x != i and (x == 0 or self.dosyalar))
        self.adimlar.ayarla(i, tiklanabilir)

    def _adim_tiklandi(self, i):
        if self.is_ is None:
            self.adima_git(i)

    # ---------------------------------------------------------- dosyalar
    def dosya_sec(self, masaustu=False):
        baslangic = (os.path.join(os.path.expanduser("~"), "Desktop") if masaustu
                     else self.ayarlar_kayit.value("son_klasor", os.path.join(os.path.expanduser("~"), "Desktop")))
        filtre = "Video ve ses (" + " ".join("*" + u for u in motor.UZANTILAR) + ");;Tüm dosyalar (*.*)"
        yollar, _ = QFileDialog.getOpenFileNames(self, "Video veya ses dosyası seçin", baslangic, filtre)
        if yollar:
            self.ayarlar_kayit.setValue("son_klasor", os.path.dirname(yollar[0]))
            self.dosya_ekle(yollar)

    def klasor_sec(self):
        baslangic = self.ayarlar_kayit.value("son_klasor", os.path.join(os.path.expanduser("~"), "Desktop"))
        k = QFileDialog.getExistingDirectory(self, "Klasör seçin", baslangic)
        if k:
            self.ayarlar_kayit.setValue("son_klasor", k)
            self.dosya_ekle([k])

    def dosya_ekle(self, yollar):
        if self.is_ is not None:
            return
        yeni = [y for y in motor.dosyalari_topla(yollar)
                if os.path.normcase(y) not in {os.path.normcase(d) for d in self.dosyalar}]
        if not yeni:
            if yollar:
                self.liste_ozet.setText("Eklenecek desteklenen video/ses dosyası bulunamadı.")
            return
        self.dosyalar.extend(yeni)
        okuyucu = SureOkuyucu([y for y in yeni if y not in self.sureler])
        okuyucu.okundu.connect(self._sure_okundu)
        okuyucu.finished.connect(lambda o=okuyucu: self.okuyucular.remove(o) if o in self.okuyucular else None)
        self.okuyucular.append(okuyucu)
        okuyucu.start()
        if self.adim != 0:
            self.adima_git(0)
        self._liste_durumlarini_yenile()

    def _sure_okundu(self, yol, s, b):
        self.sureler[yol] = None if s < 0 else s
        self.boyutlar[yol] = None if b < 0 else b
        self._liste_durumlarini_yenile()

    def listeyi_temizle(self):
        self.dosyalar.clear()
        self._liste_durumlarini_yenile()
        self.adima_git(0)

    def secileni_kaldir(self):
        secili = {self.liste.indexOfTopLevelItem(it) for it in self.liste.selectedItems()}
        self.dosyalar = [d for i, d in enumerate(self.dosyalar) if i not in secili]
        self._liste_durumlarini_yenile()
        self.adima_git(0)

    def _dosya_durumu(self, yol):
        a = self.mevcut_ayarlar()
        if a.atla and motor.yapilmis_mi(yol, a):
            return "yapilmis"
        if a.atla and motor.tamamlanabilir_mi(yol, a):
            return "tamamlanacak"
        return "hazir"

    def _liste_durumlarini_yenile(self):
        self.liste.clear()
        toplam_sure = 0.0
        bilinmeyen = 0
        yapilacak = 0
        for y in self.dosyalar:
            s = self.sureler.get(y)
            durum = self._dosya_durumu(y)
            metin, rol = DURUM_METNI[durum]
            it = QTreeWidgetItem([os.path.basename(y), motor.sure(s) if s else "…",
                                  motor.boyut_yaz(self.boyutlar.get(y)) if y in self.boyutlar else "…", metin])
            it.setToolTip(0, y)
            it.setForeground(3, QColor(self.renkler.get(rol, self.renkler["soluk"])))
            self.liste.addTopLevelItem(it)
            if durum == "hazir":
                yapilacak += 1
                if s:
                    toplam_sure += s
                else:
                    bilinmeyen += 1
        n = len(self.dosyalar)
        if n == 0:
            self.liste_ozet.setText("Henüz dosya eklenmedi. Sürükleyip bırakın ya da “Dosya seç…” ile seçin.")
        else:
            atlanacak = n - yapilacak
            metin = f"{n} dosya · toplam {motor.sure(toplam_sure)} yazıya dökülecek"
            if atlanacak:
                metin += f" · {atlanacak} dosya zaten yapılmış"
            self.liste_ozet.setText(metin)
        self.ileri1.setEnabled(n > 0)
        self.temizle_btn.setEnabled(n > 0)
        self.kaldir_btn.setEnabled(n > 0)

    # ---------------------------------------------------------- ayarlar
    def _ayarlari_yukle(self):
        k = self.ayarlar_kayit
        model = k.value("model", "small")
        for b in self.model_grubu.buttons():
            if b.property("model") == model:
                b.setChecked(True)
        if self.model_grubu.checkedButton() is None:
            self.model_grubu.button(2).setChecked(True)
        i = self.dil.findData(k.value("dil", "tr"))
        self.dil.setCurrentIndex(max(i, 0))
        self.hassas.setChecked(k.value("hassas", "false") == "true")
        secili = (k.value("ciktilar", "txt,zamanli,srt,vtt") or "").split(",")
        for tur, cb in self.cikti_kutulari.items():
            cb.setChecked(tur in secili)
        klasor = k.value("cikti_klasoru", "") or ""
        self.konum_yolu.setText(klasor)
        (self.konum_klasor if (k.value("konum", "yaninda") == "klasor" and klasor) else self.konum_yaninda
         ).setChecked(True)
        self.atla.setChecked(k.value("atla", "true") == "true")

    def _ayarlari_kaydet(self):
        a = self.mevcut_ayarlar()
        k = self.ayarlar_kayit
        k.setValue("model", a.model)
        k.setValue("dil", a.dil)
        k.setValue("hassas", "true" if a.hassas else "false")
        k.setValue("ciktilar", ",".join(a.ciktilar))
        k.setValue("konum", "klasor" if self.konum_klasor.isChecked() else "yaninda")
        k.setValue("cikti_klasoru", self.konum_yolu.text())
        k.setValue("atla", "true" if a.atla else "false")

    def mevcut_ayarlar(self):
        b = self.model_grubu.checkedButton()
        return motor.Ayarlar(
            model=b.property("model") if b else "small",
            dil=self.dil.currentData() or "tr",
            ciktilar=tuple(t for t, cb in self.cikti_kutulari.items() if cb.isChecked()),
            cikti_klasoru=self.konum_yolu.text() if self.konum_klasor.isChecked() else "",
            atla=self.atla.isChecked(),
            hassas=self.hassas.isChecked(),
        )

    def _cikti_klasoru_sec(self):
        k = QFileDialog.getExistingDirectory(self, "Çıktı klasörü seçin", self.konum_yolu.text()
                                             or os.path.join(os.path.expanduser("~"), "Desktop"))
        if k:
            self.konum_yolu.setText(k)
            self.konum_klasor.setChecked(True)
            self._ayar_degisti()

    def _model_durumlarini_yenile(self):
        for m in motor.MODELLER:
            e = self.model_durum[m.ad]
            boyut = f"{m.boyut_mb / 1024:.1f} GB" if m.boyut_mb >= 1000 else f"{m.boyut_mb} MB"
            if motor.model_yolu(m.ad):
                e.setText("✓ İndirilmiş")
                e.setToolTip("Bu model bilgisayarda hazır; internetsiz çalışır.")
                e.setProperty("rol", "basari")
            else:
                e.setText(f"İnecek · {boyut}")
                e.setToolTip(f"İlk kullanımda bir kez indirilir ({boyut}).")
                e.setProperty("rol", "kucuk")
            _yeniden_stille(e)

    def _ayar_degisti(self, *_):
        if not hasattr(self, "baslat"):
            return
        a = self.mevcut_ayarlar()
        sorun = ""
        if not a.ciktilar:
            sorun = "En az bir çıktı türü seçin."
        elif self.konum_klasor.isChecked() and not self.konum_yolu.text():
            sorun = "Çıktı klasörü seçin."
        self.baslat.setEnabled(not sorun and bool(self.dosyalar))
        if sorun:
            self.ayar_ozet.setText(sorun)
            self.ayar_ozet.setProperty("rol", "tehlike")
        else:
            yapilacak = sum(1 for y in self.dosyalar if self._dosya_durumu(y) != "yapilmis")
            self.ayar_ozet.setText(f"{yapilacak} dosya işlenecek · model {a.model} · "
                                   f"{dict(motor.DILLER).get(a.dil, a.dil)}")
            self.ayar_ozet.setProperty("rol", "soluk")
        _yeniden_stille(self.ayar_ozet)

    # ---------------------------------------------------------- iş
    def baslat_is(self):
        if self.is_ is not None or not self.dosyalar:
            return
        self._ayarlari_kaydet()
        ayarlar = self.mevcut_ayarlar()
        self.sonuclar = []
        self.akis.clear()
        self.kuyruk.clear()
        for y in self.dosyalar:
            it = QTreeWidgetItem([os.path.basename(y), DURUM_METNI["bekliyor"][0]])
            it.setToolTip(0, y)
            it.setForeground(1, QColor(self.renkler["soluk"]))
            self.kuyruk.addTopLevelItem(it)
        self.bitenler = set()
        self.segment_sayisi = 0
        self.son_hiz = 0.0
        self.dosya_kalan = 0.0
        self.dosya_toplam = 0.0
        self.dosya_islenen = 0.0
        self.aktif_sira = -1
        self.akis_otomatik = True
        for c in (self.c_islenen, self.c_kalan, self.c_hiz, self.c_segment):
            c.yaz("—")
        self.c_gecen.yaz("00:00:00")
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setValue(0)
        self.genel_cubugu.setValue(0)
        self.aktif_dosya.setText("Hazırlanıyor…")
        self.asama.setText("")
        self.yuzde.setText("")
        self.iptal_btn.setEnabled(True)
        self.iptal_btn.setText("İptal et")
        self.is_basladi = time.monotonic()
        self.is_ = IsParcacigi(self.dosyalar, ayarlar)
        self.is_.asamaS.connect(self._asama)
        self.is_.indirmeS.connect(self._indirme)
        self.is_.dosyaBasladiS.connect(self._dosya_basladi)
        self.is_.sesS.connect(self._ses)
        self.is_.bilgiS.connect(self._bilgi)
        self.is_.segmentS.connect(self._segment)
        self.is_.ilerlemeS.connect(self._ilerleme)
        self.is_.dosyaBittiS.connect(self._dosya_bitti)
        self.is_.bittiS.connect(self._is_bitti)
        self.adima_git(2)
        self.saat.start()
        self._genel_yenile()
        self.is_.start()

    def iptal_et(self):
        if self.is_ is None:
            return
        cevap = QMessageBox.question(
            self, "İptal edilsin mi?",
            "Biten dosyalar korunur. Şu an işlenen dosyanın yarım çıktısı silinir;\n"
            "sonra tekrar başlattığınızda kaldığı yerden devam eder.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if cevap == QMessageBox.Yes and self.is_ is not None:
            self.is_.iptal.set()
            self.iptal_btn.setEnabled(False)
            self.iptal_btn.setText("İptal ediliyor…")
            self.asama.setText("İptal ediliyor… (o anki parça bitince durur)")

    def _asama(self, metin, belirsiz):
        self.asama.setText(metin)
        if belirsiz:
            self.dosya_cubugu.setRange(0, 0)
            self.yuzde.setText("")
        else:
            self.dosya_cubugu.setRange(0, 1000)

    def _indirme(self, indirilen, toplam):
        self.dosya_cubugu.setRange(0, 1000)
        oran = indirilen / toplam if toplam else 0
        self.dosya_cubugu.setValue(int(oran * 1000))
        self.yuzde.setText(f"%{oran * 100:.0f}")
        self.asama.setText(f"Model indiriliyor (yalnızca ilk sefer) · "
                           f"{indirilen / 1048576:.0f} / {toplam / 1048576:.0f} MB")
        self._baslik_yaz(oran, "Model indiriliyor")

    def _dosya_basladi(self, sira, yol):
        self.aktif_sira = sira
        self.dosya_toplam = self.sureler.get(yol) or 0.0
        self.dosya_islenen = 0.0
        self.dosya_kalan = 0.0
        self.aktif_dosya.setText(f"{os.path.basename(yol)}")
        self.aktif_dosya.setToolTip(yol)
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setValue(0)
        self.yuzde.setText("")
        self.c_islenen.yaz(f"00:00:00 / {motor.sure(self.dosya_toplam)}" if self.dosya_toplam else "—")
        it = self.kuyruk.topLevelItem(sira)
        if it:
            it.setText(1, DURUM_METNI["isleniyor"][0])
            it.setForeground(1, QColor(self.renkler["vurgu"]))
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            self.kuyruk.scrollToItem(it)
        self._genel_yenile()

    def _ses(self, oran):
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setValue(int(oran * 1000))
        self.yuzde.setText(f"%{oran * 100:.0f}")
        self.asama.setText(f"Ses çıkarılıyor… %{oran * 100:.0f}")

    def _bilgi(self, dil, olasilik, sure_s):
        self.dosya_toplam = sure_s
        ad = dict(motor.DILLER).get(dil, dil)
        self.asama.setText(f"Yazıya dökülüyor · dil: {ad} (%{olasilik * 100:.0f}) · süre {motor.sure(sure_s)}")
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setValue(0)
        if self.akis.document().characterCount() > 1:
            self.akis.appendPlainText("")
        r = self.renkler
        ad_dosya = html.escape(os.path.basename(self.dosyalar[self.aktif_sira])) if self.aktif_sira >= 0 else ""
        self.akis.appendHtml(f'<span style="color:{r["soluk"]}">── {ad_dosya} · {motor.sure(sure_s)} ──</span>')

    def _segment(self, sira, bas, son, metin):
        self.segment_sayisi += 1
        r = self.renkler
        self.akis.appendHtml(
            f'<span style="color:{r["vurgu"]}">[{motor.sure(bas)} → {motor.sure(son)}]</span> '
            f'{html.escape(metin)}')
        if self.akis_otomatik:
            sb = self.akis.verticalScrollBar()
            sb.setValue(sb.maximum())
        self.c_segment.yaz(str(self.segment_sayisi))

    def _akis_kaydirildi(self, deger):
        sb = self.akis.verticalScrollBar()
        self.akis_otomatik = deger >= sb.maximum() - 4

    def _ilerleme(self, islenen, toplam, gecen, kalan, hiz):
        self.dosya_toplam = toplam
        self.dosya_islenen = islenen
        self.dosya_kalan = kalan
        if hiz > 0:
            self.son_hiz = hiz
        oran = islenen / toplam if toplam else 0
        self.dosya_cubugu.setRange(0, 1000)
        self.dosya_cubugu.setValue(int(oran * 1000))
        self.yuzde.setText(f"%{oran * 100:.0f}")
        self.c_islenen.yaz(f"{motor.sure(islenen)} / {motor.sure(toplam)}")
        self.c_hiz.yaz(f"×{self.son_hiz:.1f}" if self.son_hiz else "—")
        self.c_hiz.setToolTip("Gerçek zamanın kaç katı hızla işleniyor (×2 = 1 dakikalık kayıt 30 saniyede)")
        self._genel_yenile()

    def _dosya_bitti(self, sira, sonuc):
        self.bitenler.add(sira)
        it = self.kuyruk.topLevelItem(sira)
        if it:
            metin, rol = DURUM_METNI.get(sonuc.durum, (sonuc.durum, "soluk"))
            it.setText(1, metin)
            it.setForeground(1, QColor(self.renkler.get(rol, self.renkler["soluk"])))
            if sonuc.mesaj:
                it.setToolTip(1, sonuc.mesaj)
            f = it.font(0)
            f.setBold(False)
            it.setFont(0, f)
        if sonuc.durum == "hata":
            self.akis.appendHtml(f'<span style="color:{self.renkler["tehlike"]}">✕ {html.escape(os.path.basename(sonuc.yol))}: '
                                 f'{html.escape(sonuc.mesaj)}</span>')
        self.dosya_islenen = 0.0
        self.dosya_kalan = 0.0
        self._genel_yenile()

    def _genel_yenile(self):
        n = len(self.dosyalar)
        if not n:
            return
        biten = len(getattr(self, "bitenler", ()))
        oran_dosya = (self.dosya_islenen / self.dosya_toplam) if self.dosya_toplam else 0
        genel = (biten + (0 if self.aktif_sira in getattr(self, "bitenler", ()) else oran_dosya)) / n
        self.genel_cubugu.setValue(int(min(genel, 1) * 1000))
        self.genel_yazi.setText(f"Genel ilerleme: {biten}/{n} dosya")
        # kalan: bu dosyanın kalanı + bekleyenlerin süresi / son hız
        bekleyen = sum((self.sureler.get(y) or 0) for i, y in enumerate(self.dosyalar)
                       if i > self.aktif_sira and i not in self.bitenler)
        if self.son_hiz > 0:
            kalan = self.dosya_kalan + bekleyen / self.son_hiz
            self.c_kalan.yaz(motor.sure(kalan))
        self._baslik_yaz(genel, "Transkript")

    def _baslik_yaz(self, oran, ne):
        if self.is_ is not None:
            self.setWindowTitle(f"%{oran * 100:.0f} · {ne} — {app_info.APP_NAME}")

    def _saat_tik(self):
        if self.is_ is not None:
            self.c_gecen.yaz(motor.sure(time.monotonic() - self.is_basladi))

    def _is_bitti(self, sonuclar, hata):
        self.saat.stop()
        self.is_.wait(2000)
        self.is_ = None
        self.setWindowTitle(app_info.APP_NAME)
        self.sonuclar = sonuclar or []
        gecen = time.monotonic() - self.is_basladi
        say = {}
        for s in self.sonuclar:
            say[s.durum] = say.get(s.durum, 0) + 1
        basarili = say.get("bitti", 0) + say.get("tamamlandi", 0)
        parcalar = [f"{basarili} başarılı"]
        if say.get("atlandi"):
            parcalar.append(f"{say['atlandi']} atlandı")
        if say.get("hata"):
            parcalar.append(f"{say['hata']} hatalı")
        if say.get("iptal"):
            parcalar.append(f"{say['iptal']} iptal")
        islenen = sum(s.sure for s in self.sonuclar if s.durum == "bitti")
        isleme = sum(s.isleme for s in self.sonuclar if s.durum == "bitti")
        parcalar.append(f"toplam süre {motor.sure(gecen)}")
        if islenen and isleme:
            parcalar.append(f"{motor.sure(islenen)} kayıt · ortalama hız ×{islenen / isleme:.1f}")
        self.sonuc_alt.setText(" · ".join(parcalar))
        if hata:
            self.sonuc_durum = "hata"
            self.sonuc_baslik.setText("Beklenmeyen bir hata oluştu")
            self.sonuc_alt.setText(hata.strip().splitlines()[-1])
            _hata_kaydet(hata)
        elif say.get("iptal"):
            self.sonuc_durum = "iptal"
            self.sonuc_baslik.setText("İş iptal edildi")
        elif say.get("hata"):
            self.sonuc_durum = "uyari"
            self.sonuc_baslik.setText("Bazı dosyalar yapılamadı")
        else:
            self.sonuc_durum = "basari"
            self.sonuc_baslik.setText("Transkript tamamlandı")
        self._sonuc_ikonu_ciz()
        self.sonuc_listesi.clear()
        for s in self.sonuclar:
            metin, rol = DURUM_METNI.get(s.durum, (s.durum, "soluk"))
            it = QTreeWidgetItem([os.path.basename(s.yol), metin, motor.sure(s.sure) if s.sure else "—",
                                  str(s.segment) if s.segment else "—"])
            it.setToolTip(0, s.yol)
            if s.mesaj:
                it.setToolTip(1, s.mesaj)
            it.setForeground(1, QColor(self.renkler.get(rol, self.renkler["soluk"])))
            self.sonuc_listesi.addTopLevelItem(it)
        if self.sonuclar:
            secilecek = next((i for i, s in enumerate(self.sonuclar) if s.durum in ("bitti", "tamamlandi")), 0)
            self.sonuc_listesi.setCurrentItem(self.sonuc_listesi.topLevelItem(secilecek))
        self.adima_git(3)
        QApplication.alert(self)

    def _sonuc_ikonu_ciz(self):
        durum = getattr(self, "sonuc_durum", "basari")
        renk = {"basari": self.renkler["basari"], "uyari": self.renkler["uyari"],
                "iptal": self.renkler["soluk"], "hata": self.renkler["tehlike"]}[durum]
        pm = QPixmap(96, 96)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        zemin = QColor(renk)
        zemin.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(zemin)
        p.drawEllipse(QRectF(4, 4, 88, 88))
        p.setPen(QPen(QColor(renk), 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if durum == "basari":
            p.drawPolyline([QPointF(30, 50), QPointF(43, 63), QPointF(67, 36)])
        elif durum == "uyari" or durum == "hata":
            p.drawLine(QPointF(48, 28), QPointF(48, 54))
            p.drawPoint(QPointF(48, 68))
        else:
            p.drawLine(QPointF(34, 48), QPointF(62, 48))
        p.end()
        pm.setDevicePixelRatio(2)
        self.sonuc_ikon.setPixmap(pm)

    def _secili_sonuc(self):
        it = self.sonuc_listesi.currentItem()
        if it is None:
            return None
        i = self.sonuc_listesi.indexOfTopLevelItem(it)
        return self.sonuclar[i] if 0 <= i < len(self.sonuclar) else None

    def _sonuc_secildi(self, *_):
        s = self._secili_sonuc()
        self.kopyalandi.setText("")
        if s is None:
            self.onizleme.setPlainText("")
            return
        self.onizleme_baslik.setText(f"Önizleme — {os.path.basename(s.yol)}")
        if s.durum == "hata":
            self.onizleme.setPlainText(f"Bu dosya yazıya dökülemedi:\n\n{s.mesaj}")
        elif s.durum == "iptal":
            self.onizleme.setPlainText("Bu dosya iptal edildi. Tekrar başlattığınızda kaldığı yerden devam eder.")
        else:
            self.onizleme.setPlainText(_metin_oku(s) or "(çıktı bulunamadı)")
        var = any(os.path.isfile(p) for p in s.ciktilar.values())
        for b in (self.kopyala_btn, self.ac_btn):
            b.setEnabled(var)

    def _metni_kopyala(self):
        s = self._secili_sonuc()
        if s:
            QApplication.clipboard().setText(_duz_metin(s))
            self.kopyalandi.setText("✓ Panoya kopyalandı")

    def _metni_ac(self):
        s = self._secili_sonuc()
        if not s:
            return
        for tur in ("txt", "zamanli", "srt", "vtt"):
            p = s.ciktilar.get(tur)
            if p and os.path.isfile(p):
                os.startfile(p)
                return

    def _klasoru_ac(self):
        s = self._secili_sonuc()
        if not s:
            return
        hedef = next((p for p in s.ciktilar.values() if os.path.isfile(p)), s.yol)
        _klasorde_goster(hedef)

    def yeni_is(self):
        self.dosyalar = []
        self.sonuclar = []
        self.adima_git(0)

    # ---------------------------------------------------------- sürükle-bırak
    def dragEnterEvent(self, e):
        if self.is_ is None and e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.surukle.vurgulu = True
            self.surukle.update()

    def dragLeaveEvent(self, e):
        self.surukle.vurgulu = False
        self.surukle.update()

    def dropEvent(self, e):
        self.surukle.vurgulu = False
        self.surukle.update()
        yollar = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if self.adim == 3:
            self.dosyalar = []
        self.dosya_ekle(yollar)

    def closeEvent(self, e):
        if self.is_ is not None:
            cevap = QMessageBox.question(self, "Çıkılsın mı?",
                                         "Transkript devam ediyor. Çıkarsanız şu anki dosya yarım kalır "
                                         "(sonra kaldığı yerden devam edebilirsiniz).",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if cevap != QMessageBox.Yes:
                e.ignore()
                return
            self.is_.iptal.set()
            self.hide()
            self.is_.wait(15000)
        self._ayarlari_kaydet()
        e.accept()


# ------------------------------------------------------------------ başlatma

def _hata_kaydet(metin):
    try:
        with open(os.path.join(motor.veri_klasoru(), "hata.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + metin + "\n\n")
    except Exception:
        pass


def _uygulama():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DemiralpOzturk.VideoTranskript")
    except Exception:
        pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(app_info.APP_NAME)
    app.setApplicationVersion(app_info.VERSION)
    app.setOrganizationName(app_info.CREATOR)
    app.setStyle("Fusion")
    f = QFont("Segoe UI", 10)
    app.setFont(f)
    app.setWindowIcon(QIcon(ikon_ciz(256)))
    return app


def calistir_arayuz(dosyalar=None):
    app = _uygulama()

    def istisna(tur, deger, iz):
        metin = "".join(traceback.format_exception(tur, deger, iz))
        _hata_kaydet(metin)
        QMessageBox.critical(None, app_info.APP_NAME, f"Beklenmeyen hata:\n{deger}\n\nAyrıntı: hata.log")

    sys.excepthook = istisna
    pencere = AnaPencere()
    pencere.show()
    if dosyalar:
        pencere.dosya_ekle(dosyalar)
    return app.exec()


def ekran_goruntuleri(hedef, dosya=None):
    """Pencere açmadan (offscreen) her adımın ekran görüntüsünü alır; uçtan uca arayüz testi."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if os.environ["QT_QPA_PLATFORM"] == "offscreen":
        os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    hedef = os.path.abspath(hedef)
    os.makedirs(hedef, exist_ok=True)
    app = _uygulama()
    gecici = tempfile.mkdtemp(prefix="vt_ekran_")
    if not dosya:
        from deneme import ornek_ses_uret
        dosya = os.path.join(gecici, "Toplantı kaydı.wav")
        ornek_ses_uret(dosya)
    pencere = AnaPencere(ayar_dosyasi=os.path.join(gecici, "ayarlar.ini"))
    pencere.tema_secimi = "acik"
    pencere.tema_uygula()
    pencere.resize(1180, 780)
    pencere.show()
    sonuc = {"kod": 1, "kareler": []}

    def bekle(ms):
        son = time.monotonic() + ms / 1000
        while time.monotonic() < son:
            app.processEvents()
            time.sleep(0.01)

    def kaydet(ad, w=None, olaylari_isle=True):
        if olaylari_isle:
            app.processEvents()
        yol = os.path.join(hedef, ad)
        (w or pencere).grab().save(yol)
        sonuc["kareler"].append(yol)
        print("ekran görüntüsü:", yol, flush=True)

    pencere.dosya_ekle([dosya])
    bekle(1500)
    kaydet("1-dosya-sec.png")
    pencere.adima_git(1)
    bekle(300)
    kaydet("2-ayarlar.png")  # varsayılan ayarlar
    # deneme çıktıları geçici klasöre; her seferinde yeniden yazıya dök
    pencere.konum_yolu.setText(gecici)
    pencere.konum_klasor.setChecked(True)
    pencere.atla.setChecked(False)

    alindi = {"ara": False}

    def segment_geldi(sira, *_):
        if sira == 3 and not alindi["ara"]:
            alindi["ara"] = True
            kaydet("3-transkript.png", olaylari_isle=False)  # iş bitmeden, o anki hâliyle

    pencere.baslat_is()
    pencere.is_.segmentS.connect(segment_geldi)
    zaman_siniri = time.monotonic() + 600
    while pencere.is_ is not None and time.monotonic() < zaman_siniri:
        app.processEvents()
        time.sleep(0.02)
    bekle(500)
    if not alindi["ara"]:
        pencere.yigin.setCurrentIndex(2)
        kaydet("3-transkript.png")
        pencere.yigin.setCurrentIndex(3)
    kaydet("4-sonuc.png")
    pencere.tema_secimi = "koyu"
    pencere.tema_uygula()
    bekle(300)
    kaydet("4-sonuc-koyu.png")
    pencere.adima_git(3)
    pencere.yigin.setCurrentIndex(2)
    pencere.adimlar.ayarla(2)
    bekle(200)
    kaydet("3-transkript-koyu.png")
    pencere.tema_secimi = "acik"
    pencere.tema_uygula()
    hk = HakkindaPenceresi(pencere, pencere.renkler)
    hk.show()
    bekle(300)
    kaydet("hakkinda.png", hk)
    hk.close()
    durumlar = [s.durum for s in pencere.sonuclar]
    print("sonuç durumları:", durumlar, flush=True)
    sonuc["kod"] = 0 if durumlar and all(d == "bitti" for d in durumlar) else 1
    pencere.is_ = None
    pencere.close()
    return sonuc["kod"]
