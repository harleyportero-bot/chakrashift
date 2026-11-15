"""
ChakraShift — PASO 2: la página web
===================================
El usuario:
  1. Elige qué sembró en su chakra.
  2. Dibuja su chakra en el mapa.
  3. Recibe el Índice de Salud de la Chakra (0–100) y recomendaciones.

Los mapas ya están descargados en "datos/" (ver preparar_datos.py).
Uso:  streamlit run app.py
"""
import json
import os

import folium
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from folium.plugins import Draw
from pyproj import Transformer
from rasterio.mask import mask
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as transformar
from streamlit_folium import st_folium

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, "datos")
OESTE, SUR, ESTE, NORTE = -77.90, -1.10, -77.60, -0.85      # zona piloto (igual que preparar_datos.py)
MODELO_GEMINI = "gemini-2.5-flash"   # poner aquí el nombre del modelo que aparece en Google AI Studio

st.set_page_config(page_title="ChakraShift", page_icon="🌱", layout="wide")


# ====================================================================== DATOS
@st.cache_data
def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


CULTIVOS = leer_json(os.path.join(BASE, "cultivos.json"))["cultivos"]
RUTA_CLIMA = os.path.join(DATOS, "clima.json")
CLIMA = leer_json(RUTA_CLIMA) if os.path.exists(RUTA_CLIMA) else {}

# nombre: (archivo, factor, mínimo válido, máximo válido, unidad, fuente · resolución)
CAPAS = {
    "ph":          ("ph.tif", 0.1, 3, 10, "", "SoilGrids · 250 m"),
    "carbono_org": ("soc.tif", 0.1, 0, 600, "g/kg", "SoilGrids · 250 m"),
    "arcilla":     ("arcilla.tif", 0.1, 0, 100, "%", "SoilGrids · 250 m"),
    "agua_hist":   ("agua_hist.tif", 1, 0, 100, "% del tiempo con agua", "JRC Global Surface Water · 30 m"),
    "pendiente":   ("pendiente.tif", 1, 0, 90, "grados", "Copernicus DEM · 30 m"),
    "altura_rel":  ("altura_relativa.tif", 1, 0, 2000, "m sobre lo más bajo", "Copernicus DEM · 30 m"),
    "ndvi_actual": ("ndvi_actual.tif", 1, -1, 1, "", "MODIS NDVI · 250 m"),
    "ndvi_anom":   ("ndvi_anom.tif", 1, -1, 1, "", "MODIS NDVI · 250 m"),
}
NOMBRES = {
    "ph": "pH del suelo", "carbono_org": "Carbono orgánico del suelo", "arcilla": "Arcilla del suelo",
    "agua_hist": "Agua histórica", "pendiente": "Pendiente", "altura_rel": "Altura sobre zona baja",
    "ndvi_actual": "Verdor de la vegetación (NDVI)", "ndvi_anom": "Cambio del verdor vs. lo normal",
    "temp_media_c": "Temperatura media (°C)", "lluvia_anual_mm": "Lluvia anual normal (mm)",
    "lluvia_reciente_rel": "Lluvia últimos 12 meses (1 = normal)", "hum_raiz_anom": "Humedad del suelo vs. normal",
    "dias_calor_32_anio": "Días/año con más de 32 °C", "dias_lluvia_extrema_anio": "Días/año con lluvia > 50 mm",
    "dias_helada_anio": "Días/año con helada", "tendencia_lluvia_mm_decada": "Tendencia de lluvia (mm por década)",
}


def valor_en_poligono(nombre, geom):
    """Promedio de un mapa dentro de la chakra dibujada (None si no hay dato)."""
    archivo, factor, vmin, vmax, _, _ = CAPAS[nombre]
    ruta = os.path.join(DATOS, archivo)
    if not os.path.exists(ruta):
        return None
    with rasterio.open(ruta) as src:
        a_crs = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform
        g = transformar(a_crs, geom)
        try:
            datos, _ = mask(src, [mapping(g)], crop=True, all_touched=True, filled=False)
        except ValueError:      # la chakra está fuera del mapa
            return None
    v = datos[0].astype("float64").compressed() * factor
    v = v[np.isfinite(v) & (v >= vmin) & (v <= vmax)]
    return float(v.mean()) if v.size else None


