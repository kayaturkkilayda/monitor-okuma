"""Uzun süren işi (mail gönderme, kameradan görüntü alma) pencereyi dondurmadan çalıştırma.

Tkinter pencerelerine yalnızca ana iş parçacığından dokunulmalı. Bu yüzden arka plandaki iş
pencereye hiç erişmez, yalnızca sonucunu bırakır; ana iş parçacığı kısa aralıklarla
"bitti mi?" diye bakar ve sonucu pencereye kendisi yansıtır.
"""
import threading


def arka_planda(pencere, is_, bitince, aralik_ms: int = 100):
    """is_() ayrı iş parçacığında çalışır; bitince(sonuc) ana iş parçacığında çağrılır.

    is_ kendi hatalarını yakalayıp sonuç olarak döndürmeli; yine de beklenmedik bir hatayla
    biterse bitince(None) çağrılır, pencere "bekliyor" hâlinde takılı kalmaz.
    """
    sonuc = {}

    def calis():
        try:
            sonuc["deger"] = is_()
        except Exception:
            pass                 # kontrol() iş parçacığının değersiz bittiğini görür, bitince(None)

    is_parcacigi = threading.Thread(target=calis, daemon=True)
    is_parcacigi.start()

    def kontrol():
        if "deger" in sonuc:
            bitince(sonuc["deger"])
        elif is_parcacigi.is_alive():
            pencere.after(aralik_ms, kontrol)
        else:
            bitince(None)

    pencere.after(0, kontrol)
