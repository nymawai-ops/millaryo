import os
import time
import re
import threading

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

# === CONFIG DESDE VARIABLES DE ENTORNO ===
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
URL = os.environ.get("URL_CLARO", "https://www.tiendaclaro.pe/apple")

# Detectar bajadas fuertes:
# - ALERT_PCT_DROP: porcentaje mínimo de caída (0.3 = 30%)
# - ALERT_MIN_DROP: caída mínima en soles
ALERT_PCT_DROP = float(os.environ.get("ALERT_PCT_DROP", "0.3"))
ALERT_MIN_DROP = float(os.environ.get("ALERT_MIN_DROP", "300.0"))

INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", "1800"))  # 30 min

app = Flask(__name__)

# Estado para /status
estado = {
    "ultimo_error": None,
    "ultimo_check_ts": None,
    "ultimos_precios": {},  # name -> price
}

# Historial en memoria: modelo -> último precio visto
last_prices = {}


def enviar_mensaje(msg: str):
    """
    Envía un mensaje de texto al chat de Telegram usando la API HTTP.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": msg,
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()


def extraer_iphones(html: str):
    """
    Extrae modelos de iPhone y su precio a partir del texto de la página.
    Busca patrones como:
        'iPhone 13 128 GB ... S/ 1479.00'
    Devuelve una lista de:
        {"name": "iPhone 13 128 GB", "price": 1479.0}
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    # Captura líneas con 'iPhone ... S/ precio'
    patron = re.compile(r"(iPhone[^\n]*?)S/\s*([\d\.]+)")

    ofertas = []

    for match in patron.finditer(text):
        segmento = match.group(1)
        precio_str = match.group(2)

        try:
            precio = float(precio_str)
        except ValueError:
            continue

        if precio < 10:
            # ignorar cosas como S/ 0.00, S/ 1.00, etc.
            continue

        nombre = segmento
        nombre = nombre.replace("Desde", "")
        nombre = re.sub(r"\s+", " ", nombre).strip()

        ofertas.append(
            {
                "name": nombre,
                "price": precio,
            }
        )

    return ofertas


def obtener_ofertas_iphones():
    """
    Descarga la página y devuelve las ofertas de iPhones (modelo + precio).
    """
    resp = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resp.raise_for_status()

    ofertas = extraer_iphones(resp.text)
    if not ofertas:
        raise ValueError("No se encontraron iPhones con precio en la página.")

    return ofertas


def monitorear():
    """
    Bucle infinito que revisa la página cada cierto tiempo
    y manda alerta cuando detecta una bajada fuerte de precio
    en cualquier modelo de iPhone.
    """
    global last_prices

    try:
        enviar_mensaje(
            "🚀 Bot de iPhones iniciado (detección de bajadas fuertes de precio)."
        )
    except Exception as e:
        print("Error enviando mensaje inicial:", e)

    while True:
        try:
            ofertas = obtener_ofertas_iphones()

            ahora = time.time()
            estado["ultimo_check_ts"] = ahora
            estado["ultimo_error"] = None
            estado["ultimos_precios"] = {o["name"]: o["price"] for o in ofertas}

            print("[DEBUG] Ofertas iPhone encontradas:")
            for o in ofertas:
                print(f" - {o['name']} | S/ {o['price']}")

            bajadas = []

            for o in ofertas:
                nombre = o["name"]
                precio_nuevo = o["price"]
                precio_anterior = last_prices.get(nombre)

                if precio_anterior is not None:
                    drop_abs = precio_anterior - precio_nuevo
                    drop_pct = drop_abs / precio_anterior if precio_anterior > 0 else 0.0

                    if drop_abs >= ALERT_MIN_DROP or drop_pct >= ALERT_PCT_DROP:
                        bajadas.append(
                            {
                                "name": nombre,
                                "old": precio_anterior,
                                "new": precio_nuevo,
                                "drop_abs": drop_abs,
                                "drop_pct": drop_pct,
                            }
                        )

                # Actualizar historial siempre
                last_prices[nombre] = precio_nuevo

            if bajadas:
                lineas = []
                for b in bajadas:
                    pct = round(b["drop_pct"] * 100, 1)
                    lineas.append(
                        f"- {b['name']}: de S/ {b['old']} a S/ {b['new']} "
                        f"(bajó S/ {round(b['drop_abs'],1)} ≈ {pct}%)"
                    )

                mensaje = (
                    "📉 ¡Bajada fuerte de precio en iPhones!\n\n"
                    f"URL: {URL}\n"
                    f"Condición: caída ≥ S/ {ALERT_MIN_DROP} "
                    f"o ≥ {int(ALERT_PCT_DROP * 100)}%\n\n"
                    + "\n".join(lineas)
                )
                enviar_mensaje(mensaje)

        except Exception as e:
            print("Error en monitorear:", e)
            estado["ultimo_error"] = str(e)
            try:
                enviar_mensaje(f"❌ Error al revisar iPhones: {e}")
            except Exception:
                pass

        time.sleep(INTERVALO_SEGUNDOS)


# ========= RUTAS WEB PARA RENDER =========

@app.route("/")
def home():
    return "Bot de iPhones Claro corriendo 🔍 (bajadas fuertes)", 200


@app.route("/status")
def status():
    return jsonify(estado), 200


def iniciar_bot_en_hilo():
    hilo = threading.Thread(target=monitorear, daemon=True)
    hilo.start()


if __name__ == "__main__":
    iniciar_bot_en_hilo()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
