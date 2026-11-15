# Bitácora ChakraShift

Registro de cambios, decisiones e ideas de la app (equipo NantuPhase · NASA Space Apps 2026 · Reto 06).
Agregar cada entrada nueva **arriba**, con fecha.

---

## 2026-11-15 (2) — Mapa de calles y porcentaje de idoneidad

- **Mapa base:** de imagen de satélite (Esri) a **OpenStreetMap**: calles, pueblos y ríos se leen más fácil.
  El recuadro de la zona con datos pasó a verde y la chakra dibujada a **azul** (en blanco no se veía sobre OSM).
- **Porcentaje de idoneidad** grande junto al semáforo (ej. *"96 % de idoneidad"*), del mismo color que la luz
  encendida. Es el Índice de Salud de la Chakra (0–100). Se quitó el "Puntaje: x de 100" pequeño del final.
- Probado en el navegador (1366 × 768 y celular 375 × 812): campo al este de Tena → 🟢 96 % de idoneidad.

---

## 2026-11-15 — Interfaz para el agricultor: una sola página con semáforo

### Pedido
- Nada de menú lateral ni secciones separadas (mapas / cálculo / fuentes).
- Una sola página **responsive** (computadora y celular).
- Solo: **mapa** para dibujar la chakra, un **cuadro pequeño en la esquina superior izquierda del mapa** para
  elegir la planta, y al lado el **resultado fácil de entender** (semáforo).
- Todo el cálculo por detrás; nada técnico a la vista.

### Cómo quedó
- **Computadora:** mapa a la izquierda (60 %), resultado a la derecha (40 %).
  **Celular:** mapa arriba, resultado abajo (Streamlit apila las columnas solo).
  > El pedido decía "derecha" dos veces e "izquierda" una vez para el resultado; se dejó a la **derecha**.
  > Para cambiarlo, en `app.py` intercambiar `col_mapa, col_res = st.columns([3, 2])`.
- **Selector de planta** flotando sobre el mapa (CSS `.st-key-selector_planta`, posición absoluta).
  Para dejar libre esa esquina: zoom (+/−) y "Ir a mi ubicación" abajo a la derecha; dibujar (⬟ ▭) y borrar
  arriba a la derecha.
- **Mapa:** imagen de satélite con nombres de pueblos y ríos encima; recuadro amarillo = zona con datos.
  Al dibujar, el mapa **se acerca a la chakra** y la deja pintada (antes, al recalcular, el mapa se reiniciaba
  y el dibujo se perdía). Botón **"✏️ Revisar otra chakra"** para empezar de nuevo.
- **Resultado** (`nucleo.interpretar()`):
  - Semáforo 🔴🟡🟢 + título: *"Sí, es buen lugar para sembrar yuca"* / *"Se puede sembrar …, pero con
    cuidado"* / *"No es buen lugar para …"* / *"No se puede sembrar aquí"* (ciudad o río) /
    *"Aquí casi no hay espacio para sembrar"* (el lugar es bueno pero el dibujo cae sobre casas).
  - Motivos en palabras sencillas con ✅ ⚠️ ❌ (temperatura, lluvia, tierra, inundación, pendiente, casas, río,
    bosque, año más seco/lluvioso). Primero lo malo.
  - Hasta 3 consejos y **otras plantas que irían bien** en ese lugar.
  - Puntaje 0–100 pequeño al final, y aviso de que es una estimación con satélite.
- Textos corregidos: "la cacao" → "esta planta".
- Tema claro y verde (`.streamlit/config.toml`), sin barra ni menú de Streamlit.
- Las 4 páginas anteriores se **guardaron** en `anteriores/paginas_4_secciones/` (no se borraron) por si se
  quieren mostrar al jurado. El botón de Gemini quedó fuera.

### Prueba hecha (navegador, 1366 × 768 y celular 375 × 812)
| Caso | Resultado |
|---|---|
| Rectángulo sobre la ciudad de Tena (yuca) | 🔴 "Aquí casi no hay espacio para sembrar" · ❌ 79 % casas o calles · 21/100 |
| Campo/bosque (yuca, celular) | 🟢 "Sí, es buen lugar para sembrar yuca" · 91/100 · otras: guayusa, maní forrajero, guaba |
| Mismo lugar, cambiando a cacao en el selector | 🟢 se actualiza solo, la chakra sigue dibujada |
| "Revisar otra chakra" | vuelve a las instrucciones, sin bucles |
Registro del servidor: sin errores.

