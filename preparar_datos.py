"""
ChakraShift — PASO 1: descargar UNA SOLA VEZ los mapas que ya existen
=====================================================================
Recorta mapas públicos a la zona piloto (Tena – Archidona – Puerto Misahuallí)
y los guarda en la carpeta "datos/". La app (app.py) solo lee esa carpeta:
el usuario nunca espera descargas.

Mapas que descarga (todos ya existen, no los fabricamos):
  - Suelo: SoilGrids (ISRIC), 250 m -> pH, carbono orgánico, arcilla
  - Agua histórica: JRC Global Surface Water (Landsat 1984–2021), 30 m
  - Relieve: Copernicus DEM, 30 m -> pendiente y altura relativa (zonas bajas)
  - Clima: NASA POWER (2001–hoy), ~55 km -> temperatura, lluvia, humedad del suelo
  - Cobertura del suelo: ESA WorldCover 2021 v200, 10 m -> ciudad, agua, bosque, cultivos...
  - Lo construido HOY: OpenStreetMap (Overpass) -> edificios, barrios, calles (se baja al momento)
  - (Opcional) NDVI MODIS desde AppEEARS si existe la carpeta "appeears/"

Uso:  python preparar_datos.py                 (todo)
      python preparar_datos.py cobertura osm   (solo esos pasos; sirve para actualizar)
"""
import glob
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.merge import merge
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import transform as transformar, unary_union
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import minimum_filter

# ---------- Zona piloto (cambiar aquí para expandir a otra zona) ----------
OESTE, SUR, ESTE, NORTE = -77.90, -1.10, -77.60, -0.85
CRS_UTM = "EPSG:32718"  # metros, UTM 18 Sur (Napo)

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "datos")
os.makedirs(CARPETA, exist_ok=True)


def ruta(nombre):
    return os.path.join(CARPETA, nombre)


def recortar(url, salida):
    """Lee SOLO el pedazo de la zona piloto de un mapa en internet y lo guarda como GeoTIFF."""
    with rasterio.open(url) as src:
        b = transform_bounds("EPSG:4326", src.crs, OESTE, SUR, ESTE, NORTE, densify_pts=21)
        w = from_bounds(*b, transform=src.transform)
        w = Window(int(np.floor(w.col_off)), int(np.floor(w.row_off)),
                   int(np.ceil(w.width)) + 2, int(np.ceil(w.height)) + 2)
        w = w.intersection(Window(0, 0, src.width, src.height))
        datos = src.read(1, window=w)
        perfil = {"driver": "GTiff", "height": datos.shape[0], "width": datos.shape[1],
                  "count": 1, "dtype": datos.dtype, "crs": src.crs,
                  "transform": src.window_transform(w), "nodata": src.nodata,
                  "compress": "deflate"}
    with rasterio.open(salida, "w", **perfil) as dst:
        dst.write(datos, 1)
    print("   guardado:", os.path.basename(salida), datos.shape)


def guardar_utm(arr, transform, nombre):
    perfil = {"driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
              "dtype": "float32", "crs": CRS_UTM, "transform": transform,
              "nodata": np.nan, "compress": "deflate"}
    with rasterio.open(ruta(nombre), "w", **perfil) as dst:
        dst.write(arr.astype("float32"), 1)
    print("   guardado:", nombre, arr.shape)


# ---------------------------------------------------------------- SUELO
def suelo():
    print("Suelo (SoilGrids, 250 m)...")
    for var, nombre in [("soc", "soc.tif"), ("phh2o", "ph.tif"), ("clay", "arcilla.tif")]:
        recortar(f"https://files.isric.org/soilgrids/latest/data/{var}/{var}_0-5cm_mean.vrt",
                 ruta(nombre))


# ---------------------------------------------------------------- AGUA
def agua():
    print("Agua histórica (JRC Global Surface Water, 30 m)...")
    recortar("https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/"
             "occurrence_80W_0Nv1_4_2021.tif", ruta("agua_hist.tif"))


# ---------------------------------------------------------------- RELIEVE
# FABDEM v1.2 (Universidad de Bristol): el MISMO DEM de Copernicus GLO-30 pero con la altura de los
# árboles y los edificios eliminada. En la Amazonía esto es más realista para pendiente e inundación.
# Son archivos COG: se leen solo los pedazos de la zona, sin bajar los 40 MB completos.
FABDEM_URL = "https://huggingface.co/buckets/links-ads/fabdem/resolve/tiles"


