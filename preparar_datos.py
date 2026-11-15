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
  - (Opcional) NDVI MODIS desde AppEEARS si existe la carpeta "appeears/"

Uso:  python preparar_datos.py
"""
import glob
import json
import os
import re
from datetime import date, timedelta

import numpy as np
import rasterio
import requests
from rasterio.merge import merge
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
    print("1/5 Suelo (SoilGrids, 250 m)...")
    for var, nombre in [("soc", "soc.tif"), ("phh2o", "ph.tif"), ("clay", "arcilla.tif")]:
        recortar(f"https://files.isric.org/soilgrids/latest/data/{var}/{var}_0-5cm_mean.vrt",
                 ruta(nombre))


# ---------------------------------------------------------------- AGUA
def agua():
    print("2/5 Agua histórica (JRC Global Surface Water, 30 m)...")
    recortar("https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/"
             "occurrence_80W_0Nv1_4_2021.tif", ruta("agua_hist.tif"))


# ---------------------------------------------------------------- RELIEVE
def relieve():
    print("3/5 Relieve (Copernicus DEM, 30 m)...")
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


# ---------------------------------------------------------------- CLIMA
def clima():
    print("4/5 Clima (NASA POWER, diario 2001–hoy)...")
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
        print("5/5 NDVI: no hay carpeta 'appeears' con datos MODIS. Se omite (la app funciona igual).")
        return
    print(f"5/5 NDVI MODIS desde AppEEARS ({len(archivos)} imágenes)...")
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


if __name__ == "__main__":
    for paso in (suelo, agua, relieve, clima, ndvi_appeears):
        try:
            paso()
        except Exception as e:  # si un mapa falla, los demás siguen
            print(f"   ERROR en {paso.__name__}: {e}")
    print("\nListo. Archivos en:", CARPETA)