---

## 2026-11-14 (5) — Prueba completa de la app en esta PC

### Cómo se probó
- Python 3.12 instalado en esta PC (Compu Universidad Harley) y entorno `.venv` dentro de `app_chakrashift`.
- `preparar_datos.py` corrido completo: todos los mapas descargados a `datos/` (sin NDVI, que necesita AppEEARS).
- App abierta en `http://localhost:8501` y probada a mano en el navegador + prueba automática
  (`streamlit.testing.v1.AppTest`) de las 4 páginas y de **los 21 mapas** (12 de datos, 9 de resultados).

### Resultados (Yuca)
| Lugar | Índice | Parte sembrable |
|---|---|---|
| Centro de Tena (dibujado en la app) | **12 🔴** "aquí no se puede sembrar" | 12 % (88 % construido) |
| Centro de Tena (cuadro chico, prueba directa) | **0 🔴** | 0 % |
| Centro de Archidona | **4 🔴** | 4 % |
| Orilla del río Napo (Misahuallí) | **44 🟡** | 54 % · riesgo de inundación 90 % |
| Campo/bosque al este de Tena | **99 🟢** | 99 % |

→ El problema original (ciudad = 96 🟢) **quedó resuelto**.

### Errores encontrados y corregidos en la prueba
1. `folium.ImageOverlay` no existe en folium 0.20 → la página de mapas se caía. Ahora se importa de
   `folium.raster_layers`. (**Este error también estaba en la versión anterior de una sola página**: en el
   servidor habría fallado al elegir un cultivo para el mapa.)
2. Tablas que mezclaban números con "sin dato" dejaban un error largo en la consola (Arrow) → ahora todo va
   como texto.
3. En "Evaluar mi chakra" las 4 cifras (aptitud, estado, riesgo, sembrable) se cortaban ("10…") → ahora van
   en 2 × 2.
4. Textos: "la pH del suelo" → "lo que más limita es: pH del suelo"; "Ph" → "pH".

### Para correrla en esta PC
```
cd "C:\Users\HP\Desktop\Hackaton NISAR Metano\app_chakrashift"
.venv\Scripts\python.exe -m streamlit run app.py
```

### Ojo con lo que sigue optimista
- **Estado actual = 100 % casi en todas partes**: sin NDVI solo usa lluvia y humedad de NASA POWER, que hoy
  están normales y son iguales para toda la zona.
- **Aptitud de yuca ≈ 100 % en casi toda la zona**: los rangos de `cultivos.json` son de ejemplo y muy anchos.
  Con los rangos reales de ECOCROP el mapa debería mostrar más diferencias.

---

## 2026-11-14 (4) — DEM más preciso (FABDEM), riesgo honesto y relaciones de OSM

Se cerraron varios pendientes de la bitácora anterior.

### 1. DEM nuevo: FABDEM v1.2 (mejor precisión en selva)
- Antes: **Copernicus GLO-30** (30 m) era un *modelo de superficie*: incluía la altura de los árboles
  (~10–15 m en la Amazonía), así que la pendiente y el HAND salían algo inflados.
- Ahora: el paso `relieve` baja **FABDEM v1.2** (Universidad de Bristol), que es el **mismo Copernicus GLO-30
  con la altura de árboles y edificios eliminada** (modelo de *terreno*). Sigue a 30 m, sin cuenta ni clave.
- Se leen solo los pedazos de la zona desde los COG de Hugging Face (`links-ads/fabdem`); si falla, cae
  automáticamente al Copernicus de siempre. Queda anotado en `datos/fuente_dem.json` y se muestra en la
  página **4. Datos y fuentes**.
- Efecto medido en la zona piloto: altitud media 674,6 → **662,6 m**; pendiente media 10,3° → **8,8°**;
  altura relativa media 60,9 → **55,1 m**. Misma cobertura (1116 × 923 px, 0,3 % sin dato).
