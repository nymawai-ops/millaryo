import os
import time
import re
import requests
from bs4 import BeautifulSoup

# === CONFIG DESDE VARIABLES DE ENTORNO ===
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
URL = os.environ.get("URL_CLARO", "https://www.tiendaclaro.pe/")
PRECIO_UMBRAL = float(os.environ.get("PRECIO_UMBRAL", "100.0"))
INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", "1800"))  # 30 min por defecto


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
    Es genérico; luego podemos afinarlo según la página de Claro.
    """
    soup = BeautifulSoup(html, "html.parser")
    textos = soup.find_all(string=re.compile(r"S/"))
    precios = []

    for t in textos:
        match = re.search(r"S/\s*([\d\.]+)", t)
        if match:
            valor = match.group(1)
            try:
                precios.append(float(valor))
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
        raise ValueError("No se encontraron precios en la página (puede que se carguen con JS).")

    return min(precios), precios


def monitorear():
    """
    Bucle infinito que revisa la página cada cierto tiempo
    y manda alerta si el precio baja del umbral.
    """
    # Mensaje de prueba al iniciar
    try:
        enviar_mensaje("🚀 Bot de precios iniciado en Render.")
    except Exception as e:
        print("Error enviando mensaje inicial:", e)

    ultimo_aviso = None

    while True:
        try:
            precio_minimo, lista = obtener_precio_minimo()
            print(f"[DEBUG] Precios encontrados: {lista}")
            print(f"[DEBUG] Precio mínimo: {precio_minimo}")

            if precio_minimo <= PRECIO_UMBRAL and precio_minimo != ultimo_aviso:
                enviar_mensaje(
                    f"📉 ¡Bajó el precio!\n\n"
                    f"URL: {URL}\n"
                    f"Precio mínimo encontrado: S/ {precio_minimo}\n"
