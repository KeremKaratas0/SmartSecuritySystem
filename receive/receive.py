import time
import psutil
import pyautogui
import keyboard
import pygetwindow as gw
import subprocess
from pywinauto import Application,timings

def is_fsquirt_running():
    return any('fsquirt' in (p.info['name'] or '').lower() for p in psutil.process_iter(['name']))


print("Starting Bluetooth file receive automation.")
print("Press Ctrl+Esc to stop.")


try:
    while True:
        if keyboard.is_pressed('ctrl+esc'):
            print("Exiting loop.")
            break

        time.sleep(1)
        app = Application(backend="uia").start(r"C:\Windows\System32\fsquirt.exe")
        dlg=app.top_window()
        dlg.wait('visible')
        pyautogui.press('tab')
        pyautogui.press('enter')
        while not any(b.is_enabled() and b.is_visible() for b in dlg.descendants(control_type='List')):
            time.sleep(1)
        time.sleep(1)
        pyautogui.press('enter')

        time.sleep(2)

except KeyboardInterrupt:
    print("Interrupted manually.")