def _nombre_fabdem(lat, lon):
    ns = f"S{abs(lat):02d}" if lat < 0 else f"N{abs(lat):02d}"
    ew = f"W{abs(lon):03d}" if lon < 0 else f"E{abs(lon):03d}"
    return ns + ew


def _frontera10(v, hacia_arriba):
    """Redondea a múltiplo de 10 hacia abajo (o hacia arriba). Sirve para armar el nombre del paquete de 10°."""
    return int(math.ceil(v / 10) * 10 if hacia_arriba else math.floor(v / 10) * 10)


def _descargar_fabdem():
    """Baja los tiles de FABDEM que cubren la zona piloto y devuelve la lista de archivos temporales."""
    paquete = (f"{_nombre_fabdem(_frontera10(SUR, False), _frontera10(OESTE, False))}-"
               f"{_nombre_fabdem(_frontera10(NORTE, True), _frontera10(ESTE, True))}_FABDEM_V1-2")
    temporales = []
    for lat in range(math.floor(SUR), math.floor(NORTE) + 1):
        for lon in range(math.floor(OESTE), math.floor(ESTE) + 1):
            tile = _nombre_fabdem(lat, lon)
            url = f"{FABDEM_URL}/{paquete}/{tile}_FABDEM_V1-2.tif"
            tmp = ruta(f"_fabdem_{tile}.tif")
            recortar(url, tmp)
            temporales.append(tmp)
    return temporales


def _descargar_copernicus():
    """Respaldo: Copernicus DEM GLO-30 (incluye árboles y techos)."""
    temporales = []
    for lat in (-2, -1, 0):          # probamos los mosaicos vecinos; los que no existen se saltan
        for lon in (-79, -78):
            ns = "S" if lat < 0 else "N"
            nombre = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_W{abs(lon):03d}_00_DEM"
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{nombre}/{nombre}.tif"
            tmp = ruta(f"_dem_{ns}{abs(lat)}_{abs(lon)}.tif")
            try:
                recortar(url, tmp)
                temporales.append(tmp)
            except Exception:
                pass
    return temporales


def relieve():
    print("Relieve (DEM de la zona)...")
    try:
        temporales = _descargar_fabdem()
        fuente = "FABDEM v1.2 (Copernicus GLO-30 sin árboles ni edificios) · 30 m"
    except Exception as e:
        print(f"   FABDEM no disponible ({e}).")
        print("   Se usa el respaldo: Copernicus DEM GLO-30 (30 m).")
        temporales = []
        fuente = None
    if not temporales:
        temporales = _descargar_copernicus()
        fuente = "Copernicus DEM GLO-30 · 30 m"
    if not temporales:
        print("   ¡No se pudo descargar el relieve! Revisa tu internet.")
        return

    fuentes = [rasterio.open(t) for t in temporales]
    mosaico, tr = merge(fuentes, bounds=(OESTE, SUR, ESTE, NORTE))
    crs_dem = fuentes[0].crs
    for f in fuentes:
        f.close()
    for t in temporales:
        os.remove(t)
    dem = mosaico[0].astype("float32")

    # Pasar a metros (UTM, 30 m) para calcular la pendiente bien
    alto, ancho = dem.shape
    izq, arriba = tr.c, tr.f
    der, abajo = izq + tr.a * ancho, arriba + tr.e * alto
    tr_utm, w, h = calculate_default_transform(crs_dem, CRS_UTM, ancho, alto,
                                               izq, abajo, der, arriba, resolution=30)
    z = np.full((h, w), np.nan, dtype="float32")
    reproject(dem, z, src_transform=tr, src_crs=crs_dem, dst_transform=tr_utm,
              dst_crs=CRS_UTM, dst_nodata=np.nan, resampling=Resampling.bilinear)

    dzdy, dzdx = np.gradient(z, 30)
    pendiente = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # Altura sobre el punto más bajo en ~1 km a la redonda: aproximación del HAND.
    # Valores bajos (< 3 m) = zonas bajas que se inundan con facilidad.
    relleno = np.where(np.isnan(z), np.nanmax(z), z)
    altura_rel = z - minimum_filter(relleno, size=33)
    guardar_utm(pendiente, tr_utm, "pendiente.tif")
    guardar_utm(altura_rel, tr_utm, "altura_relativa.tif")
    guardar_utm(z, tr_utm, "elevacion.tif")   # para bajar la temperatura con la altura (-6,5 °C por km)

    # Deja anotado de qué fuente salió el relieve (la app lo muestra en "Datos y fuentes")
    with open(ruta("fuente_dem.json"), "w", encoding="utf-8") as f:
        json.dump({"fuente": fuente, "descargado": datetime.now().isoformat(timespec="minutes"),
                   "resolucion_m": 30,
                   "rango_m": [round(float(np.nanmin(z)), 1), round(float(np.nanmax(z)), 1)]}, f,
                  ensure_ascii=False, indent=2)
    print("   fuente del relieve:", fuente)


