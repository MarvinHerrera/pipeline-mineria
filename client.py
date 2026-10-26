"""Extracción en vivo desde CoinGecko y envío al microservicio en la nube."""
import json
import sys
import time

import requests

COINGECKO = "https://api.coingecko.com/api/v3/coins/markets"
# Cambia por tu URL de Render, p. ej. https://mi-pipeline.onrender.com/procesar
SERVICIO = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000/procesar"


def extraer(n=20):
    params = {"vs_currency": "usd", "order": "market_cap_desc",
              "per_page": n, "page": 1}
    r = requests.get(COINGECKO, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    print("[1] Extrayendo datos de CoinGecko...")
    crudo = extraer()
    with open("payload_crudo.json", "w", encoding="utf-8") as f:
        json.dump(crudo, f, ensure_ascii=False, indent=2)
    print(f"    {len(crudo)} registros crudos guardados en payload_crudo.json")

    print(f"[2] Enviando a {SERVICIO} ...")
    t0 = time.time()
    resp = requests.post(SERVICIO, json=crudo, timeout=90)  # Render free: 1ª llamada lenta
    resp.raise_for_status()
    print(f"    HTTP {resp.status_code} en {time.time() - t0:.2f}s")

    resultado = resp.json()
    with open("resultados.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print("[3] Resumen analítico:")
    print(json.dumps(resultado["resumen"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
