import os
import time
import re
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
URL = os.environ.get("URL_CLARO", "https://www.tiendaclaro.pe/")
PRECIO_UMBRAL = float(os.environ.get("PRECIO_UMBRAL", "100.0"))
INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", "1800"))


def obtener_precios(html: str):
    soup = BeautifulSoup(html, "html.parser")
    textos = soup.find_all(string=re.compile(r"S/"))
    precios = []
    for t in textos:
        match = re.search(r"S/\s*([\d\.]+)", t)
        if match:
            try:
                precios.append(float(match.group(1)))
            except:
                pass
    return precios

def obtener_precio_minimo():
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    precios = obtener_precios(resp.text)
    if not precios:
        raise ValueError("No se encontraron precios.")
    return min(precios), precios

def enviar_mensaje(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": msg
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()

def monitorear():
    ultimo = None
    while True:
        try:
            precio_min, lista = obtener_precio_minimo()
            print("[DEBUG] Precios:", lista)
            if precio_min <= PRECIO_UMBRAL and precio_min != ultimo:
                enviar_mensaje(f"📉 ¡Precio bajo!\nURL: {URL}\nPrecio: S/ {precio_min}")
                ultimo = precio_min
        except Exception as e:
            print("Error:", e)
        time.sleep(INTERVALO_SEGUNDOS)

if __name__ == "__main__":
    monitorear()
