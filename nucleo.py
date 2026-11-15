"""
ChakraShift — NÚCLEO: datos y cálculos (sin páginas)
====================================================
Todo lo que lee mapas y calcula notas vive aquí. Las páginas (carpeta paginas/) solo muestran.

  1. CONFIGURACIÓN Y DATOS ........ zona piloto, archivos, cultivos, clima
  2. CATÁLOGO DE MAPAS ............ qué es cada mapa, fuente, resolución, cómo leerlo
  3. VALORES DENTRO DE UNA CHAKRA .. promedio de cada mapa dentro del polígono dibujado
  4. METODOLOGÍA (Ecocrop FAO) ..... notas, aptitud, estado, riesgo, parte sembrable, índice
  5. MAPAS DE TODA LA ZONA ......... la misma fórmula aplicada a cada celda de ~110 m
  6. DIBUJO ....................... colores, imágenes y mapa base
"""
import json
import os
import re
from datetime import datetime

import folium
import numpy as np
from folium.raster_layers import ImageOverlay
import rasterio
import streamlit as st
from pyproj import Transformer
from rasterio.mask import mask
from rasterio.transform import from_origin, rowcol
from rasterio.warp import Resampling, reproject
from shapely.geometry import mapping, shape
from shapely.ops import transform as transformar

# ====================================================================== 1. CONFIGURACIÓN Y DATOS
BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, "datos")
OESTE, SUR, ESTE, NORTE = -77.90, -1.10, -77.60, -0.85      # zona piloto (igual que preparar_datos.py)
MODELO_GEMINI = "gemini-2.5-flash"   # nombre del modelo que aparece en Google AI Studio
GRADIENTE_T = -0.0065                # °C por metro: la temperatura baja ~6,5 °C cada 1000 m de subida
PESOS = {"aptitud": 0.5, "estado": 0.3, "sin_riesgo": 0.2}


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


CULTIVOS = leer_json(os.path.join(BASE, "cultivos.json"))["cultivos"]
RUTA_CLIMA = os.path.join(DATOS, "clima.json")
CLIMA = leer_json(RUTA_CLIMA) if os.path.exists(RUTA_CLIMA) else {}


def info_osm():
    ruta = os.path.join(DATOS, "osm_info.json")
    return leer_json(ruta) if os.path.exists(ruta) else None


def info_dem():
    """Qué DEM se usó (FABDEM o Copernicus) y desde cuándo está en datos/."""
    ruta = os.path.join(DATOS, "fuente_dem.json")
    return leer_json(ruta) if os.path.exists(ruta) else None


def version_datos():
    """Cambia cuando se actualiza algún archivo de datos/ (así no se queda un resultado viejo en caché)."""
    if not os.path.isdir(DATOS):
        return 0
    return max((os.path.getmtime(os.path.join(DATOS, f)) for f in os.listdir(DATOS)), default=0)


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
    "elevacion":   ("elevacion.tif", 1, -50, 7000, "m s.n.m.", "FABDEM / Copernicus DEM · 30 m"),
}
NOMBRES = {
    "elevacion": "Altitud (m s.n.m.)",
    "ph": "pH del suelo", "carbono_org": "Carbono orgánico del suelo", "arcilla": "Arcilla del suelo",
    "agua_hist": "Agua histórica", "pendiente": "Pendiente", "altura_rel": "Altura sobre zona baja",
    "ndvi_actual": "Verdor de la vegetación (NDVI)", "ndvi_anom": "Cambio del verdor vs. lo normal",
    "temp_media_c": "Temperatura media (°C)", "lluvia_anual_mm": "Lluvia anual normal (mm)",
    "lluvia_reciente_rel": "Lluvia últimos 12 meses (1 = normal)", "hum_raiz_anom": "Humedad del suelo vs. normal",
    "dias_calor_32_anio": "Días/año con más de 32 °C", "dias_lluvia_extrema_anio": "Días/año con lluvia > 50 mm",
    "dias_helada_anio": "Días/año con helada", "tendencia_lluvia_mm_decada": "Tendencia de lluvia (mm por década)",
}

# ESA WorldCover: código de clase -> (nombre, color oficial)
CLASES_WC = {10: "Bosque", 20: "Arbustos", 30: "Pasto", 40: "Cultivos", 50: "Construido (ciudad, casas, vías)",
             60: "Suelo desnudo / arena", 70: "Nieve", 80: "Agua permanente", 90: "Humedal", 95: "Manglar",
             100: "Musgo / líquenes"}
COLORES_WC = {10: "#006400", 20: "#ffbb22", 30: "#ffff4c", 40: "#f096ff", 50: "#fa0000", 60: "#b4b4b4",
              70: "#f0f0f0", 80: "#0064c8", 90: "#0096a0", 95: "#00cf75", 100: "#fae6a0"}


# ====================================================================== 2. CATÁLOGO DE MAPAS
ROJO_VERDE = ["#d73027", "#fee08b", "#1a9850"]
FUENTES = {
    "worldcover": "ESA WorldCover 2021 v200 (satélites Sentinel-1 y Sentinel-2) · 10 m · año 2021",
    "osm": "OpenStreetMap (Overpass API) · edificios y calles dibujados por voluntarios · se baja al día",
    "construido": "ESA WorldCover 2021 v200 · 10 m (año 2021) + OpenStreetMap al día (edificios, barrios y calles)",
    "dem": "FABDEM v1.2 (Universidad de Bristol: Copernicus GLO-30 con árboles y edificios eliminados) · 30 m · "
           "respaldo: Copernicus DEM GLO-30",
    "soilgrids": "SoilGrids 2.0 (ISRIC) · modelo de aprendizaje automático con ~240 000 muestras · 250 m · 0–5 cm",
    "jrc": "JRC Global Surface Water (Landsat 5, 7 y 8) · 30 m · 1984–2021",
    "power": "NASA POWER (MERRA-2 + satélites GPM/IMERG) · ~55 km · diario 2001–hoy",
    "modis": "NASA MODIS MOD13Q1 (satélite Terra) · 250 m · cada 16 días",
}