- Atribución: FABDEM v1.2 © Universidad de Bristol (uso no comercial), basado en Copernicus DEM.

### 2. El riesgo ya no se cuenta como 0 cuando faltan datos
- Antes, si faltaba el relieve, `riesgo_inundacion` y `riesgo_erosion` devolvían **0** → el índice salía
  optimista (ese 20 % del peso entraba como "sin riesgo" perfecto).
- Ahora devuelven **None** y el componente se **deja fuera** del promedio ponderado (el peso se reparte).
- Nuevo helper `riesgo_total(v, c)` en `nucleo.py`; `evaluar()` devuelve `riesgo_evaluado` y `riesgo_faltan`.
- En los mapas de toda la zona, `sin_riesgo` queda en **NaN** donde no hay relieve, y `combinar()` lo ignora
  celda por celda.
- La app avisa en **Evaluar mi chakra**, **Cómo se calcula**, **Mapas** y **Datos y fuentes**.

### 3. "Estado actual" avisa cuando le falta el NDVI
- `evaluar()` devuelve `estado_completo` y `estado_faltan`. Si no hay NDVI, la app dice que el estado se
  calculó solo con lluvia y humedad y que puede verse mejor de lo real.

### 4. OpenStreetMap: ahora sí se leen las relaciones (multipolígonos)
- La consulta Overpass incluye `relation["building"]`, `relation["landuse"]`, `relation["amenity"]` y
  `relation["aeroway"]`.
- Se arman juntando los anillos `outer` y **restando los `inner`** (huecos: patios, plazas, ríos dentro de un
  barrio). Antes esos barrios grandes se perdían.
- **Ojo:** con `out tags geom` las relaciones llegan **sin miembros** (`members: []`), así que nunca se podían
  armar. Ahora se pide `out body geom`.
- `datos/osm_info.json` guarda además `relaciones`.
- Extra: Overpass se satura seguido. Ahora `consultar_overpass()` prueba **3 servidores** y reintenta
  (overpass-api.de → kumi.systems → private.coffee) en vez de fallar con 502.

### 5. Detalles
- La ficha del mapa **Construido** decía "fuente: OSM" y en realidad es **WorldCover 2021 + OSM**; corregido.
- Tabla del clima en **Datos y fuentes** daba error de tipos en Arrow (mezclaba números y el texto
  `20261107`): ahora todo va como texto formateado.

### Verificación hecha (esta PC sí puede correr Python: `.venv` en la carpeta)
- `py_compile` de todos los archivos: OK.
- Las 4 páginas se ejecutaron con `streamlit.testing.v1.AppTest`: **0 excepciones**.
- `preparar_datos.py relieve` corrido de verdad: FABDEM descargado y aplicado.
- `preparar_datos.py osm` corrido de verdad, con dos vueltas de reintentos: **8025 edificios, 130 zonas
  urbanas, 2323 calles y 5 relaciones** (OSM al 2026-11-14T19:18:37Z).

### Sigue pendiente
- **NDVI MODIS**: falta bajarlo de AppEEARS (necesita cuenta) → el estado actual sigue optimista.
- **Umbrales** (sembrable < 20 %, construido ≥ 15 %): decisión del equipo.
- **Cobertura más reciente que 2021** (Dynamic World / Sentinel-2): necesita cuenta o es frágil por nubes.
- **Validación en campo** con 5–10 chakras reales.

---

## 2026-11-14 (3) — La app se divide en 4 páginas y el cálculo va en su propio archivo

### Idea
Separar todo: primero **ver los mapas** uno por uno, luego **entender el cálculo** (qué usa y cómo funciona),
luego **evaluar la chakra**, y aparte **de dónde salen los datos**.

### Nueva estructura de archivos
```
app_chakrashift/
├── app.py              ← solo el menú (4 páginas)
├── nucleo.py           ← TODOS los datos y cálculos (Ecocrop, riesgo, sembrable, mapas de la zona)
├── paginas/
│   ├── mapas.py        ← 1. 🗺️ Mapas
│   ├── calculo.py      ← 2. 🧮 Cómo se calcula
│   ├── mi_chakra.py    ← 3. 🌱 Evaluar mi chakra
│   └── fuentes.py      ← 4. 📚 Datos y fuentes
├── preparar_datos.py   ← descarga los mapas a datos/
├── cultivos.json
└── datos/
```

