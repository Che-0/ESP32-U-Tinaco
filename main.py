# Archivo: main.py
import network
import socket
import time
import json
import urequests
import gc
import machine
from machine import Pin, time_pulse_us

# --- CONFIGURACIÓN WI-FI Y NTFY ---
SSID = "TU_SSID"
PASSWORD = "TU_PASSWORD_AQUI"
NTFY_TOPIC = "TU_TOPICO_DE_NTFY"
OTA_PASS = "1234"  # Contraseña para actualizar por curl 

# --- PARÁMETROS REALES DE TU ROTOPLAS ---
DIST_VACIO_CM = 130.0   # Altura del sensor al fondo (vacío)
DIST_LLENO_CM = 30.0    # Distancia del sensor al agua cuando llega a 100 cm
CAPACIDAD_LITROS = 1000 # ~6 tambos útiles

# --- PINES DEL SENSOR ---
trig = Pin(5, Pin.OUT)
echo = Pin(18, Pin.IN)

# Estados de alertas y monitoreo
alerta_baja_enviada = False
alerta_lleno_enviada = False
ultimo_chequeo = 0
estado_actual = {"error": True, "distancia_cm": 0, "porcentaje": 0, "litros": 0}

def enviar_ntfy(mensaje, titulo="Monitor Tinaco", prioridad="default"):
    try:
        gc.collect()
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {"Title": titulo, "Priority": prioridad}
        res = urequests.post(url, data=mensaje.encode('utf-8'), headers=headers)
        res.close()
        print(f"Notificación enviada a ntfy ({NTFY_TOPIC}): {mensaje}")
    except Exception as e:
        print("Error enviando a ntfy:", e)

def verificar_alertas(datos):
    global alerta_baja_enviada, alerta_lleno_enviada
    if datos["error"]:
        return

    pct = datos["porcentaje"]
    litros = datos["litros"]

    # 1. Alerta por nivel bajo (<= 20%)
    if pct <= 20.0 and not alerta_baja_enviada:
        enviar_ntfy(f"Agua baja: queda {pct}% ({litros} L).", "Alerta Tinaco Bajo", "high")
        alerta_baja_enviada = True
    elif pct >= 30.0:
        alerta_baja_enviada = False

    # 2. Aviso de tinaco lleno (>= 95%)
    if pct >= 95.0 and not alerta_lleno_enviada:
        enviar_ntfy(f"Tinaco lleno al {pct}% ({litros} L).", "Tinaco Lleno", "default")
        alerta_lleno_enviada = True
    elif pct <= 85.0:
        alerta_lleno_enviada = False

def medir_distancia_cm():
    trig.value(0)
    time.sleep_us(5)
    trig.value(1)
    time.sleep_us(20)
    trig.value(0)
    duracion = time_pulse_us(echo, 1, 35000)
    if duracion < 0:
        return None
    return (duracion * 0.0343) / 2