# Mapas "crudos": lo que mide el satélite o el modelo, en sus unidades reales
MAPAS_DATOS = {
    "cobertura": dict(titulo="Cobertura del suelo", unidad="clase", fuente="worldcover",
                      que_es="Qué hay encima del suelo: bosque, pasto, cultivos, ciudad, agua…",
                      como_se_obtiene="Clasificación automática de imágenes de radar (Sentinel-1) y ópticas "
                                      "(Sentinel-2) de todo 2021. Precisión global ~75 %.",
                      como_leer="Rojo = construido. Azul = agua. Verde oscuro = bosque.",
                      usa_en="Parte sembrable"),
    "construido": dict(titulo="Construido (ciudad, casas, calles)", unidad="% de la celda", fuente="construido",
                       colores=["#ffffff", "#fdae61", "#a50026"], vmin=0, vmax=100,
                       que_es="Qué parte de cada celda está cubierta por techos, asfalto o calles.",
                       como_se_obtiene="Se junta la clase 'Construido' de WorldCover 2021 con los edificios, "
                                       "barrios y calles de OpenStreetMap (las calles se ensanchan 4–12 m según "
                                       "su tipo). OSM capta lo construido después de 2021.",
                       como_leer="Blanco = nada construido. Rojo oscuro = todo construido.",
                       usa_en="Parte sembrable"),
    "elevacion": dict(titulo="Altitud", unidad="m s.n.m.", fuente="dem",
                      colores=["#1a9850", "#a6d96a", "#fee08b", "#d8b365", "#8c510a"],
                      que_es="Altura sobre el nivel del mar.",
                      como_se_obtiene="Modelo digital de elevación de radar (TanDEM-X).",
                      como_leer="Verde = bajo (valle del Napo). Café = alto (lomas hacia los Andes).",
                      usa_en="Ajustar la temperatura por altura"),
    "temperatura": dict(titulo="Temperatura media anual", unidad="°C", fuente="power",
                        colores=["#4575b4", "#ffffbf", "#d73027"],
                        que_es="Temperatura promedio del aire a 2 m (2001–2024).",
                        como_se_obtiene="NASA POWER da UN valor para toda la zona; se ajusta por la altitud de "
                                        "cada celda: T = T_POWER − 6,5 °C/km × (altitud − altitud media de la zona).",
                        como_leer="Azul = más fresco (zonas altas). Rojo = más caliente (zonas bajas).",
                        usa_en="Nota de temperatura (Ecocrop)"),
    "ph": dict(titulo="pH del suelo", unidad="pH", fuente="soilgrids",
               colores=["#d73027", "#fee08b", "#91cf60", "#4575b4"],
               que_es="Acidez del suelo en los primeros 5 cm (menor = más ácido).",
               como_se_obtiene="Estimación por modelo a partir de muestras de suelo y variables ambientales. "
                               "No es una medición en tu chakra.",
               como_leer="Rojo = muy ácido (típico de la Amazonía, 4–5). Azul = neutro (~7).",
               usa_en="Nota de pH (Ecocrop)"),
    "carbono_org": dict(titulo="Carbono orgánico del suelo", unidad="g/kg", fuente="soilgrids",
                        colores=["#f6e8c3", "#bf812d", "#543005"],
                        que_es="Cantidad de materia orgánica (hojarasca descompuesta) en el suelo.",
                        como_se_obtiene="Estimación por modelo (SoilGrids).",
                        como_leer="Claro = poca materia orgánica. Oscuro = suelo rico.",
                        usa_en="Recomendaciones (abono orgánico)"),
    "arcilla": dict(titulo="Arcilla del suelo", unidad="%", fuente="soilgrids",
                    colores=["#ffffcc", "#fd8d3c", "#800026"],
                    que_es="Porcentaje de partículas finas (arcilla) en el suelo.",
                    como_se_obtiene="Estimación por modelo (SoilGrids).",
                    como_leer="Más arcilla = guarda más agua pero se encharca más.",
                    usa_en="Solo informativo por ahora"),
    "pendiente": dict(titulo="Pendiente del terreno", unidad="grados", fuente="dem",
                      colores=["#ffffcc", "#fd8d3c", "#800026"], vmin=0, vmax=35,
                      que_es="Qué tan inclinado es el terreno.",
                      como_se_obtiene="Se calcula del modelo de elevación: cambio de altura por cada 30 m.",
                      como_leer="Amarillo = plano. Rojo oscuro = muy inclinado (> 15° = riesgo alto de erosión).",
                      usa_en="Riesgo de erosión"),
    "altura_rel": dict(titulo="Altura sobre la zona baja", unidad="m", fuente="dem",
                       colores=["#08306b", "#6baed6", "#f7fbff"], vmin=0, vmax=40,
                       que_es="Cuántos metros está el lugar por encima del punto más bajo a ~1 km a la redonda.",
                       como_se_obtiene="Altitud − altitud mínima en una ventana de 33 × 33 celdas de 30 m "
                                       "(aproximación del índice HAND).",
                       como_leer="Azul oscuro = zona baja que se inunda fácil (< 3 m). Blanco = alto y seco.",
                       usa_en="Riesgo de inundación"),
    "agua_hist": dict(titulo="Agua histórica", unidad="% del tiempo", fuente="jrc",
                      colores=["#ffffff", "#6baed6", "#08306b"], vmin=0, vmax=100,
                      que_es="En qué porcentaje de las imágenes Landsat (1984–2021) hubo agua en ese lugar.",
                      como_se_obtiene="Análisis de ~4 millones de imágenes Landsat.",
                      como_leer="Blanco = nunca hubo agua. Azul = río o zona que se inunda seguido.",
                      usa_en="Riesgo de inundación"),
    "ndvi_actual": dict(titulo="Verdor de la vegetación (NDVI)", unidad="NDVI", fuente="modis",
                        colores=["#a50026", "#fee08b", "#006837"], vmin=0, vmax=1,
                        que_es="Qué tan verde y vigorosa está la vegetación en los últimos 3 meses.",
                        como_se_obtiene="Índice (infrarrojo − rojo) / (infrarrojo + rojo) del satélite Terra.",
                        como_leer="Rojo = poca vegetación. Verde oscuro = vegetación densa.",
                        usa_en="Estado actual"),
    "ndvi_anom": dict(titulo="Cambio del verdor vs. lo normal", unidad="NDVI", fuente="modis",
                      colores=["#a50026", "#ffffbf", "#006837"], vmin=-0.2, vmax=0.2,
                      que_es="NDVI de los últimos 3 meses menos el promedio de todos los años.",
                      como_se_obtiene="Serie de tiempo MODIS desde AppEEARS.",
                      como_leer="Rojo = más seco/débil que lo normal. Verde = mejor que lo normal.",
                      usa_en="Estado actual"),
}