### Qué hace cada página
1. **🗺️ Mapas** — eliges *Datos de satélite* (cobertura, construido, altitud, temperatura, pH, carbono,
   arcilla, pendiente, altura relativa, agua histórica, NDVI) o *Resultados de la metodología* (índice,
   aptitud, factor limitante, nota temperatura/pH/lluvia, estado, sin riesgo, sembrable). Se muestra **un
   mapa a la vez** con su leyenda y, al lado: qué es, fuente, cómo se obtiene, cómo leerlo y en qué parte del
   cálculo se usa, más estadísticas de la zona. **Clic en un punto** → todos los valores de ese lugar y botón
   para ver su cálculo paso a paso.
2. **🧮 Cómo se calcula** — diagrama del flujo y **calculadora**: deslizadores con cada dato; se ve en vivo
   el Paso 1 (notas Ecocrop con gráfico de trapecio), Paso 2 (aptitud = mínimo), Paso 3 (estado), Paso 4
   (riesgo), Paso 5 (pesos) y Paso 6 (× sembrable). Tabla de rangos de cultivos.
3. **🌱 Evaluar mi chakra** — lo de antes (dibujar, índice, recomendaciones) + botón "ver el cálculo paso a
   paso" que lleva los valores de la chakra a la calculadora.
4. **📚 Datos y fuentes** — tabla de qué dato usa cada componente y si varía dentro de la zona; qué archivos
   están descargados y su fecha; clima de NASA POWER; fecha de OpenStreetMap; límites de los datos.

### Notas técnicas
- Requiere **Streamlit ≥ 1.38** (usa `st.navigation`). Si el servidor tiene uno más viejo:
  `pip install -U streamlit streamlit-folium`.
- Para el servidor hay que copiar **toda** la carpeta (incluida `paginas/` y `nucleo.py`), no solo `app.py`.

---

## 2026-11-14 (2) — Mapa Ecocrop de toda la zona (todas las capas combinadas)

### Idea
Que el usuario no solo vea la nota de su chakra, sino un **mapa de toda la zona** donde se vea cada
componente de la metodología por separado y combinado, para poder **verificar** de dónde sale la nota.

### Cómo funciona
1. Todos los mapas se llevan a una **grilla común de ~110 m (0,001°)**, promediando los píxeles finos
   (WorldCover 10 m, DEM 30 m) y repartiendo los gruesos (SoilGrids 250 m).
2. En **cada celda** se aplica la misma fórmula que a la chakra dibujada:
   - Nota temperatura, nota lluvia, nota pH → función trapecio Ecocrop (FAO).
   - **Aptitud Ecocrop = la nota más baja** (ley del mínimo: lo que más limita manda).
   - Estado actual, riesgo (inundación/erosión) y parte sembrable.
   - **Índice = [50 % aptitud + 30 % estado + 20 % (1 − riesgo)] × parte sembrable.**
3. En la app aparece el selector **"🗺️ Ver en el mapa la aptitud de toda la zona para: …"**. Cada componente es
   una capa del mapa (botón de capas): ⭐ Índice (visible al inicio), Aptitud Ecocrop, nota temperatura,
   nota pH, nota lluvia, sin riesgo, parte sembrable y **Factor limitante** (🟧 temp · 🟦 lluvia · 🟪 pH).
   Colores: rojo = 0 (malo) → amarillo → verde = 100 (bueno).

### Mejora de la temperatura
- NASA POWER da una sola temperatura para ~55 km; con eso la nota de temperatura era igual en toda la zona.
- Ahora se ajusta por altitud: **T = T_POWER − 6,5 °C/km × (altitud − altitud media de la zona)**
  (gradiente térmico estándar). Así la nota de temperatura sí cambia entre el valle del Napo y las lomas.