@st.cache_data
def analizar(geom_json):
    geom = shape(json.loads(geom_json))
    valores = {k: valor_en_poligono(k, geom) for k in CAPAS}
    valores.update({k: v for k, v in CLIMA.items() if k != "ultimo_dato"})
    return valores


# ====================================================================== METODOLOGÍA
def nota_rango(x, abs_min, opt_min, opt_max, abs_max):
    """Método Ecocrop (FAO): 1 en el rango óptimo, baja en línea recta hasta 0 en el límite absoluto."""
    if x is None:
        return None
    if opt_min <= x <= opt_max:
        return 1.0
    if x <= abs_min or x >= abs_max:
        return 0.0
    if x < opt_min:
        return (x - abs_min) / (opt_min - abs_min)
    return (abs_max - x) / (abs_max - opt_max)


def nota_minimo(x, malo, bueno):
    """0 si x <= malo, 1 si x >= bueno, en línea recta entre ambos."""
    if x is None:
        return None
    return float(np.clip((x - malo) / (bueno - malo), 0, 1))


def riesgo_inundacion(v):
    alt, agua = v.get("altura_rel"), v.get("agua_hist") or 0
    if (alt is not None and alt < 3) or agua > 10:
        return 1.0
    if alt is not None and alt < 8:
        return 0.5
    return 0.0


def riesgo_erosion(v):
    p = v.get("pendiente")
    if p is None:
        return 0.0
    base = 1.0 if p > 15 else 0.5 if p > 8 else 0.0
    return base if (v.get("dias_lluvia_extrema_anio") or 0) >= 1 else base * 0.7


def evaluar(c, v):
    """Índice de Salud de la Chakra = 50 % aptitud + 30 % estado actual + 20 % (1 − riesgo)."""
    notas = {
        "temperatura": nota_rango(v.get("temp_media_c"), *c["temp"]),
        "lluvia": nota_rango(v.get("lluvia_anual_mm"), *c["lluvia"]),
        "pH del suelo": nota_rango(v.get("ph"), *c["ph"]),
    }
    notas = {k: n for k, n in notas.items() if n is not None}
    aptitud = min(notas.values()) if notas else None
    limitante = min(notas, key=notas.get) if notas else None

    estado_partes = [
        nota_rango(v.get("lluvia_reciente_rel"), 0.5, 0.8, 1.2, 1.6),
        nota_rango(v.get("hum_raiz_anom"), -0.15, -0.05, 0.10, 0.25),
        nota_minimo(v.get("ndvi_anom"), -0.10, -0.02),
    ]
    estado_partes = [e for e in estado_partes if e is not None]
    estado = float(np.mean(estado_partes)) if estado_partes else None

    r_inund = riesgo_inundacion(v) * (1 - c["tolera_inundacion"])
    r_eros = riesgo_erosion(v)
    riesgo = max(r_inund, r_eros)

    partes = [(0.5, aptitud), (0.3, estado), (0.2, 1 - riesgo)]
    partes = [(w, x) for w, x in partes if x is not None]
    indice = 100 * sum(w * x for w, x in partes) / sum(w for w, _ in partes)
    return {"indice": round(indice), "aptitud": aptitud, "limitante": limitante, "notas": notas,
            "estado": estado, "riesgo_inundacion": r_inund, "riesgo_erosion": r_eros}