# Mapas de RESULTADOS de la metodología (0–1, 1 = mejor) para un cultivo
MAPAS_RESULTADOS = {
    "indice": dict(titulo="⭐ Índice de Salud de la Chakra (todo combinado)",
                   formula="[50 % Aptitud + 30 % Estado + 20 % (1 − Riesgo)] × Parte sembrable",
                   como_leer="Verde ≥ 70 buena · Amarillo 40–69 regular · Rojo < 40 mala."),
    "aptitud": dict(titulo="Aptitud Ecocrop (la nota más baja)",
                    formula="mínimo(nota temperatura, nota lluvia, nota pH)",
                    como_leer="Lo que más limita manda: si una sola nota es mala, la aptitud es mala."),
    "limitante": dict(titulo="Factor limitante",
                      formula="cuál de las 3 notas Ecocrop es la más baja",
                      como_leer="🟧 temperatura · 🟦 lluvia · 🟪 pH. Indica qué hay que mejorar o vigilar."),
    "temperatura": dict(titulo="Nota de temperatura",
                        formula="trapecio Ecocrop con los rangos del cultivo, usando la temperatura ajustada por altitud",
                        como_leer="1 (verde) si la temperatura está en el rango óptimo del cultivo."),
    "ph": dict(titulo="Nota de pH del suelo", formula="trapecio Ecocrop con el pH de SoilGrids",
               como_leer="1 (verde) si el pH está en el rango óptimo del cultivo."),
    "lluvia": dict(titulo="Nota de lluvia", formula="trapecio Ecocrop con la lluvia anual de NASA POWER",
                   como_leer="Un solo color: NASA POWER da un único valor de lluvia para toda la zona."),
    "estado": dict(titulo="Estado actual",
                   formula="promedio(nota lluvia últimos 12 meses, nota humedad del suelo últimos 3 meses, nota NDVI)",
                   como_leer="Verde = este año las condiciones están normales. Rojo = sequía o exceso de lluvia."),
    "sin_riesgo": dict(titulo="Sin riesgo (1 − riesgo)",
                       formula="1 − máximo(riesgo de inundación × (1 − tolerancia del cultivo), riesgo de erosión). "
                               "Si faltan los mapas de relieve, el riesgo no se evalúa y este componente se deja "
                               "fuera del índice (no se supone riesgo 0).",
                       como_leer="Rojo = zona baja que se inunda o ladera empinada."),
    "sembrable": dict(titulo="Parte sembrable",
                      formula="1 − construido − agua permanente − ½ suelo desnudo",
                      como_leer="Rojo = ciudad, calles o río: ahí no se puede sembrar."),
}
COLORES_LIMITANTE = {0: ("#e6550d", "Temperatura"), 1: ("#3182bd", "Lluvia"), 2: ("#756bb1", "pH")}


# ====================================================================== 3. VALORES DENTRO DE UNA CHAKRA
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


def leer_recorte(ruta, geom, all_touched):
    with rasterio.open(ruta) as src:
        g = transformar(Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform, geom)
        datos, _ = mask(src, [mapping(g)], crop=True, all_touched=all_touched, filled=False)
    return datos[0]


def cobertura_en_poligono(geom):
    """Fracción (0–1) de la chakra en cada tipo de cobertura. 'Construido' junta ESA WorldCover (clase 50)
    con lo que OpenStreetMap marca hoy como edificio, barrio, calle, etc. None si falta el mapa."""
    ruta_wc, ruta_osm = os.path.join(DATOS, "cobertura.tif"), os.path.join(DATOS, "osm_urbano.tif")
    if not os.path.exists(ruta_wc):
        return None
    try:
        wc = leer_recorte(ruta_wc, geom, all_touched=False)
        if wc.count() == 0:                       # chakra más chica que un píxel de 10 m
            wc = leer_recorte(ruta_wc, geom, all_touched=True)
        osm = None
        if os.path.exists(ruta_osm):
            osm = leer_recorte(ruta_osm, geom, all_touched=False)
            if osm.shape != wc.shape:
                osm = leer_recorte(ruta_osm, geom, all_touched=True)
    except ValueError:                            # fuera del mapa
        return None
    validos = ~np.ma.getmaskarray(wc) & (np.ma.filled(wc, 0) > 0)
    n = int(validos.sum())
    if n == 0:
        return None
    clases = np.ma.filled(wc, 0)
    construido = clases == 50
    if osm is not None and osm.shape == wc.shape:
        construido |= np.ma.filled(osm, 0) == 1
    frac = {}
    for codigo, nombre in CLASES_WC.items():
        sel = validos & (clases == codigo) & ~construido if codigo != 50 else validos & construido
        f = float(sel.sum()) / n
        if f > 0:
            frac[nombre] = f
    return frac


