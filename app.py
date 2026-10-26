"""Microservicio de limpieza + minería de datos (Flask). Desplegable en Render."""
import re
import statistics
import unicodedata
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)


# ---------- 1. LIMPIEZA / PREPROCESAMIENTO ----------
def limpiar_texto(txt):
    """Normaliza: minúsculas, sin acentos, sin caracteres especiales."""
    if not isinstance(txt, str):
        return "desconocido"
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-zA-Z0-9 ]", "", txt).strip().lower()
    return txt or "desconocido"


def limpiar(registros):
    campos_num = ["current_price", "market_cap", "total_volume",
                  "price_change_percentage_24h"]
    # mediana por campo para imputar valores nulos
    medianas = {}
    for c in campos_num:
        vals = [r[c] for r in registros if isinstance(r.get(c), (int, float))]
        medianas[c] = statistics.median(vals) if vals else 0.0

    limpios, imputados = [], 0
    for r in registros:
        item = {"id": limpiar_texto(r.get("id")),
                "nombre": limpiar_texto(r.get("name")),
                "simbolo": limpiar_texto(r.get("symbol")).upper()}
        for c in campos_num:
            v = r.get(c)
            if not isinstance(v, (int, float)):
                v = medianas[c]
                imputados += 1
            item[c] = float(v)
        limpios.append(item)
    return limpios, imputados


# ---------- 2. MINERÍA ----------
def clasificar_regla(r):
    """Scoring por reglas -> etiqueta de tendencia y riesgo."""
    cambio = r["price_change_percentage_24h"]
    if cambio > 3:
        tendencia = "alcista"
    elif cambio < -3:
        tendencia = "bajista"
    else:
        tendencia = "lateral"

    # score 0-100: volumen relativo al market cap (liquidez) + magnitud del cambio
    liquidez = r["total_volume"] / r["market_cap"] if r["market_cap"] else 0
    score = min(100, liquidez * 300 + abs(cambio) * 5)
    riesgo = "alto" if abs(cambio) > 7 or score > 70 else (
        "medio" if abs(cambio) > 3 else "bajo")
    return tendencia, riesgo, round(score, 2)


def kmeans_1d(valores, k=3, iteraciones=50):
    """K-means simple sobre una dimensión (log del market cap)."""
    import math
    xs = [math.log10(v) if v > 0 else 0 for v in valores]
    k = min(k, len(set(xs))) or 1
    s = sorted(xs)
    cent = [s[int(i * (len(s) - 1) / max(k - 1, 1))] for i in range(k)]
    asign = [0] * len(xs)
    for _ in range(iteraciones):
        asign = [min(range(k), key=lambda j: abs(x - cent[j])) for x in xs]
        nuevos = []
        for j in range(k):
            grupo = [x for x, a in zip(xs, asign) if a == j]
            nuevos.append(sum(grupo) / len(grupo) if grupo else cent[j])
        if nuevos == cent:
            break
        cent = nuevos
    # ordenar clusters de mayor a menor capitalización
    orden = sorted(range(k), key=lambda j: -cent[j])
    nombres = ["mega_cap", "mid_cap", "small_cap"]
    mapa = {j: nombres[min(i, 2)] for i, j in enumerate(orden)}
    return [mapa[a] for a in asign]


# ---------- 3. ENDPOINTS ----------
@app.route("/")
def home():
    return jsonify({"servicio": "pipeline-mineria", "estado": "ok",
                    "uso": "POST /procesar con JSON crudo de CoinGecko"})


@app.route("/procesar", methods=["POST"])
def procesar():
    crudo = request.get_json(silent=True)
    if not isinstance(crudo, list) or not crudo:
        return jsonify({"error": "Se esperaba una lista JSON no vacía"}), 400

    limpios, imputados = limpiar(crudo)
    clusters = kmeans_1d([r["market_cap"] for r in limpios])

    resultados = []
    for r, cl in zip(limpios, clusters):
        tendencia, riesgo, score = clasificar_regla(r)
        resultados.append({**r, "tendencia": tendencia, "riesgo": riesgo,
                           "score": score, "cluster_capitalizacion": cl})

    resumen = {
        "total_registros": len(resultados),
        "valores_imputados": imputados,
        "por_tendencia": {t: sum(1 for x in resultados if x["tendencia"] == t)
                          for t in ("alcista", "bajista", "lateral")},
        "por_cluster": {c: sum(1 for x in resultados
                               if x["cluster_capitalizacion"] == c)
                        for c in ("mega_cap", "mid_cap", "small_cap")},
        "top_score": max(resultados, key=lambda x: x["score"])["nombre"],
    }
    return jsonify({"timestamp": datetime.now(timezone.utc).isoformat(),
                    "resumen": resumen, "resultados": resultados})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
