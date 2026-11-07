"""A bounded Windows sound and dismissible alarm window, independent of browser."""
import sys

if __name__ == '__main__' and sys.platform == 'win32':
    import ctypes
    import threading
    import winsound
    kind = sys.argv[1] if len(sys.argv)>1 else ''
    text = '잠자리에 들 시간입니다.' if kind == 'bedtime' else '일어날 시간입니다.'
    timer = threading.Timer(60,lambda: winsound.PlaySound(None,0))
    timer.daemon = True
    try:
        winsound.PlaySound('SystemExclamation',winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_LOOP)
        timer.start()
        ctypes.windll.user32.MessageBoxW(0,text+'\n확인을 누르면 알람 소리가 멈춥니다.','달잠 알람',0x40 | 0x10000)
    finally:
        timer.cancel()
        winsound.PlaySound(None,0)
