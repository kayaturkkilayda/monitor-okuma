"""Yatak QR kodunu gösteren pencere.

QR yalnızca o yatağın adresini taşır; şifre ya da hasta bilgisi içermez. Bu yüzden
yazdırılıp yatak başına asılabilir. Adresi açan kişiden ayrıca giriş istenir.
"""
import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import qr_kod
import tema

GRI = "#5f6b7a"


class QrPenceresi(tk.Toplevel):
    """kamera: QR'ı gösterilecek kamera. port: telefon sunucusunun portu."""

    def __init__(self, ust, kamera: dict, port: int, acik: bool, ip: str | None = None):
        super().__init__(ust)
        self.kamera = kamera
        self.ip = ip or qr_kod.yerel_ip()
        self.adres = qr_kod.yatak_adresi(self.ip, kamera["kod"], port)

        self.title(f"{kamera['kod']} → {kamera['yatak']} QR")
        self.resizable(False, False)
        self.transient(ust)

        govde = ttk.Frame(self, padding=18)
        govde.pack(fill="both", expand=True)

        ttk.Label(govde, text=f"{kamera['kod']} → {kamera['yatak']}",
                  font=(tema.AILE, tema.BUYUK, "bold")).pack()
        ttk.Label(govde, text="Telefonla okutup monitör fotoğrafı gönderin",
                  foreground=GRI).pack(pady=(0, 12))

        self.resim = self._qr_resmi()
        ttk.Label(govde, image=self.resim).pack()

        ttk.Label(govde, text=self.adres, foreground=GRI,
                  font=tema.TEK_ARALIK_YAZI).pack(pady=(10, 0))

        if not acik:
            ttk.Label(govde, text="Telefon yükleme KAPALI. Ayarlar sekmesinden açın.",
                      foreground="#b00020",
                      wraplength=tema.sarma_genisligi(300)).pack(pady=(10, 0))

        dugmeler = ttk.Frame(govde)
        dugmeler.pack(pady=(14, 0))
        ttk.Button(dugmeler, text="PNG olarak kaydet", command=self._kaydet).pack(side="left", padx=4)
        ttk.Button(dugmeler, text="Kapat", command=self.destroy).pack(side="left", padx=4)

    def _qr_resmi(self, olcek: int = 7) -> ImageTk.PhotoImage:
        tampon = BytesIO()
        qr_kod.qr_uret(self.adres).save(tampon, kind="png", scale=olcek, border=3)
        tampon.seek(0)
        with Image.open(tampon) as resim:
            return ImageTk.PhotoImage(resim.convert("RGB"))

    def _kaydet(self):
        varsayilan = f"QR_{self.kamera['kod']}_{self.kamera['yatak']}.png"
        yol = filedialog.asksaveasfilename(
            parent=self, title="QR'ı kaydet", defaultextension=".png",
            initialfile=varsayilan, filetypes=[("PNG resmi", "*.png")])
        if not yol:
            return
        try:
            qr_kod.png_kaydet(self.adres, Path(yol), self.kamera)
        except OSError as e:
            messagebox.showerror("Kaydedilemedi", str(e), parent=self)
            return
        messagebox.showinfo("Kaydedildi", f"QR kaydedildi:\n{yol}\n\n"
                                          "Yazdırıp yatak başına asabilirsiniz.", parent=self)
