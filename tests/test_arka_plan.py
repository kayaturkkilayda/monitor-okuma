import threading
import time

from arka_plan import arka_planda


def _bekle(pencere, kosul, sn=3):
    bitis = time.time() + sn
    while not kosul() and time.time() < bitis:
        pencere.update()
        time.sleep(0.02)


def test_sonuc_ana_is_parcaciginda_verilir(tk_kok):
    gelen = []
    arka_planda(tk_kok, lambda: (time.sleep(0.2), threading.current_thread().name)[1],
                lambda sonuc: gelen.append((sonuc, threading.current_thread() is threading.main_thread())),
                aralik_ms=20)
    _bekle(tk_kok, lambda: gelen)
    (sonuc, ana_mi), = gelen
    assert sonuc != threading.main_thread().name      # iş arka planda çalıştı
    assert ana_mi                                     # sonuç ana iş parçacığında geldi


def test_is_beklenmedik_hatayla_biterse_none(tk_kok):
    gelen = []

    def bozuk():
        raise RuntimeError("beklenmedik")

    arka_planda(tk_kok, bozuk, gelen.append, aralik_ms=20)
    _bekle(tk_kok, lambda: gelen)
    assert gelen == [None]
