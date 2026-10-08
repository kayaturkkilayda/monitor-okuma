"""Görüntüyü küçültüp ayrı bir pencerede gösterme (Kameralar ve Kayıtlar sekmeleri ortak kullanır)."""
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk      # AVIF desteği Pillow 12 ile birlikte gelir

EN_BUYUK = (800, 600)


def onizleme_ac(ust, goruntu: Image.Image, baslik: str) -> tk.Toplevel:
    pencere = tk.Toplevel(ust)
    pencere.title(f"{baslik}  |  {goruntu.width}x{goruntu.height}")
    kucuk = goruntu.copy()
    kucuk.thumbnail(EN_BUYUK)
    foto = ImageTk.PhotoImage(kucuk)
    etiket = ttk.Label(pencere, image=foto)
    etiket.image = foto      # referansı tut; yoksa Python resmi siler ve pencere boş kalır
    etiket.pack(padx=10, pady=10)
    return pencere