- Se aplica igual en el mapa y en la chakra dibujada. Requiere el archivo nuevo `datos/elevacion.tif`
  → hay que volver a correr `python preparar_datos.py relieve`.

### Limitaciones a decir en la presentación
- La **lluvia** sigue siendo un solo valor (NASA POWER ~55 km): su capa sale de un solo color. Mejora posible:
  CHIRPS (5 km) o GPM IMERG (10 km, NASA).
- El **pH** viene de SoilGrids (modelo a 250 m): es una estimación, no una muestra de suelo.
- Altitud media de la zona como referencia de POWER es una aproximación.

### Para actualizar el servidor
```
python preparar_datos.py relieve cobertura osm
streamlit run app.py --server.address 0.0.0.0
```

---

## 2026-11-14 — La app decía "apto" incluso en plena ciudad

### Problema
- Al dibujar la chakra sobre el centro de Tena (asfalto, edificios) la app daba ~96/100 🟢 "Buena".
- Prueba en la app del servidor (`http://10.254.2.56:8501`): Yuca, rectángulo junto a Tena →
  Aptitud 91 %, Estado 100 %, Riesgo 0 %, índice 96.

### Causa (diagnóstico)
1. **No había ningún mapa de cobertura del suelo.** La app solo miraba clima, suelo, agua y relieve:
   - El **clima** (NASA POWER, ~55 km) es **un solo valor para toda la zona**: ciudad y campo dan lo mismo.
   - El **suelo** (SoilGrids, 250 m) es un modelo que **predice pH y carbono también debajo de la ciudad**
     (no "sabe" que hay asfalto).
   - Tena está en terreno alto y no tan inclinado → riesgo 0 %.
   - Resultado: nada en la fórmula podía bajar la nota por estar sobre casas o calles.
2. **Los datos que faltan se ignoraban en silencio** y eso subía la nota (ej.: sin NDVI el "estado actual"
   solo usa la lluvia y la humedad, que son iguales para toda la zona). Si no hay ningún mapa, el índice
   llegaba a 100.

### Cambios hechos
**`preparar_datos.py`**
- Nuevo paso `cobertura`: descarga **ESA WorldCover 2021 v200** (10 m, Sentinel-1 + Sentinel-2) →
  `datos/cobertura.tif`. Clases: 10 bosque, 20 arbustos, 30 pasto, 40 cultivos, **50 construido**,
  60 suelo desnudo, 80 agua permanente, 90 humedal.
- Nuevo paso `osm`: descarga de **OpenStreetMap (Overpass API)**, actualizado al día, los edificios,
  barrios (landuse residencial/comercial/industrial), escuelas, hospitales, parqueaderos, aeropuerto y
  **calles** (convertidas en franjas de 4–12 m según el tipo de vía). Se pinta sobre la misma grilla de
  10 m → `datos/osm_urbano.tif` + `datos/osm_info.json` (fecha de OSM y cuántos edificios/calles).
  - Prueba hecha hoy: solo en el centro de Tena (≈2 × 3 km) OSM tiene **790** edificios/zonas urbanas,
    con datos al 2026-11-14.
- Ahora se puede correr **solo una parte**: `python preparar_datos.py cobertura osm`.

**`app.py`**
- Calcula qué **porcentaje de la chakra** es cada tipo de cobertura.
  "Construido" = WorldCover clase 50 **o** lo que OSM marca como edificio/calle/barrio
  (OSM capta lo que se construyó después de 2021).
- Nueva **Parte sembrable** = 1 − construido − agua permanente − ½ suelo desnudo.
- **Índice final = índice anterior × parte sembrable.** Sobre asfalto/techos el índice cae a 0 🔴.
- Mensajes nuevos:
  - Sembrable < 20 % → "aquí no se puede sembrar" y no da consejos de cultivo.
  - Construido ≥ 15 % → aviso de que parte del dibujo son casas o calles.
  - Bosque ≥ 60 % → recomienda chakra bajo sombra, no talar.
  - Si falta `cobertura.tif` → error rojo visible (antes fallaba en silencio).
  - Lista de mapas que faltan.
