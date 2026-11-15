# ChakraShift — cómo correr la app

Página web en Python (Streamlit). El usuario elige qué sembró, dibuja su chakra en el mapa y recibe el
Índice de Salud de la Chakra (0–100) con recomendaciones. Zona piloto: Tena – Archidona – Puerto Misahuallí.

## Archivos

| Archivo | Para qué |
|---|---|
| `preparar_datos.py` | Se corre UNA vez: descarga los mapas existentes (suelo, agua, relieve, clima NASA) a `datos/` |
| `app.py` | La página web |
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
   `pendiente.tif`, `altura_relativa.tif`, `clima.json`. Si algún mapa da ERROR, los demás siguen sirviendo.
4. Abrir la app:
   ```
   streamlit run app.py
   ```
   Se abre en el navegador (http://localhost:8501).

## Opcional

- **NDVI (estrés de la vegetación):** pedir MOD13Q1 (NDVI) en https://appeears.earthdatacloud.nasa.gov para la
  zona piloto, en GeoTIFF. Poner los .tif en una carpeta `appeears/` junto a estos archivos y volver a correr
  `python preparar_datos.py`.
- **Gemini:** crear una clave en Google AI Studio y antes de abrir la app ejecutar
  `set GEMINI_API_KEY=tu_clave` (Windows) o `export GEMINI_API_KEY=tu_clave` (Mac/Linux).
  En `app.py`, cambiar `MODELO_GEMINI` por el nombre del modelo que aparece en AI Studio.
- **Publicarla con enlace para el jurado:** subir esta carpeta (con `datos/`) a GitHub y desplegarla gratis en
  https://share.streamlit.io . La clave de Gemini va en *Settings → Secrets* como `GEMINI_API_KEY = "..."`.

## Expandir a otra zona

Cambiar `OESTE, SUR, ESTE, NORTE` en `preparar_datos.py` y en `app.py`, y volver a correr `preparar_datos.py`.
Para zonas grandes (toda Napo o Ecuador) conviene usar celdas más grandes para que los archivos no pesen tanto.
