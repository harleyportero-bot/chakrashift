# ChakraShift — cómo correr la app

Página web en Python (Streamlit), **una sola página** para computadora y celular. El agricultor elige la planta
en el cuadro de la esquina del mapa, dibuja su chakra y al lado (abajo en el celular) ve un **semáforo** con el
resultado en palabras sencillas. Todo el cálculo se hace por detrás. Zona piloto: Tena – Archidona – Puerto Misahuallí.

## Archivos

| Archivo | Para qué |
|---|---|
| `preparar_datos.py` | Se corre UNA vez: descarga los mapas existentes (suelo, agua, relieve, clima NASA, cobertura, OSM) a `datos/` |
| `app.py` | La página web: mapa + selector de planta + semáforo con el resultado |
| `nucleo.py` | Todos los datos y cálculos (metodología Ecocrop, riesgo, parte sembrable) y `interpretar()`, que traduce el cálculo a frases sencillas |
| `.streamlit/config.toml` | Tema claro y sin barra de Streamlit |
| `anteriores/paginas_4_secciones/` | Versión anterior de 4 páginas (mapas, cálculo, chakra, fuentes), guardada por si se necesita para la presentación técnica. La app ya no la usa |
| `BITACORA.md` | Registro de cambios e ideas del equipo |
| `cultivos.json` | Tabla de cultivos (valores de ejemplo: Amelia los reemplaza con fuentes ECOCROP/FAO) |
| `requirements.txt` | Librerías que hay que instalar |

## Pasos (en la computadora de quien tenga Python 3.10 o más nuevo)

1. Abrir una terminal dentro de esta carpeta.
2. Instalar librerías:
   ```
   pip install -r requirements.txt
   ```
3. Descargar los mapas (tarda unos minutos, necesita internet):
   ```
   python preparar_datos.py
   ```
   Debe aparecer la carpeta `datos/` con: `soc.tif`, `ph.tif`, `arcilla.tif`, `agua_hist.tif`,
   `pendiente.tif`, `altura_relativa.tif`, `elevacion.tif`, `fuente_dem.json`, `clima.json`,
   `cobertura.tif`, `osm_urbano.tif`, `osm_info.json`.
   Si algún mapa da ERROR, los demás siguen sirviendo.

   Para **actualizar solo una parte** (por ejemplo, traer los edificios y calles de OpenStreetMap de hoy):
   ```
   python preparar_datos.py cobertura osm
   ```
   Pasos disponibles: `suelo agua relieve clima ndvi cobertura osm`.
4. Abrir la app **desde esta carpeta** (así toma el tema de `.streamlit/config.toml`):
   ```
   streamlit run app.py --server.address 0.0.0.0
   ```
   Se abre en el navegador (http://localhost:8501). Desde un celular en la misma red: `http://IP-de-la-PC:8501`.
   Nota: el botón "Ir a mi ubicación" del mapa solo funciona en `localhost` o con `https` (regla de los navegadores).

## Opcional

- **NDVI (estrés de la vegetación):** pedir MOD13Q1 (NDVI) en https://appeears.earthdatacloud.nasa.gov para la
  zona piloto, en GeoTIFF. Poner los .tif en una carpeta `appeears/` junto a estos archivos y volver a correr
  `python preparar_datos.py`.
- **Gemini:** la página única ya no tiene el botón "Explícamelo con Gemini" (el resultado ya sale en palabras
  sencillas). El código anterior quedó en `anteriores/paginas_4_secciones/mi_chakra.py`.
- **Publicarla con enlace para el jurado:** subir esta carpeta (con `datos/`) a GitHub y desplegarla gratis en
  https://share.streamlit.io .

## Expandir a otra zona

Cambiar `OESTE, SUR, ESTE, NORTE` en `preparar_datos.py` y en `nucleo.py`, y volver a correr
`preparar_datos.py`.
Para zonas grandes (toda Napo o Ecuador) conviene usar celdas más grandes para que los archivos no pesen tanto.

## Relieve (DEM)

`python preparar_datos.py relieve` baja **FABDEM v1.2** (30 m, Copernicus sin árboles ni edificios), que en
selva es más preciso para pendiente e inundación. Si FABDEM no responde, usa **Copernicus GLO-30** como
respaldo. La fuente usada queda en `datos/fuente_dem.json`.