def obtener_datos_tinaco(muestras=5):
    lecturas = []
    for _ in range(muestras):
        d = medir_distancia_cm()
        if d is not None and d > 19.0:
            lecturas.append(d)
        time.sleep_ms(40)
        
    if not lecturas:
        return {"error": True, "distancia_cm": 0, "porcentaje": 0, "litros": 0}
        
    lecturas.sort()
    dist = round(lecturas[len(lecturas) // 2], 1)
    
    rango_util = DIST_VACIO_CM - DIST_LLENO_CM
    altura_agua = DIST_VACIO_CM - dist
    porcentaje = max(0.0, min(100.0, (altura_agua / rango_util) * 100.0))
    litros = int((porcentaje / 100.0) * CAPACIDAD_LITROS)
    
    return {
        "error": False,
        "distancia_cm": dist,
        "porcentaje": round(porcentaje, 1),
        "litros": litros
    }

def asegurar_wifi():
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"[main.py] Usando conexión de boot.py -> http://{ip}")
        return ip
        
    wlan.active(True)
    wlan.ifconfig(("192.168.68.200", "255.255.255.0", "192.168.68.1", "8.8.8.8"))
    wlan.connect(SSID, PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)
    ip = wlan.ifconfig()[0]
    print(f"[main.py] Conectado -> http://{ip}")
    return ip

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitor Rotoplas</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; text-align: center; padding: 20px; }
        .card { max-width: 360px; margin: auto; background: #1e293b; padding: 24px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        .tank { width: 140px; height: 200px; border: 4px solid #94a3b8; border-radius: 20px 20px 8px 8px; margin: 20px auto; position: relative; overflow: hidden; background: #0f172a; }
        .water { width: 100%; bottom: 0; position: absolute; background: linear-gradient(180deg, #38bdf8, #0284c7); transition: height 0.6s ease; height: 0%; }
        .stat { font-size: 2rem; font-weight: bold; margin: 10px 0; }
        .sub { color: #94a3b8; font-size: 0.95rem; }
        .btn { margin-top: 16px; padding: 10px 16px; background: #0284c7; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Nivel del Tinaco</h2>
        <div class="tank"><div class="water" id="water"></div></div>
        <div class="stat" id="pct">-- %</div>
        <div class="sub" id="litros">-- Litros</div>
        <div class="sub" id="dist" style="margin-top:8px;">Distancia sensor: -- cm</div>
        <button class="btn" onclick="probarNtfy()">Probar alerta ntfy</button>
    </div>
    <script>
        async function actualizar() {
            try {
                const res = await fetch('/api');
                const data = await res.json();
                if (!data.error) {
                    document.getElementById('water').style.height = data.porcentaje + '%';
                    document.getElementById('pct').innerText = data.porcentaje + ' %';
                    document.getElementById('litros').innerText = data.litros + ' L aprox.';
                    document.getElementById('dist').innerText = 'Distancia sensor: ' + data.distancia_cm + ' cm';
                } else {
                    document.getElementById('dist').innerText = 'Sensor fuera de rango';
                }
            } catch (e) { console.error(e); }
        }
        async function probarNtfy() {
            await fetch('/test-ntfy');
            alert('Notificación de prueba enviada a tu celular');
        }
        setInterval(actualizar, 3000);
        actualizar();
    </script>
</body>
</html>
"""

# --- ARRANQUE DEL SISTEMA ---
ip = asegurar_wifi()
estado_actual = obtener_datos_tinaco()
enviar_ntfy(
    f"ESP32 en línea (http://{ip}). Nivel actual: {estado_actual['porcentaje']}% ({estado_actual['litros']} L)",
    "Sistema Iniciado"
)

addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(5)
s.settimeout(1.0)

# --- BUCLE PRINCIPAL (WHILE TRUE) ---
while True:
    # 1. Revisión automática cada 60 segundos aunque nadie abra la web
    ahora = time.ticks_ms()
    if time.ticks_diff(ahora, ultimo_chequeo) > 60000:
        estado_actual = obtener_datos_tinaco()
        verificar_alertas(estado_actual)
        ultimo_chequeo = ahora

    # 2. Servidor Web y Actualizador OTA
    try:
        cl, addr = s.accept()
        cl.settimeout(3.0)
        request = cl.recv(1024)
        
        if f"POST /ota?pass={OTA_PASS}".encode() in request:
            partes = request.split(b"\r\n\r\n", 1)
            headers = partes[0].decode('utf-8', 'ignore')
            cuerpo = partes[1] if len(partes) > 1 else b""
            
            largo_total = 0
            for linea in headers.split("\r\n"):
                if linea.lower().startswith("content-length:"):
                    largo_total = int(linea.split(":")[1].strip())
                    
            while len(cuerpo) < largo_total:
                cuerpo += cl.recv(1024)
                
            if len(cuerpo) > 50:
                with open("main.py", "wb") as f:
                    f.write(cuerpo)
                cl.send(b"HTTP/1.1 200 OK\r\n\r\nActualizado OK. Reiniciando...\n")
                cl.close()
                time.sleep(0.5)
                machine.reset()
            else:
                cl.send(b"HTTP/1.1 400 Bad Request\r\n\r\nArchivo vacio\n")
                
        elif b"GET /api" in request:
            estado_actual = obtener_datos_tinaco()
            verificar_alertas(estado_actual)
            respuesta = json.dumps(estado_actual)
            cl.send("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + respuesta)
            
        elif b"GET /test-ntfy" in request:
            enviar_ntfy(
                f"Prueba manual: Tinaco al {estado_actual['porcentaje']}% ({estado_actual['litros']} L)",
                "Prueba desde Web"
            )
            cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nOK")
            
        elif b"GET /reboot" in request:
            cl.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nReiniciando...")
            cl.close()
            time.sleep(0.5)
            machine.reset()
            
        else:
            cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + HTML_PAGE)
            
        cl.close()
    except OSError:
        # Pasa cada 1 segundo cuando no hay visitas en la web
        pass
    except Exception as e:
        try:
            cl.close()
        except:
            pass