def recomendaciones(clave, c, v, r):
    nombre = c["nombre"].lower()
    recs = []
    if r["riesgo_inundacion"] >= 0.4:
        recs.append(f"🌊 Tu chakra está en zona baja o que se ha inundado antes. Siembra la {nombre} en la parte "
                    "más alta o en camellones, y cosecha antes de la época de crecidas.")
    if r["riesgo_erosion"] >= 0.5:
        recs.append("⛰️ El terreno es inclinado: cubre el suelo con maní forrajero y siembra árboles como la guaba "
                    "en curvas de nivel para que la lluvia no se lleve la tierra.")
    co = v.get("carbono_org")
    if co is not None and co < 20:
        recs.append("🍂 El suelo tiene poca materia orgánica: deja la hojarasca, agrega abono orgánico y rota con "
                    "plantas que devuelven nitrógeno (maní, fréjol, guaba).")
    ph = v.get("ph")
    if ph is not None and ph < c["ph"][1]:
        recs.append(f"🧪 El suelo es más ácido de lo ideal para la {nombre} (pH {ph:.1f}). La materia orgánica y "
                    "un poco de ceniza o cal agrícola ayudan; consulta antes a un técnico.")
    if ph is not None and ph > c["ph"][2]:
        recs.append(f"🧪 El suelo es menos ácido de lo ideal para la {nombre} (pH {ph:.1f}). Consulta a un técnico.")
    lr = v.get("lluvia_reciente_rel")
    if lr is not None and lr < 0.8:
        recs.append("☀️ En los últimos 12 meses llovió menos de lo normal: cubre el suelo con hojas secas (mulch) "
                    "y siembra al inicio de las lluvias.")
    if lr is not None and lr > 1.2:
        recs.append("🌧️ En los últimos 12 meses llovió más de lo normal: revisa que el agua no se empoce y vigila "
                    "hongos y pudrición en raíces.")
    na = v.get("ndvi_anom")
    if na is not None and na < -0.05:
        recs.append("🍃 La vegetación de tu zona está más débil que lo normal: revisa plagas, enfermedades o falta "
                    "de nutrientes.")
    if r["aptitud"] is not None and r["aptitud"] < 0.5:
        recs.append(f"📍 Este lugar no es el ideal para la {nombre}: lo que más limita es la {r['limitante']}.")
    recs.append(f"💡 {c['consejo']}")
    return recs


def companeros(seleccion, v):
    """Plantas que conviene sumar a la chakra: mejoran el suelo y se adaptan al lugar."""
    opciones = []
    for k, c in CULTIVOS.items():
        if k in seleccion:
            continue
        apt = evaluar(c, v)["aptitud"] or 0.5
        beneficio = c["fija_n"] + c["materia_organica"] + c["reduce_erosion"]
        opciones.append((apt * beneficio, c["nombre"], c))
    opciones.sort(reverse=True)
    return opciones[:2]


def semaforo(i):
    return "🟢 Buena" if i >= 70 else "🟡 Regular" if i >= 40 else "🔴 Mala"


# ====================================================================== PÁGINA
st.title("🌱 ChakraShift")
st.caption("Datos de satélites NASA + saber de la chakra · Zona piloto: Tena – Archidona – Puerto Misahuallí (Napo)")

col_mapa, col_res = st.columns([3, 2])