# ---------------------------------------------------------------- CLIMA
def clima():
    print("Clima (NASA POWER, diario 2001–hoy)...")
    lat_c, lon_c = (SUR + NORTE) / 2, (OESTE + ESTE) / 2
    fin = (date.today() - timedelta(days=7)).strftime("%Y%m%d")
    url = ("https://power.larc.nasa.gov/api/temporal/daily/point"
           "?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,GWETROOT"
           f"&community=AG&longitude={lon_c:.3f}&latitude={lat_c:.3f}"
           f"&start=20010101&end={fin}&format=JSON")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    p = r.json()["properties"]["parameter"]

    fechas = sorted(p["T2M"].keys())
    def serie(var):
        return np.array([p[var][f] if p[var][f] != -999 else np.nan for f in fechas], dtype=float)
    anios = np.array([int(f[:4]) for f in fechas])
    t2m, tmax, tmin, lluvia, hum = (serie(v) for v in ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "GWETROOT"])

    normal = (anios >= 2001) & (anios <= 2024)
    validos = np.where(~np.isnan(lluvia))[0]
    ult = validos[-1]
    rec12 = slice(max(0, ult - 364), ult + 1)
    rec3 = slice(max(0, ult - 90), ult + 1)

    lluvia_por_anio = np.array([np.nansum(lluvia[anios == a]) for a in range(2001, 2025)])
    def por_anio(condicion):
        return float(np.mean([np.sum(condicion[anios == a]) for a in range(2001, 2025)]))

    ind = {
        "temp_media_c": float(np.nanmean(t2m[normal])),
        "lluvia_anual_mm": float(lluvia_por_anio.mean()),
        "lluvia_reciente_rel": float(np.nansum(lluvia[rec12]) / lluvia_por_anio.mean()),
        "hum_raiz_anom": float(np.nanmean(hum[rec3]) - np.nanmean(hum[normal])),
        "dias_calor_32_anio": por_anio(np.nan_to_num(tmax) > 32),
        "dias_lluvia_extrema_anio": por_anio(np.nan_to_num(lluvia) > 50),
        "dias_helada_anio": por_anio(np.nan_to_num(tmin, nan=99) < 2),
        "tendencia_lluvia_mm_decada": float(np.polyfit(np.arange(2001, 2025), lluvia_por_anio, 1)[0] * 10),
        "ultimo_dato": fechas[ult],
    }
    with open(ruta("clima.json"), "w", encoding="utf-8") as f:
        json.dump(ind, f, ensure_ascii=False, indent=2)
    for k, v in ind.items():
        print(f"   {k:28s} {v}")


# ---------------------------------------------------------------- NDVI (opcional)
def ndvi_appeears():
    archivos = sorted(glob.glob(os.path.join(BASE, "appeears", "*NDVI*doy*.tif")))
    if not archivos:
        print("NDVI: no hay carpeta 'appeears' con datos MODIS. Se omite (la app funciona igual).")
        return
    print(f"NDVI MODIS desde AppEEARS ({len(archivos)} imágenes)...")
    fechas, pilas, perfil = [], [], None
    for f in archivos:
        m = re.search(r"doy(\d{4})(\d{3})", f)
        fechas.append(np.datetime64(f"{m.group(1)}-01-01") + np.timedelta64(int(m.group(2)) - 1, "D"))
        with rasterio.open(f) as s:
            a = s.read(1).astype("float32")
            perfil = s.profile.copy()
        a[a <= -2000] = np.nan
        pilas.append(a)
    pila = np.stack(pilas)
    if np.nanmax(pila) > 2:
        pila *= 0.0001
    fechas = np.array(fechas)
    recientes = fechas >= fechas.max() - np.timedelta64(90, "D")
    actual = np.nanmean(pila[recientes], axis=0)
    anomalia = actual - np.nanmean(pila, axis=0)
    perfil.update(dtype="float32", nodata=np.nan, count=1, compress="deflate")
    for arr, nombre in [(actual, "ndvi_actual.tif"), (anomalia, "ndvi_anom.tif")]:
        with rasterio.open(ruta(nombre), "w", **perfil) as dst:
            dst.write(arr.astype("float32"), 1)
        print("   guardado:", nombre)


