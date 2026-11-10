# ESP32-U-Tinaco
Proyecto para monitorear la cantidad de agua de un rotoplas

# 🚰 Monitor de Nivel de Tinaco IoT con ESP32 y MicroPython

Sistema embebido de bajo costo para el monitoreo en tiempo real de niveles de agua en tinacos residenciales (Rotoplas / Rotomex). Integra medición ultrasónica impermeable, filtrado estadístico de rebotes, dashboard web responsivo servido directamente desde el microcontrolador, notificaciones push automáticas al celular (vía **ntfy**) y soporte de actualización de firmware por red (**OTA vía HTTP cURL**).

---

## 📸 Arquitectura y Prototipo

* **Sensor:** Ultrasónico impermeable JSN-SR04T (aislado de humedad por condensación).
* **Controlador:** ESP32-WROOM-32U con antena coaxial externa reciclada de laptop (banda 2.4 GHz).
* **Alimentación:** Fuente regulada a 5V mediante Base Shield acoplada a red eléctrica local.
* **Carcasa:** Enclosure reciclado de doble cámara plástica con salida inferior de cables ("cuello de ganso" antigoteo).

---

## 🛠️ Especificaciones Técnicas y Materiales

| Componente | Función | Notas / Consideraciones |
| :--- | :--- | :--- |
| **ESP32-WROOM-32U** | Microcontrolador central (Dual-core, Wi-Fi 2.4 GHz) | Requiere antena externa obligatoria mediante conector U.FL / IPEX. |
| **JSN-SR04T V2.0 / V3.0** | Sensor de distancia ultrasónico impermeable | Transductor sellado para intemperie; electrónica en interior protegido. Zona muerta: ~20-25 cm. |
| **Base Shield de expansión (5V/3.3V)** | Distribución de potencia y desacoplo de corriente | Provee 5V estables para el pulso del transductor ultrasónico y el handshake Wi-Fi. |
| **Antena Wi-Fi U.FL** | Recepción de radiofrecuencia (2.4 GHz) | Rescatada de pantalla de laptop vieja; ganancia de ~3-5 dBi. |
| **Divisor de Tensión (1 kΩ / 2 kΩ)** | Adaptación de nivel lógico 5V -> 3.3V | Protege el GPIO de recepción del ESP32 frente a los pulsos del pin `Echo`. |
| **Enclosure plástico** | Protección intemperie (lluvia / radiación solar) | Montado a la sombra en pata metálica de base de tinaco. |

---

## 📐 Calibración Geométrica y Punto Ciego

Los sensores ultrasónicos impermeables presentan una zona de bloqueo acústico (zona muerta) de entre **20 y 25 cm**. Para garantizar lecturas fiables sin falseo al 100%:

* **Altura total ($D_{\text{vacío}}$):** $130\text{ cm}$ (distancia del sensor montado en la tapa al fondo del tinaco).
* **Distancia a lleno ($D_{\text{lleno}}$):** $30\text{ cm}$ (cuando el agua llega a los $100\text{ cm}$ de tirante hidráulico cortado por el flotador).
* **Margen de seguridad:** $130\text{ cm} - 100\text{ cm} = 30\text{ cm} > 25\text{ cm}$ (elimina completamente el problema de la zona muerta).
* **Capacidad útil calibrada:** $\approx 1000\text{ L}$ (Rotomex / Rotoplas Super Reforzado).

### Fórmula de Nivel:
$$\text{Porcentaje} = \left( \frac{D_{\text{vacío}} - \text{Distancia}_{\text{medida}}}{D_{\text{vacío}} - D_{\text{lleno}}} \right) \times 100$$
$$\text{Litros} = \left( \frac{\text{Porcentaje}}{100} \right) \times \text{Capacidad}_{\text{útil}}$$

---

## 🔌 Diagrama de Conexiones

```
        +-----------------------------------------+
        |                ESP32                    |
        |                                         |
        |   GPIO 5  -----------------> Trig       | (JSN-SR04T)
        |                                         |
        |   GPIO 18 <---+             Echo        | (JSN-SR04T)
        |               |              |          |
        |             [1kΩ]            |          |
        |               +--------------+          |
        |               |                         |
        |             [2kΩ]                       |
        |               |                         |
        |   GND --------+------------> GND        | (JSN-SR04T & Base)
        |   5V / VIN <---------------- 5V         | (Base Shield)
        +-----------------------------------------+
```

---

## 💻 Estructura del Software

El firmware está desarrollado en **MicroPython** y dividido en dos scripts para desacoplar la inicialización de red y el bucle principal de control:

### 1. `boot.py` (Asignación de IP Estática y Red)
Garantiza conexión inmediata y asigna una dirección estática (`192.168.68.200`) conservando la puerta de enlace y DNS público para llamadas a APIs externas:

```python
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
```

### 2. `main.py` (Filtrado de Lecturas, Dashboard Web y OTA)
* **Filtro de Mediana:** Realiza 5 lecturas consecutivas con retardos de disipación de eco para descartar turbulencias u ondas en la superficie del agua.
* **Servidor HTTP no bloqueante:** Escucha peticiones con timeout de 1 segundo para alternar entre atender clientes web y evaluar periódicamente las condiciones de alerta.
* **Alertas Push (ntfy):** Emite notificaciones automáticas al celular si el nivel baja del 20% o supera el 95%.
* **Actualización Remota (OTA):** Expone un endpoint `POST /ota?pass=1234` que sobreescribe `main.py` y reinicia el sistema mediante `machine.reset()`.

---

## 🚀 Despliegue y Mantenimiento Remoto

### Actualizar código por Wi-Fi (Sin cables):
Desde la computadora conectada a la misma red local:

```bash
curl -X POST --data-binary @main.py "http://192.168.68.200/ota?pass=1234"
```

El ESP32 responderá `Actualizado OK. Reiniciando...` y enviará una notificación push a **ntfy** confirmando el reinicio del sistema con la versión actualizada.

---

## 🔒 Buenas Prácticas de Instalación Física en Azotea

1. **Perforación centrada:** Broca sacabocados de $22\text{ mm}$ (7/8") en la parte plana de la tapa para que el cono ultrasónico apunte perpendicular a la superficie.
2. **Cámara de goteo:** Orientar la boquilla de salida de cables siempre hacia abajo; realizar una curva en "U" antes del ingreso al contenedor.
3. **Disipación térmica:** Separar la Base Shield y el ESP32 mediante separadores plásticos o rieles rígidos, evitando el uso de espumas aislantes o fomi alrededor de las etapas de potencia.