with col_mapa:
    seleccion = st.multiselect("1️⃣ ¿Qué sembraste en tu chakra?", options=list(CULTIVOS),
                               format_func=lambda k: CULTIVOS[k]["nombre"])
    st.markdown("2️⃣ **Dibuja tu chakra en el mapa** con el botón ⬟ (polígono) o ▭ (rectángulo) a la izquierda.")
    m = folium.Map(location=[-0.97, -77.75], zoom_start=11, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satélite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Calles").add_to(m)
    folium.Rectangle(bounds=[[SUR, OESTE], [NORTE, ESTE]], color="#2e7d32", weight=2, fill=False,
                     tooltip="Zona piloto con datos").add_to(m)
    Draw(draw_options={"polyline": False, "circle": False, "circlemarker": False, "marker": False},
         edit_options={"edit": False}).add_to(m)
    folium.LayerControl().add_to(m)
    salida = st_folium(m, height=520, use_container_width=True, returned_objects=["last_active_drawing"])

with col_res:
    dibujo = (salida or {}).get("last_active_drawing")
    if not seleccion:
        st.info("Empieza eligiendo qué sembraste en tu chakra.")
    elif not dibujo:
        st.info("Ahora dibuja tu chakra en el mapa.")
    else:
        geom = shape(dibujo["geometry"])
        if not geom.intersects(box(OESTE, SUR, ESTE, NORTE)):
            st.warning("Tu chakra está fuera de la zona piloto (rectángulo verde). Por ahora solo hay datos ahí.")
            st.stop()
        area_ha = transformar(Transformer.from_crs("EPSG:4326", "EPSG:32718", always_xy=True).transform,
                              geom).area / 10_000
        st.markdown(f"**Tu chakra:** {area_ha:.2f} ha")
        if area_ha < 6.25:
            st.caption("Tu chakra es más pequeña que un píxel de suelo (250 m): se usa el valor del lugar donde está.")

        v = analizar(json.dumps(dibujo["geometry"]))
        resultados = {}
        for k in seleccion:
            c = CULTIVOS[k]
            r = evaluar(c, v)
            resultados[c["nombre"]] = r
            st.subheader(f"{c['nombre']}: {r['indice']}/100 · {semaforo(r['indice'])}")
            st.progress(r["indice"] / 100)
            a, b, d = st.columns(3)
            a.metric("Aptitud del lugar", "—" if r["aptitud"] is None else f"{r['aptitud']*100:.0f}%")
            b.metric("Estado actual", "—" if r["estado"] is None else f"{r['estado']*100:.0f}%")
            d.metric("Riesgo", f"{max(r['riesgo_inundacion'], r['riesgo_erosion'])*100:.0f}%")
            for rec in recomendaciones(k, c, v, r):
                st.markdown(f"- {rec}")

        st.subheader("🌿 Plantas que le harían bien a tu chakra")
        for _, nombre, c in companeros(seleccion, v):
            st.markdown(f"- **{nombre}**: {c['por_que_sumarla']}")

        with st.expander("📊 Datos de tu chakra y de dónde salen"):
            filas = []
            for k, val in v.items():
                fuente = CAPAS[k][5] if k in CAPAS else "NASA POWER · ~55 km (igual para toda la zona)"
                filas.append({"Indicador": NOMBRES.get(k, k),
                              "Valor": "sin dato" if val is None else round(val, 2), "Fuente": fuente})
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
            if CLIMA.get("ultimo_dato"):
                st.caption(f"Clima actualizado hasta: {CLIMA['ultimo_dato']}")

        # ---- Explicación opcional con Gemini (necesita una clave de Google AI Studio)
        try:
            clave = st.secrets["GEMINI_API_KEY"]
        except Exception:
            clave = os.environ.get("GEMINI_API_KEY")
        if clave and st.button("💬 Explícamelo en palabras sencillas (Gemini)"):
            prompt = ("Eres un técnico agrícola amable que habla con familias kichwa de Napo. Con SOLO estos datos, "
                      "explica en español sencillo, en 5 a 7 frases, cómo está su chakra y qué hacer primero. "
                      "No inventes cifras. Aclara que son estimaciones con datos de satélite.\n\n"
                      f"Datos de la zona: {json.dumps(v, default=str)}\n"
                      f"Resultados por cultivo: {json.dumps(resultados, default=str)}")
            try:
                from google import genai
                respuesta = genai.Client(api_key=clave).models.generate_content(model=MODELO_GEMINI, contents=prompt)
                st.success(respuesta.text)
            except Exception as e:
                st.error(f"No se pudo usar Gemini: {e}")

st.divider()
st.caption("Metodología: Índice de Salud de la Chakra = 50 % aptitud (método Ecocrop, FAO) + 30 % estado actual "
           "(anomalías de lluvia, humedad del suelo y vegetación) + 20 % riesgos (inundación y erosión). "
           "Son estimaciones con datos satelitales; no reemplazan la visita de un técnico.")