def fraccion_sembrable(cob):
    """Parte donde físicamente se puede sembrar: se quita lo construido y el agua permanente;
    el suelo desnudo (arenales de río, tierra removida) cuenta a la mitad."""
    if cob is None:
        return None
    no = (cob.get(CLASES_WC[50], 0) + cob.get(CLASES_WC[80], 0) + cob.get(CLASES_WC[70], 0)
          + 0.5 * cob.get(CLASES_WC[60], 0))
    return float(np.clip(1 - no, 0, 1))


def temperatura_ajustada(t_zona, elevacion, elev_ref):
    """NASA POWER da UNA temperatura para ~55 km. Se ajusta por altura con el gradiente térmico estándar."""
    if t_zona is None or elevacion is None or elev_ref is None:
        return t_zona
    return t_zona + GRADIENTE_T * (elevacion - elev_ref)


@st.cache_data
def analizar(geom_json, version):
    geom = shape(json.loads(geom_json))
    valores = {k: valor_en_poligono(k, geom) for k in CAPAS}
    valores.update({k: v for k, v in CLIMA.items() if k != "ultimo_dato"})
    valores["temp_media_c"] = temperatura_ajustada(valores.get("temp_media_c"), valores.get("elevacion"),
                                                   grillas_base(version)["elev_ref"])
    return valores, cobertura_en_poligono(geom)


# ====================================================================== 4. METODOLOGÍA (Ecocrop FAO)
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


RANGO_LLUVIA_RECIENTE = (0.5, 0.8, 1.2, 1.6)      # lluvia últimos 12 meses / normal
RANGO_HUMEDAD = (-0.15, -0.05, 0.10, 0.25)        # humedad del suelo 3 meses − normal
NDVI_MALO, NDVI_BUENO = -0.10, -0.02              # cambio del NDVI


def riesgo_inundacion(v):
    """Riesgo de inundación (0–1), o None si no hay ningún mapa para saberlo.
    None significa "no se pudo evaluar" y NO riesgo cero: suponer cero hacía la app demasiado optimista
    (un problema reportado en la BITACORA cuando faltaban los mapas de relieve)."""
    alt, agua = v.get("altura_rel"), v.get("agua_hist")
    if alt is None and agua is None:
        return None
    if agua is not None and agua > 10:
        return 1.0
    if alt is not None:
        if alt < 3:
            return 1.0
        if alt < 8:
            return 0.5
    return 0.0


def riesgo_erosion(v):
    """Riesgo de erosión (0–1), o None si falta el mapa de pendiente (no se puede inventar que no hay riesgo)."""
    p = v.get("pendiente")
    if p is None:
        return None
    base = 1.0 if p > 15 else 0.5 if p > 8 else 0.0
    return base if (v.get("dias_lluvia_extrema_anio") or 0) >= 1 else base * 0.7


def riesgo_total(v, c):
    """Junta inundación y erosión. Devuelve el mayor de los que sí se pudieron calcular y None si no
    se pudo calcular ninguno. Así el riesgo nunca se cuenta como 0 por falta de datos."""
    inund_base = riesgo_inundacion(v)
    inund = None if inund_base is None else inund_base * (1 - c["tolera_inundacion"])
    erosion = riesgo_erosion(v)
    disponibles = [x for x in (inund, erosion) if x is not None]
    return {
        "inundacion_base": inund_base,
        "inundacion": inund,
        "erosion": erosion,
        "total": max(disponibles) if disponibles else None,
        "faltan": [nombre for nombre, x in (("altura relativa / agua histórica", inund_base),
                                            ("pendiente del terreno", erosion)) if x is None],
    }


def evaluar(c, v, sembrable=None):
    """Índice de Salud de la Chakra = [50 % aptitud + 30 % estado actual + 20 % (1 − riesgo)] × parte sembrable."""
    notas = {
        "temperatura": nota_rango(v.get("temp_media_c"), *c["temp"]),
        "lluvia": nota_rango(v.get("lluvia_anual_mm"), *c["lluvia"]),
        "pH del suelo": nota_rango(v.get("ph"), *c["ph"]),
    }
    notas = {k: n for k, n in notas.items() if n is not None}
    aptitud = min(notas.values()) if notas else None
    limitante = min(notas, key=notas.get) if notas else None

    estado_notas = {
        "lluvia 12 meses": nota_rango(v.get("lluvia_reciente_rel"), *RANGO_LLUVIA_RECIENTE),
        "humedad del suelo": nota_rango(v.get("hum_raiz_anom"), *RANGO_HUMEDAD),
        "verdor NDVI": nota_minimo(v.get("ndvi_anom"), NDVI_MALO, NDVI_BUENO),
    }
    estado_notas = {k: n for k, n in estado_notas.items() if n is not None}
    estado = float(np.mean(list(estado_notas.values()))) if estado_notas else None
    estado_faltan = [k for k in ("lluvia 12 meses", "humedad del suelo", "verdor NDVI") if k not in estado_notas]

    rr = riesgo_total(v, c)
    riesgo = rr["total"]

    partes = [(PESOS["aptitud"], aptitud), (PESOS["estado"], estado)]
    if riesgo is not None:                       # sin datos de relieve el riesgo se deja FUERA (no se pone en 0)
        partes.append((PESOS["sin_riesgo"], 1 - riesgo))
    partes = [(w, x) for w, x in partes if x is not None]
    peso_total = sum(w for w, _ in partes)
    indice_base = 100 * sum(w * x for w, x in partes) / peso_total if peso_total else 0.0
    indice = indice_base * (1 if sembrable is None else sembrable)
    return {"indice": round(indice), "indice_base": indice_base, "sembrable": sembrable,
            "aptitud": aptitud, "limitante": limitante, "notas": notas,
            "estado": estado, "estado_notas": estado_notas, "estado_completo": not estado_faltan,
            "estado_faltan": estado_faltan,
            "riesgo": riesgo, "riesgo_evaluado": riesgo is not None, "riesgo_faltan": rr["faltan"],
            "riesgo_inundacion_base": rr["inundacion_base"], "riesgo_inundacion": rr["inundacion"],
            "riesgo_erosion": rr["erosion"],
            "partes": partes}