# ---------------------------------------------------------------- COBERTURA DEL SUELO
def cobertura():
    """ESA WorldCover 2021 (10 m, Sentinel-1 + Sentinel-2). Clases: 10 bosque, 20 arbustos, 30 pasto,
    40 cultivos, 50 construido (ciudad), 60 suelo desnudo, 80 agua permanente, 90 humedal."""
    print("Cobertura del suelo (ESA WorldCover 2021, 10 m)...")
    # Los mosaicos son de 3° x 3° y se nombran por su esquina sur-oeste
    temporales = []
    for lat in range(math.floor(SUR / 3) * 3, math.floor(NORTE / 3) * 3 + 1, 3):
        for lon in range(math.floor(OESTE / 3) * 3, math.floor(ESTE / 3) * 3 + 1, 3):
            ns, ew = ("S" if lat < 0 else "N"), ("W" if lon < 0 else "E")
            nombre = f"ESA_WorldCover_10m_2021_v200_{ns}{abs(lat):02d}{ew}{abs(lon):03d}_Map.tif"
            tmp = ruta(f"_wc_{ns}{abs(lat)}_{ew}{abs(lon)}.tif")
            recortar(f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/{nombre}", tmp)
            temporales.append(tmp)
    if len(temporales) == 1:
        os.replace(temporales[0], ruta("cobertura.tif"))
    else:
        fuentes = [rasterio.open(t) for t in temporales]
        mosaico, tr = merge(fuentes, bounds=(OESTE, SUR, ESTE, NORTE))
        perfil = fuentes[0].profile.copy()
        for f in fuentes:
            f.close()
        for t in temporales:
            os.remove(t)
        perfil.update(height=mosaico.shape[1], width=mosaico.shape[2], transform=tr, compress="deflate")
        with rasterio.open(ruta("cobertura.tif"), "w", **perfil) as dst:
            dst.write(mosaico)
    print("   guardado: cobertura.tif")


# ---------------------------------------------------------------- LO CONSTRUIDO HOY (OpenStreetMap)
# Ancho aproximado (m) de cada tipo de calle, para convertir la línea en una franja de asfalto
ANCHO_CALLE = {"trunk": 12, "primary": 10, "secondary": 8, "tertiary": 7, "unclassified": 6,
               "residential": 6, "living_street": 5, "service": 4}
# Servidores públicos de Overpass. Si uno está saturado (error 502/504) se prueba el siguiente.
SERVIDORES_OVERPASS = ["https://overpass-api.de/api/interpreter",
                       "https://overpass.kumi.systems/api/interpreter",
                       "https://overpass.private.coffee/api/interpreter"]


def consultar_overpass(consulta, intentos=2):
    """Pide datos a Overpass probando varios servidores: son gratuitos y a veces están saturados."""
    ultimo = None
    for vuelta in range(intentos):
        for url in SERVIDORES_OVERPASS:
            try:
                r = requests.post(url, data={"data": consulta},
                                  headers={"User-Agent": "ChakraShift-hackathon/0.1"}, timeout=300)
                if r.status_code == 200:
                    print(f"   respuesta de {url.split('/')[2]}")
                    return r.json()
                ultimo = f"{url} -> error {r.status_code}"
                print("   " + ultimo + ", probando otro servidor…")
            except Exception as e:
                ultimo = f"{url} -> {e}"
                print("   " + ultimo + ", probando otro servidor…")
    raise RuntimeError(f"Ningún servidor de Overpass respondió ({ultimo}). Prueba más tarde.")


def osm_urbano():
    """Descarga de OpenStreetMap (actualizado al día) edificios, barrios, zonas comerciales/industriales,
    aeropuerto y calles, y los pinta sobre la MISMA grilla de 10 m de cobertura.tif (1 = construido)."""
    print("Lo construido hoy (OpenStreetMap vía Overpass)...")
    if not os.path.exists(ruta("cobertura.tif")):
        print("   Falta cobertura.tif: corre primero el paso 'cobertura'.")
        return
    bb = f"{SUR},{OESTE},{NORTE},{ESTE}"
    calles = "|".join(ANCHO_CALLE)
    consulta = f"""[out:json][timeout:240];
(
  way["building"]({bb});
  relation["building"]({bb});
  way["landuse"~"^(residential|commercial|industrial|retail|construction|garages|railway|military)$"]({bb});
  relation["landuse"~"^(residential|commercial|industrial|retail|construction|garages|railway|military)$"]({bb});
  way["amenity"~"^(parking|school|university|college|hospital|marketplace|fuel)$"]({bb});
  relation["amenity"~"^(parking|school|university|college|hospital|marketplace|fuel)$"]({bb});
  way["aeroway"~"^(aerodrome|runway|apron|taxiway)$"]({bb});
  relation["aeroway"~"^(aerodrome|runway|apron|taxiway)$"]({bb});
  way["highway"~"^({calles})$"]({bb});
);
out body geom;"""
    datos = consultar_overpass(consulta)
    fecha_osm = datos.get("osm3s", {}).get("timestamp_osm_base", "")

    a_utm = Transformer.from_crs("EPSG:4326", CRS_UTM, always_xy=True).transform
    a_geo = Transformer.from_crs(CRS_UTM, "EPSG:4326", always_xy=True).transform
    formas, n_edif, n_zonas, n_calles, n_rel = [], 0, 0, 0, 0
    for el in datos.get("elements", []):
        tags = el.get("tags", {})
        try:
            if el.get("type") == "relation":
                # Relaciones = multipolígonos: varios anillos "outer" y huecos "inner" (ej. barrios grandes).
                exteriores, interiores = [], []
                for miembro in el.get("members", []):
                    pts = [(p["lon"], p["lat"]) for p in miembro.get("geometry", [])]
                    if len(pts) < 3:
                        continue
                    if pts[0] != pts[-1]:
                        pts.append(pts[0])
                    anillo = Polygon(pts)
                    if not anillo.is_valid:
                        anillo = anillo.buffer(0)
                    (interiores if miembro.get("role") == "inner" else exteriores).append(anillo)
                if not exteriores:
                    continue
                g = unary_union(exteriores).buffer(0)
                if interiores:                     # restar los huecos: patios, plazas, ríos dentro del barrio
                    g = g.difference(unary_union(interiores).buffer(0))
                n_rel += 1
            else:
                pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
                if len(pts) < 2:
                    continue
                if "highway" in tags:
                    ancho = ANCHO_CALLE.get(tags["highway"], 5)
                    g = transformar(a_geo, transformar(a_utm, LineString(pts)).buffer(ancho / 2, cap_style=2))
                    n_calles += 1
                elif len(pts) >= 4 and pts[0] == pts[-1]:
                    g = Polygon(pts)
                    if not g.is_valid:
                        g = g.buffer(0)
                    if "building" in tags:
                        n_edif += 1
                    else:
                        n_zonas += 1
                else:
                    continue
        except Exception:
            continue
        if not g.is_empty:
            formas.append((mapping(g), 1))

    with rasterio.open(ruta("cobertura.tif")) as src:
        perfil = src.profile.copy()
        alto, ancho, tr = src.height, src.width, src.transform
    arr = rasterize(formas, out_shape=(alto, ancho), transform=tr, fill=0, dtype="uint8",
                    all_touched=False) if formas else np.zeros((alto, ancho), "uint8")
    perfil.update(dtype="uint8", nodata=255, count=1, compress="deflate")
    with rasterio.open(ruta("osm_urbano.tif"), "w", **perfil) as dst:
        dst.write(arr, 1)
    with open(ruta("osm_info.json"), "w", encoding="utf-8") as f:
        json.dump({"fecha_osm": fecha_osm, "descargado": datetime.now().isoformat(timespec="minutes"),
                   "edificios": n_edif, "zonas_urbanas": n_zonas, "calles": n_calles,
                   "relaciones": n_rel}, f, indent=2)
    print(f"   guardado: osm_urbano.tif ({n_edif} edificios, {n_zonas} zonas urbanas, {n_calles} calles, "
          f"{n_rel} relaciones; OSM al {fecha_osm})")


PASOS = {"suelo": suelo, "agua": agua, "relieve": relieve, "clima": clima, "ndvi": ndvi_appeears,
         "cobertura": cobertura, "osm": osm_urbano}

if __name__ == "__main__":
    elegidos = sys.argv[1:] or list(PASOS)
    for nombre in elegidos:
        if nombre not in PASOS:
            print(f"Paso desconocido '{nombre}'. Opciones: {', '.join(PASOS)}")
            continue
        try:
            PASOS[nombre]()
        except Exception as e:  # si un mapa falla, los demás siguen
            print(f"   ERROR en {nombre}: {e}")
    print("\nListo. Archivos en:", CARPETA)