- Nueva métrica "Sembrable" junto a Aptitud / Estado / Riesgo.
- La tabla "Datos de tu chakra" muestra los % de cobertura y la fecha de OpenStreetMap.
- Se añadió la sección **"¿Cómo se calcula el Índice de Salud de la Chakra?"** dentro de la app.
- El caché de resultados se invalida cuando se actualizan los archivos de `datos/`.

### Para que funcione en el servidor (la PC de `10.254.2.56`)
1. Copiar a esa PC los archivos nuevos `app.py`, `preparar_datos.py`, `LEEME.md`, `BITACORA.md`.
2. En esa PC, dentro de la carpeta de la app:
   ```
   python preparar_datos.py cobertura osm
   ```
   (descarga ~10 MB de WorldCover y la consulta a OSM; tarda 1–3 minutos).
3. Reiniciar Streamlit (Ctrl+C y `streamlit run app.py --server.address 0.0.0.0`).
4. Probar: dibujar sobre el centro de Tena → debe salir 🔴 cerca de 0. Dibujar sobre una chakra/pasto
   → debe salir parecido a antes.

> Nota: esta PC (Compu Universidad Harley) no tiene Python instalado, así que el código **no se pudo
> ejecutar aquí**; se verificó que las dos fuentes de datos responden (WorldCover 200 OK, Overpass OK).
> La primera corrida en el servidor es la prueba real.

---

## Metodología actual (resumen)

**Índice de Salud de la Chakra = [50 % Aptitud + 30 % Estado actual + 20 % (1 − Riesgo)] × Parte sembrable**

| Componente | Qué mide | Cómo | Fuente · resolución |
|---|---|---|---|
| Parte sembrable | ¿Se puede sembrar físicamente? | 1 − construido − agua − ½ suelo desnudo | ESA WorldCover 2021 · 10 m + OpenStreetMap (al día) |
| Aptitud | ¿El lugar le sirve al cultivo? | Método **Ecocrop (FAO)**: 1 en rango óptimo, baja en línea recta a 0 en el límite absoluto; para temperatura (ajustada por altitud), lluvia y pH. Se toma **la peor** (factor limitante) | NASA POWER (~55 km) + Copernicus DEM (30 m), SoilGrids (250 m) |
| Estado actual | ¿Cómo está ahora vs. lo normal? | Promedio de: lluvia últimos 12 meses / normal; humedad del suelo últimos 3 meses − normal; cambio de NDVI | NASA POWER; MODIS NDVI (opcional, AppEEARS) |
| Riesgo | Inundación o erosión | Inundación: altura relativa < 3 m o > 10 % del tiempo con agua (menos lo que tolera el cultivo). Erosión: pendiente > 8° (media) o > 15° (alta) | Copernicus DEM 30 m, JRC Global Surface Water 30 m |

Semáforo: 🟢 ≥ 70 · 🟡 40–69 · 🔴 < 40.

Rangos de cada cultivo: `cultivos.json` (todavía **valores de ejemplo**; Amelia los reemplaza con ECOCROP/FAO).

---

## Ideas y pendientes
- [ ] **Datos más recientes que 2021 para la cobertura:** Google **Dynamic World** (10 m, casi en tiempo real,
      Sentinel-2) necesita cuenta de Google Earth Engine. Alternativa sin cuenta: armar NDVI reciente de
      Sentinel-2 desde el catálogo abierto *Earth Search* (AWS) — difícil por las nubes de la Amazonía.
- [ ] **NDVI MODIS** (AppEEARS) aún no está cargado en el servidor → "Estado actual" sale alto para todos.
- [ ] Riesgo: hoy si falta el mapa de relieve el riesgo cuenta como 0 (optimista). Decidir si mejor se excluye.
- [ ] OSM: no se leen todavía las "relaciones" (polígonos con huecos, ej. algunos barrios grandes).
- [ ] Revisar con el equipo los umbrales: sembrable < 20 % = "no se puede", construido ≥ 15 % = aviso.
- [ ] Mostrar en el mapa una capa con lo construido (WorldCover + OSM) para que el usuario lo vea.
- [ ] Validar en campo: elegir 5–10 chakras reales conocidas y comparar con lo que dice la app.
