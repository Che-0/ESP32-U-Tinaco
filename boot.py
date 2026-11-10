import network
import time

SSID = "TU_SSID"
PASSWORD = "TU_PASSWORD"

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
try:
    wlan.config(pm=network.WLAN.PM_NONE) # Desactivar ahorro para evitar cortes
    wlan.config(txpower=17)
except:
    pass

# Fijar IP estática antes del handshake
wlan.ifconfig(("192.168.68.200", "255.255.255.0", "192.168.68.1", "8.8.8.8"))

if not wlan.isconnected():
    print(f"Conectando a {SSID}...")
    wlan.connect(SSID, PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)