def recomendaciones(c, v, r):
    nombre = c["nombre"].lower()
    recs = []
    if r["riesgo_inundacion"] is not None and r["riesgo_inundacion"] >= 0.4:
        recs.append("🌊 Tu chakra está en zona baja o que se ha inundado antes. Siembra en la parte "
                    "más alta o en camellones, y cosecha antes de la época de crecidas.")
    if r["riesgo_erosion"] is not None and r["riesgo_erosion"] >= 0.5:
        recs.append("⛰️ El terreno es inclinado: cubre el suelo con maní forrajero y siembra árboles como la guaba "
                    "en curvas de nivel para que la lluvia no se lleve la tierra.")
    co = v.get("carbono_org")
    if co is not None and co < 20:
        recs.append("🍂 El suelo tiene poca materia orgánica: deja la hojarasca, agrega abono orgánico y rota con "
                    "plantas que devuelven nitrógeno (maní, fréjol, guaba).")
    ph = v.get("ph")
    if ph is not None and ph < c["ph"][1]:
        recs.append(f"🧪 El suelo es más ácido de lo ideal para esta planta (pH {ph:.1f}). La materia orgánica y "
                    "un poco de ceniza o cal agrícola ayudan; consulta antes a un técnico.")
    if ph is not None and ph > c["ph"][2]:
        recs.append(f"🧪 El suelo es menos ácido de lo ideal para esta planta (pH {ph:.1f}). Consulta a un técnico.")
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
        recs.append(f"📍 Este lugar no es el ideal para esta planta: lo que más limita es: {r['limitante']}.")
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
    opciones.sort(key=lambda x: x[0], reverse=True)
    return opciones[:2]


def semaforo(i):
    return "🟢 Buena" if i >= 70 else "🟡 Regular" if i >= 40 else "🔴 Mala"


# ---------------------------------------------------------------- RESULTADO EN PALABRAS SENCILLAS
def _frase_variable(nombre, valor, rango):
    """Explica en palabras simples por qué una nota Ecocrop es baja (dirección del problema)."""
    bajo = valor is not None and valor < rango[1]
    if nombre == "temperatura":
        return "hace más frío de lo que le gusta (zona alta)" if bajo else "hace más calor de lo que le gusta"
    if nombre == "lluvia":
        return "llueve menos de lo que necesita" if bajo else "llueve más de lo que aguanta"
    return "la tierra es demasiado ácida" if bajo else "la tierra es poco ácida para ella"


