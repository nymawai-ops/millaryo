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

# Cada cuánto revisar (en segundos)
INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", "1800"))  # 30 min por defecto

app = Flask(__name__)

# Estado para consulta desde /status
estado = {
    "ultimo_error": None,
    "ultimo_check_ts": None,
    "ultimos_precios": [],  # lista de precios
}

# Historial simple en memoria: última lista de precios (ordenada)
last_prices = None


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


def extraer_precios(html: str):
    """
    Extrae TODOS los precios tipo 'S/ 1499.00' del HTML.
    Devuelve una lista de floats (sin repetir, ordenada).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    # Buscar cualquier 'S/ <numero>'
    patron = re.compile(r"S/\s*([\d\.]+)")
    precios = []

    for match in patron.finditer(text):
        valor = match.group(1)
        try:
            precio = float(valor)
        except ValueError:
            continue

        # Filtrar basura (0 o muy bajos)
        if precio < 10:
            continue

        precios.append(precio)

    # Quitar duplicados y ordenar
    precios_unicos = sorted(set(precios))
    return precios_unicos


def obtener_precios():
    """
    Descarga la página y devuelve la lista de precios encontrados.
    """
    resp = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resp.raise_for_status()

    precios = extraer_precios(resp.text)
    if not precios:
        raise ValueError("No se encontraron precios en la página.")

    return precios


def monitorear():
    """
    Bucle infinito que revisa la página cada cierto tiempo
    y solo envía mensaje a Telegram cuando la lista de precios
    cambia respecto a la revisión anterior.
    """
    global last_prices

    try:
        enviar_mensaje("🚀 Bot de precios iniciado (envía lista solo si cambian).")
    except Exception as e:
        print("Error enviando mensaje inicial:", e)

    while True:
        try:
            precios = obtener_precios()

            ahora = time.time()
            estado["ultimo_check_ts"] = ahora
            estado["ultimo_error"] = None
            estado["ultimos_precios"] = precios

            print("[DEBUG] Precios encontrados:", precios)

            # Representamos la lista como tupla para compararla fácilmente
            precios_tuple = tuple(precios)

            # Si es la primera vez o si cambió la lista, enviamos alerta
            if last_prices is None or precios_tuple != last_prices:
                last_prices = precios_tuple

                lineas = [f"S/ {p}" for p in precios]
                mensaje = (
                    "📊 Lista de precios actualizados en la página:\n\n"
                    f"URL: {URL}\n\n" +
                    "\n".join(lineas)
                )

                enviar_mensaje(mensaje)

        except Exception as e:
            print("Error en monitorear:", e)
            estado["ultimo_error"] = str(e)
            try:
                enviar_mensaje(f"❌ Error al revisar precios: {e}")
            except Exception:
                pass

        time.sleep(INTERVALO_SEGUNDOS)


# ========= RUTAS WEB PARA RENDER =========

@app.route("/")
def home():
    return "Bot de precios Claro corriendo 🔍 (lista solo si cambian)", 200


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
