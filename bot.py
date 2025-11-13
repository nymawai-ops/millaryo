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
PRECIO_UMBRAL = float(os.environ.get("PRECIO_UMBRAL", "500.0"))
INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", "1800"))  # 30 min por defecto

app = Flask(__name__)

# Usaremos esto solo para ver el último estado desde los logs
estado = {
    "ultimo_precio_minimo": None,
    "ultima_lista_precios": [],
    "ultimo_error": None,
}


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


def obtener_precios(html: str):
    """
    Busca textos con 'S/' y extrae los números como float.
    Filtra valores 0 o muy bajos (ej: < 10) para evitar valores basura.
    """
    soup = BeautifulSoup(html, "html.parser")
    textos = soup.find_all(string=re.compile(r"S/"))
    precios = []

    for t in textos:
        match = re.search(r"S/\s*([\d\.]+)", t)
        if match:
            valor = match.group(1)
            try:
                precio = float(valor)
                # Filtrar valores sospechosos (0 o muy pequeños)
                if precio >= 10:
                    precios.append(precio)
            except ValueError:
                pass

    return precios


def obtener_precio_minimo():
    """
    Descarga la página y devuelve el precio mínimo encontrado.
    """
    resp = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resp.raise_for_status()

    precios = obtener_precios(resp.text)
    if not precios:
        raise ValueError(
            "No se encontraron precios en la página (puede que se carguen con JS o haya cambiado el HTML)."
        )

    return min(precios), precios


def monitorear():
    """
    Bucle infinito que revisa la página cada cierto tiempo
    y manda alerta si el precio baja del umbral.
    Corre en un hilo separado.
    """
    # Mensaje de prueba al iniciar
    try:
        enviar_mensaje("🚀 Bot de precios iniciado en Render (modo web service).")
    except Exception as e:
        print("Error enviando mensaje inicial:", e)

    ultimo_aviso = None

    while True:
        try:
            precio_minimo, lista = obtener_precio_minimo()
            estado["ultimo_precio_minimo"] = precio_minimo
            estado["ultima_lista_precios"] = lista
            estado["ultimo_error"] = None

            print(f"[DEBUG] Precios encontrados: {lista}")
            print(f"[DEBUG] Precio mínimo: {precio_minimo}")

            if precio_minimo <= PRECIO_UMBRAL and precio_minimo != ultimo_aviso:
                enviar_mensaje(
                    f"📉 ¡Bajó el precio!\n\n"
                    f"URL: {URL}\n"
                    f"Precio mínimo encontrado: S/ {precio_minimo}\n"
                    f"Umbral configurado: S/ {PRECIO_UMBRAL}"
                )
                ultimo_aviso = precio_minimo

        except Exception as e:
            print("Error en monitorear:", e)
            estado["ultimo_error"] = str(e)
            try:
                enviar_mensaje(f"❌ Error al revisar precios: {e}")
            except Exception:
                pass

        time.sleep(INTERVALO_SEGUNDOS)


# ========= RUTAS WEB PARA QUE RENDER VEA UN PUERTO ABIERTO =========

@app.route("/")
def home():
    return "Bot de precios de Claro corriendo 🔍", 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/status")
def status():
    return jsonify(estado), 200


def iniciar_bot_en_hilo():
    hilo = threading.Thread(target=monitorear, daemon=True)
    hilo.start()


if __name__ == "__main__":
    # Iniciar el hilo del bot
    iniciar_bot_en_hilo()

    # Levantar el servidor Flask en el puerto que Render espera
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