def interpretar(clave, v, cob):
    """Convierte todos los cálculos en un resultado fácil de entender para el agricultor.
    Devuelve: color (verde/amarillo/rojo), título, frase, motivos [(icono, texto)], consejos y otras plantas."""
    c = CULTIVOS[clave]
    planta = c["nombre"].lower()
    sembrable = fraccion_sembrable(cob)
    r = evaluar(c, v, sembrable)
    construido = (cob or {}).get(CLASES_WC[50], 0)
    agua = (cob or {}).get(CLASES_WC[80], 0)
    bosque = (cob or {}).get(CLASES_WC[10], 0)

    # ---- Semáforo
    if sembrable is not None and sembrable < 0.2:
        color, titulo = "rojo", "No se puede sembrar aquí"
        frase = ("Lo que dibujaste es ciudad, casas, calles o río. "
                 "Dibuja solo el terreno de tu chakra.")
    elif r["indice"] >= 70:
        color, titulo = "verde", f"Sí, es buen lugar para sembrar {planta}"
        frase = "Las condiciones del lugar le quedan bien a esta planta."
    elif r["indice"] >= 40:
        color, titulo = "amarillo", f"Se puede sembrar {planta}, pero con cuidado"
        frase = "Hay algunas cosas que pueden afectar la cosecha. Mira los consejos."
    else:
        color, titulo = "rojo", f"No es buen lugar para {planta}"
        frase = "Las condiciones del lugar no le quedan bien a esta planta. Mira qué otras plantas sí irían bien."
    # Si el lugar en sí es bueno y lo que baja la nota es que se dibujó sobre casas, calles o río, decirlo claro
    if sembrable is not None and 0.2 <= sembrable < 0.7 and r["indice_base"] >= 60:
        if sembrable < 0.5:
            titulo = "Aquí casi no hay espacio para sembrar"
        frase = ("La tierra y el clima están bien, pero gran parte de lo que dibujaste son casas, calles o río. "
                 "Dibuja solo el terreno de tu chakra para un resultado exacto.")

    # ---- Motivos (✅ a favor, ⚠️ con cuidado, ❌ en contra)
    motivos = []
    if sembrable is not None and sembrable < 0.2:
        return {"color": color, "titulo": titulo, "frase": frase, "puntaje": r["indice"],
                "motivos": [("❌", "Ahí no hay tierra para sembrar.")], "consejos": [], "otras": []}
    if construido >= 0.15:
        motivos.append(("❌" if construido >= 0.5 else "⚠️",
                        f"El {construido * 100:.0f} % de lo que dibujaste son casas o calles."))
    if agua >= 0.15:
        motivos.append(("❌" if agua >= 0.5 else "⚠️", f"El {agua * 100:.0f} % de lo que dibujaste es río o agua."))

    rangos = {"temperatura": ("temp", "temp_media_c", "La temperatura"),
              "lluvia": ("lluvia", "lluvia_anual_mm", "La lluvia"),
              "pH del suelo": ("ph", "ph", "La tierra")}
    for nombre, nota in r["notas"].items():
        k_rango, k_valor, sujeto = rangos[nombre]
        if nota >= 0.9:
            motivos.append(("✅", f"{sujeto} le queda bien a esta planta."))
        else:
            icono = "❌" if nota < 0.5 else "⚠️"
            motivos.append((icono, f"{_frase_variable(nombre.split()[0], v.get(k_valor), c[k_rango]).capitalize()}."))

    ri, re_ = r["riesgo_inundacion_base"], r["riesgo_erosion"]
    if ri is not None:
        if ri >= 1:
            motivos.append(("❌" if c["tolera_inundacion"] < 0.5 else "⚠️",
                            "Es zona baja o junto al río: se puede inundar."))
        elif ri >= 0.5:
            motivos.append(("⚠️", "Es una zona algo baja: con lluvias fuertes se puede encharcar."))
        else:
            motivos.append(("✅", "No es zona de inundación."))
    if re_ is not None:
        if re_ >= 0.5:
            motivos.append(("⚠️", "El terreno es inclinado: la lluvia puede llevarse la tierra."))
        else:
            motivos.append(("✅", "El terreno no es muy inclinado."))
    if r["estado"] is not None and r["estado"] < 0.6:
        lr = v.get("lluvia_reciente_rel") or 1
        motivos.append(("⚠️", "Este año está lloviendo menos de lo normal." if lr < 1
                        else "Este año está lloviendo más de lo normal."))
    if bosque >= 0.6:
        motivos.append(("🌳", "Tu terreno es bosque: no tumbes los árboles grandes, siembra bajo su sombra."))

    # Primero lo malo, luego lo regular, luego lo bueno
    orden = {"❌": 0, "⚠️": 1, "🌳": 2, "✅": 3}
    motivos.sort(key=lambda m: orden.get(m[0], 9))

    # ---- Consejos (sin números técnicos)
    consejos = []
    for rec in recomendaciones(c, v, r):
        if rec.startswith("📍"):
            continue
        rec = re.sub(r"\s*\(pH [\d.,]+\)", "", rec)
        consejos.append(rec)
    consejos = consejos[:3]

    # ---- Otras plantas que irían bien en el mismo lugar
    otras = []
    for k, oc in CULTIVOS.items():
        if k == clave:
            continue
        ind = evaluar(oc, v, sembrable)["indice"]
        if ind >= 70:
            otras.append((ind, oc["nombre"], oc.get("por_que_sumarla", "")))
    otras.sort(key=lambda x: x[0], reverse=True)

    return {"color": color, "titulo": titulo, "frase": frase, "puntaje": r["indice"], "motivos": motivos,
            "consejos": consejos, "otras": otras[:3]}


# ====================================================================== 5. MAPAS DE TODA LA ZONA
# Grilla común de ~110 m (0,001°) donde se juntan todos los mapas, celda por celda.
RES_MAPA = 0.001
ANCHO_M, ALTO_M = int(round((ESTE - OESTE) / RES_MAPA)), int(round((NORTE - SUR) / RES_MAPA))
TR_MAPA = from_origin(OESTE, NORTE, RES_MAPA, RES_MAPA)


def _a_grilla(arr, transform, crs, metodo=Resampling.average, nodata=np.nan, dtype="float32"):
    destino = np.full((ALTO_M, ANCHO_M), nodata, dtype)
    reproject(arr.astype(dtype), destino, src_transform=transform, src_crs=crs, src_nodata=nodata,
              dst_transform=TR_MAPA, dst_crs="EPSG:4326", dst_nodata=nodata, resampling=metodo)
    return destino


def capa_en_grilla(nombre):
    archivo, factor, vmin, vmax, _, _ = CAPAS[nombre]
    ruta = os.path.join(DATOS, archivo)
    if not os.path.exists(ruta):
        return None
    with rasterio.open(ruta) as src:
        a = src.read(1).astype("float32")
        if src.nodata is not None and not np.isnan(src.nodata):
            a[a == src.nodata] = np.nan
        a *= factor
        with np.errstate(invalid="ignore"):
            a[(a < vmin) | (a > vmax)] = np.nan
        return _a_grilla(a, src.transform, src.crs)


def cobertura_en_grilla():
    """Devuelve (clase dominante, fracción construida, fracción sembrable) en la grilla común."""
    ruta_wc, ruta_osm = os.path.join(DATOS, "cobertura.tif"), os.path.join(DATOS, "osm_urbano.tif")
    if not os.path.exists(ruta_wc):
        return None, None, None
    with rasterio.open(ruta_wc) as src:
        wc, tr, crs = src.read(1), src.transform, src.crs
    construido = (wc == 50)
    if os.path.exists(ruta_osm):
        with rasterio.open(ruta_osm) as src:
            osm = src.read(1)
        if osm.shape == wc.shape:
            construido = construido | (osm == 1)
    vacio = wc == 0
    no = np.where(construido | np.isin(wc, [70, 80]), 1.0, np.where(wc == 60, 0.5, 0.0)).astype("float32")
    no[vacio] = np.nan
    constr = construido.astype("float32")
    constr[vacio] = np.nan
    clase = np.where(construido, 50, wc).astype("uint8")
    clase_g = _a_grilla(clase, tr, crs, metodo=Resampling.mode, nodata=0, dtype="uint8")
    return clase_g, _a_grilla(constr, tr, crs), np.clip(1 - _a_grilla(no, tr, crs), 0, 1)


@st.cache_data(show_spinner="Preparando los mapas de toda la zona…")
def grillas_base(version):
    g = {k: capa_en_grilla(k) for k in CAPAS}
    g["cobertura"], g["construido"], g["sembrable"] = cobertura_en_grilla()
    g["elev_ref"] = float(np.nanmean(g["elevacion"])) if g["elevacion"] is not None else None
    t = CLIMA.get("temp_media_c")
    if t is None:
        g["temperatura"] = None
    elif g["elevacion"] is not None:
        g["temperatura"] = temperatura_ajustada(t, g["elevacion"], g["elev_ref"])
    else:
        g["temperatura"] = np.full((ALTO_M, ANCHO_M), t, "float32")
    return g


def mapa_dato(clave, version):
    """Mapa crudo (unidades reales) para la página de mapas."""
    g = grillas_base(version)
    arr = g.get(clave)
    if clave == "construido" and arr is not None:
        return arr * 100
    return arr


def nota_rango_arr(x, abs_min, opt_min, opt_max, abs_max):
    """Lo mismo que nota_rango (Ecocrop) pero para un mapa entero."""
    x = np.asarray(x, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        n = np.where((x >= opt_min) & (x <= opt_max), 1.0,
                     np.where(x < opt_min, (x - abs_min) / (opt_min - abs_min), (abs_max - x) / (abs_max - opt_max)))
    n = np.clip(n, 0, 1)
    n[np.isnan(x)] = np.nan
    return n


def combinar(pares):
    """Promedio ponderado celda por celda que ignora los componentes sin dato."""
    num = np.zeros((ALTO_M, ANCHO_M))
    den = np.zeros((ALTO_M, ANCHO_M))
    for w, x in pares:
        if x is None:
            continue
        x = np.broadcast_to(np.asarray(x, dtype="float64"), (ALTO_M, ANCHO_M))
        ok = ~np.isnan(x)
        num += np.where(ok, w * x, 0)
        den += np.where(ok, w, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


@st.cache_data(show_spinner="Calculando la metodología en toda la zona…")
def mapas_cultivo(clave_cultivo, version):
    """Todas las capas de la metodología para UN cultivo, en la grilla común (0–1, 1 = mejor)."""
    c = CULTIVOS[clave_cultivo]
    g = grillas_base(version)
    vacio = np.full((ALTO_M, ANCHO_M), np.nan)
    lluvia = CLIMA.get("lluvia_anual_mm")
    notas = {
        "temperatura": nota_rango_arr(vacio if g["temperatura"] is None else g["temperatura"], *c["temp"]),
        "lluvia": nota_rango_arr(np.full((ALTO_M, ANCHO_M), np.nan if lluvia is None else lluvia), *c["lluvia"]),
        "ph": nota_rango_arr(vacio if g["ph"] is None else g["ph"], *c["ph"]),
    }
    pila = np.stack(list(notas.values()))
    pila_inf = np.where(np.isnan(pila), np.inf, pila)
    aptitud = pila_inf.min(axis=0)
    aptitud[np.isinf(aptitud)] = np.nan
    limitante = pila_inf.argmin(axis=0).astype("float64")       # 0 temp, 1 lluvia, 2 pH
    limitante[np.isnan(aptitud)] = np.nan

    ndvi = g["ndvi_anom"]
    estado = combinar([
        (1, nota_rango(CLIMA.get("lluvia_reciente_rel"), *RANGO_LLUVIA_RECIENTE)),
        (1, nota_rango(CLIMA.get("hum_raiz_anom"), *RANGO_HUMEDAD)),
        (1, None if ndvi is None else np.clip((ndvi - NDVI_MALO) / (NDVI_BUENO - NDVI_MALO), 0, 1)),
    ])

    alt, agua = g["altura_rel"], g["agua_hist"]
    if alt is None and agua is None:
        inund = None                      # sin datos de relieve el riesgo NO se evalúa (antes contaba como 0)
    else:
        a = np.zeros((ALTO_M, ANCHO_M)) if agua is None else np.nan_to_num(agua, nan=0.0)
        if alt is None:
            inund = np.where(a > 10, 1.0, 0.0)
        else:
            inund = np.where((alt < 3) | (a > 10), 1.0, np.where(alt < 8, 0.5, 0.0))
            inund = np.where(np.isnan(alt), np.nan, inund)      # donde no hay DEM, no hay nota
        inund = inund * (1 - c["tolera_inundacion"])

    p = g["pendiente"]
    if p is None:
        eros = None
    else:
        eros = np.where(p > 15, 1.0, np.where(p > 8, 0.5, 0.0))
        if (CLIMA.get("dias_lluvia_extrema_anio") or 0) < 1:
            eros = eros * 0.7
        eros = np.where(np.isnan(p), np.nan, eros)

    disponibles = [x for x in (inund, eros) if x is not None]
    riesgo = np.maximum.reduce(disponibles) if disponibles else None
    sin_riesgo = None if riesgo is None else 1 - riesgo

    sembrable = g["sembrable"]
    indice = combinar([(PESOS["aptitud"], aptitud), (PESOS["estado"], estado), (PESOS["sin_riesgo"], sin_riesgo)])
    if sembrable is not None:
        indice = indice * np.where(np.isnan(sembrable), 1, sembrable)
    return {"indice": indice, "aptitud": aptitud, "limitante": limitante, "temperatura": notas["temperatura"],
            "ph": notas["ph"], "lluvia": notas["lluvia"], "estado": estado, "sin_riesgo": sin_riesgo,
            "sembrable": sembrable}


def celda(lat, lon):
    """Fila y columna de la grilla común para un punto (None si está fuera de la zona)."""
    f, c = rowcol(TR_MAPA, lon, lat)
    if 0 <= f < ALTO_M and 0 <= c < ANCHO_M:
        return int(f), int(c)
    return None


def valores_en_celda(lat, lon, version):
    """Valores crudos de todos los mapas en un punto, en el mismo formato que analizar()."""
    rc = celda(lat, lon)
    if rc is None:
        return None, None
    g = grillas_base(version)

    def tomar(a):
        if a is None:
            return None
        x = float(a[rc])
        return None if np.isnan(x) else x

    v = {k: tomar(g[k]) for k in CAPAS}
    v.update({k: x for k, x in CLIMA.items() if k != "ultimo_dato"})
    v["temp_media_c"] = tomar(g["temperatura"])
    return v, tomar(g["sembrable"])


# Calculadora (página "Cómo se calcula"): clave -> (dato, mínimo, máximo, paso, etiqueta)
CALC = {
    "calc_temp": ("temp_media_c", 10.0, 35.0, 0.1, "Temperatura media (°C)"),
    "calc_lluvia": ("lluvia_anual_mm", 500.0, 6000.0, 50.0, "Lluvia anual (mm)"),
    "calc_ph": ("ph", 3.5, 8.5, 0.1, "pH del suelo"),
    "calc_lluvia_rec": ("lluvia_reciente_rel", 0.3, 2.0, 0.01, "Lluvia últimos 12 meses (1 = normal)"),
    "calc_hum": ("hum_raiz_anom", -0.3, 0.3, 0.01, "Humedad del suelo vs. normal"),
    "calc_ndvi": ("ndvi_anom", -0.3, 0.3, 0.01, "Cambio del NDVI vs. normal"),
    "calc_alt": ("altura_rel", 0.0, 60.0, 0.5, "Altura sobre la zona baja (m)"),
    "calc_agua": ("agua_hist", 0.0, 100.0, 1.0, "Agua histórica (% del tiempo)"),
    "calc_pend": ("pendiente", 0.0, 45.0, 0.5, "Pendiente (grados)"),
    "calc_lluvia_ext": ("dias_lluvia_extrema_anio", 0.0, 20.0, 0.1, "Días/año con lluvia > 50 mm"),
}


def enviar_a_calculadora(clave_cultivo, v, sembrable):
    """Copia los valores de un punto o chakra a la calculadora (página 'Cómo se calcula')."""
    st.session_state["calc_cultivo"] = clave_cultivo
    for k, (dato, vmin, vmax, _, _) in CALC.items():
        x = v.get(dato)
        if k == "calc_ndvi":
            st.session_state["calc_usar_ndvi"] = x is not None
        if x is not None:
            st.session_state[k] = float(np.clip(x, vmin, vmax))
    st.session_state["calc_semb"] = 100.0 if sembrable is None else float(round(sembrable * 100))
    st.switch_page("paginas/calculo.py")


def estado_archivos():
    """Qué archivos de datos/ existen y cuándo se actualizaron."""
    archivos = [CAPAS[k][0] for k in CAPAS] + ["cobertura.tif", "osm_urbano.tif", "clima.json", "osm_info.json",
                                              "fuente_dem.json"]
    filas = []
    for a in archivos:
        ruta = os.path.join(DATOS, a)
        existe = os.path.exists(ruta)
        fecha = datetime.fromtimestamp(os.path.getmtime(ruta)).strftime("%Y-%m-%d %H:%M") if existe else "—"
        filas.append({"Archivo": a, "¿Está?": "✅" if existe else "❌ falta", "Actualizado": fecha})
    return filas


# ====================================================================== 6. DIBUJO
def _hex(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def a_imagen(x, vmin=0.0, vmax=1.0, colores=ROJO_VERDE):
    """Arreglo → imagen RGBA con una escala de colores (transparente donde no hay dato)."""
    pal = np.array([_hex(c) for c in colores], dtype="float64")
    n = len(pal) - 1
    rango = (vmax - vmin) if vmax > vmin else 1.0
    t = np.clip((np.nan_to_num(x, nan=vmin) - vmin) / rango, 0, 1) * n
    i = np.minimum(t.astype(int), n - 1)
    f = (t - i)[..., None]
    rgb = pal[i] * (1 - f) + pal[i + 1] * f
    alfa = np.where(np.isnan(x), 0, 255)[..., None]
    return np.concatenate([rgb, alfa], axis=2).astype("uint8")


def a_imagen_clases(arr, colores):
    """Mapa de clases (enteros) → imagen RGBA con un color por clase."""
    img = np.zeros(arr.shape + (4,), dtype="uint8")
    for k, color in colores.items():
        img[arr == k] = _hex(color) + [255]
    return img


def mapa_base(zoom=11, alto_zona=True):
    m = folium.Map(location=[(SUR + NORTE) / 2, (OESTE + ESTE) / 2], zoom_start=zoom, tiles=None,
                   control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satélite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Calles").add_to(m)
    if alto_zona:
        folium.Rectangle(bounds=[[SUR, OESTE], [NORTE, ESTE]], color="#2e7d32", weight=2, fill=False,
                         tooltip="Zona piloto con datos").add_to(m)
    return m


def agregar_imagen(m, img, nombre, opacidad=0.65):
    ImageOverlay(img, bounds=[[SUR, OESTE], [NORTE, ESTE]], name=nombre, opacity=opacidad,
                 pixelated=True).add_to(m)


def leyenda_html(items):
    """items: lista de (color, texto) → HTML de leyenda con cuadritos de color."""
    return "<br>".join(f"<span style='display:inline-block;width:12px;height:12px;background:{c};"
                       f"border:1px solid #888;margin-right:6px'></span>{t}" for c, t in items)
