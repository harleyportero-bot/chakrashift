"""
ChakraShift — página web (una sola página, para computadora y celular)
======================================================================
El agricultor:
  1. Elige la planta en el cuadro de la esquina del mapa.
  2. Dibuja su chakra en el mapa.
  3. Ve al lado (o abajo en el celular) un semáforo con el resultado en palabras sencillas.

Todo el cálculo (mapas de satélite, metodología Ecocrop, riesgos, parte sembrable) se hace por detrás
en nucleo.py. Los mapas se descargan una vez con preparar_datos.py.
Uso:  streamlit run app.py
"""
import json

import folium
import streamlit as st
from folium.plugins import Draw, LocateControl
from shapely.geometry import box, shape
from streamlit_folium import st_folium

import nucleo as N

st.set_page_config(page_title="ChakraShift · ¿Puedo sembrar aquí?", page_icon="🌱", layout="wide",
                   initial_sidebar_state="collapsed")

COLORES = {"verde": "#2e7d32", "amarillo": "#f9a825", "rojo": "#c62828"}

st.markdown("""
<style>
  /* Página limpia: sin menú lateral ni barra de Streamlit */
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"],
  [data-testid="stToolbar"], footer {display: none !important;}
  .block-container {padding: 1rem 1.5rem 1rem 1.5rem; max-width: 1400px;}
  h1.titulo {font-size: 1.6rem; margin: 0 0 .6rem 0; padding: 0;}

  /* El cuadro para elegir la planta flota sobre la esquina superior izquierda del mapa */
  .st-key-caja_mapa {position: relative;}
  .st-key-selector_planta {
      position: absolute; top: 10px; left: 10px; z-index: 1000; width: 230px;
      background: #ffffff; border-radius: 12px; padding: 8px 10px 4px 10px;
      box-shadow: 0 2px 10px rgba(0,0,0,.25);
  }
  .st-key-selector_planta label p {font-weight: 600; color: #1b5e20;}

  /* Tarjeta del resultado */
  .resultado {border-radius: 16px; padding: 18px 20px; border: 3px solid var(--color);
              background: color-mix(in srgb, var(--color) 8%, white);}
  .cabecera {display: flex; align-items: center; gap: 18px; flex-wrap: wrap; margin-bottom: 12px;}
  .semaforo {display: flex; gap: 10px; background: #263238; border-radius: 40px; padding: 8px 12px;
             width: max-content;}
  .porcentaje {line-height: 1;}
  .porcentaje .valor {font-size: 2.6rem; font-weight: 800; color: var(--color);}
  .porcentaje .etiqueta {display: block; font-size: .85rem; opacity: .75; margin-top: 2px;}
  .luz {width: 34px; height: 34px; border-radius: 50%; opacity: .18;}
  .luz.on {opacity: 1; box-shadow: 0 0 14px 3px var(--brillo);}
  .resultado h2 {color: var(--color); font-size: 1.45rem; line-height: 1.25; margin: 0 0 6px 0; padding: 0;}
  .resultado p.frase {font-size: 1.05rem; margin: 0 0 10px 0;}
  .resultado ul {list-style: none; padding-left: 0; margin: 0 0 6px 0;}
  .resultado li {font-size: 1rem; margin: 6px 0;}
  .resultado h4 {margin: 14px 0 4px 0; font-size: 1.05rem;}
  .puntaje {font-size: .85rem; opacity: .7;}
  .pasos {font-size: 1.1rem; line-height: 1.9;}
  .nota {font-size: .8rem; opacity: .65; margin-top: 10px;}

  @media (max-width: 640px) {
      .block-container {padding: .6rem .6rem;}
      h1.titulo {font-size: 1.25rem;}
      .st-key-selector_planta {width: 180px; top: 8px; left: 8px;}
      .resultado h2 {font-size: 1.25rem;}
  }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='titulo'>🌱 ChakraShift · ¿Puedo sembrar aquí?</h1>", unsafe_allow_html=True)

col_mapa, col_res = st.columns([3, 2], gap="medium")

# ====================================================================== MAPA + SELECTOR DE PLANTA
with col_mapa:
    with st.container(key="caja_mapa"):
        with st.container(key="selector_planta"):
            planta = st.selectbox("🌱 ¿Qué quieres sembrar?", list(N.CULTIVOS),
                                  format_func=lambda k: N.CULTIVOS[k]["nombre"])

        chakra = st.session_state.get("chakra")       # la última chakra dibujada (se guarda entre recargas)
        m = folium.Map(location=[(N.SUR + N.NORTE) / 2, (N.OESTE + N.ESTE) / 2], zoom_start=12, tiles=None,
                       control_scale=True, zoom_control="bottomright")
        folium.TileLayer("OpenStreetMap", name="Mapa").add_to(m)   # calles, pueblos y ríos: fácil de leer
        folium.Rectangle(bounds=[[N.SUR, N.OESTE], [N.NORTE, N.ESTE]], color="#2e7d32", weight=2, fill=False,
                         dash_array="6", tooltip="Zona con datos").add_to(m)
        Draw(position="topright",
             draw_options={"polyline": False, "circle": False, "circlemarker": False, "marker": False,
                           "polygon": {"shapeOptions": {"color": "#1565c0", "weight": 3}},
                           "rectangle": {"shapeOptions": {"color": "#1565c0", "weight": 3}}},
             edit_options={"edit": False}).add_to(m)
        LocateControl(position="bottomright", strings={"title": "Ir a mi ubicación"}).add_to(m)
        if chakra:   # volver a pintar la chakra y acercar el mapa a ella
            folium.GeoJson(chakra["geometry"], name="Mi chakra", tooltip="Mi chakra",
                           style_function=lambda _: {"color": "#1565c0", "weight": 3, "fillOpacity": 0.15}).add_to(m)
            x0, y0, x1, y1 = shape(chakra["geometry"]).bounds
            m.fit_bounds([[y0, x0], [y1, x1]], max_zoom=17, padding=(40, 40))
        salida = st_folium(m, height=600, use_container_width=True, returned_objects=["last_active_drawing"],
                           key="mapa")

    nuevo = (salida or {}).get("last_active_drawing")
    descartada = st.session_state.get("descartada")
    if nuevo and nuevo["geometry"] != descartada and (not chakra or nuevo["geometry"] != chakra["geometry"]):
        st.session_state["chakra"] = nuevo
        st.rerun()

# ====================================================================== RESULTADO
with col_res:
    dibujo = st.session_state.get("chakra")
    nombre_planta = N.CULTIVOS[planta]["nombre"].lower()

    if not dibujo:
        st.markdown(f"""
<div class="pasos">
<b>¿Cómo se usa?</b><br>
1️⃣ Elige la planta en el cuadro blanco del mapa.<br>
2️⃣ Busca tu chakra en el mapa (puedes acercarte con + y −).<br>
3️⃣ Toca el botón ⬟ o ▭ (arriba a la derecha del mapa) y dibuja el contorno de tu chakra.<br>
4️⃣ Aquí aparecerá si es buen lugar para sembrar <b>{nombre_planta}</b>.
</div>""", unsafe_allow_html=True)
        st.stop()

    geom = shape(dibujo["geometry"])
    if not geom.intersects(box(N.OESTE, N.SUR, N.ESTE, N.NORTE)):
        st.warning("Tu chakra está fuera de la zona con datos (el recuadro amarillo del mapa: Tena, Archidona y "
                   "Puerto Misahuallí). Por ahora solo podemos revisar esa zona.")
        st.stop()

    with st.spinner("Revisando tu chakra con datos de satélite…"):
        v, cob = N.analizar(json.dumps(dibujo["geometry"]), N.version_datos())
        res = N.interpretar(planta, v, cob)

    color = COLORES[res["color"]]
    luces = "".join(
        f"<div class='luz{' on' if res['color'] == k else ''}' style='background:{COLORES[k]};--brillo:{COLORES[k]}'>"
        f"</div>" for k in ("rojo", "amarillo", "verde"))
    motivos = "".join(f"<li>{icono} {texto}</li>" for icono, texto in res["motivos"])
    consejos = "".join(f"<li>{texto}</li>" for texto in res["consejos"])
    otras = "".join(f"<li>🌿 <b>{nombre}</b>{': ' + por_que if por_que else ''}</li>"
                    for _, nombre, por_que in res["otras"])

    html = f"""
<div class="resultado" style="--color:{color}">
  <div class="cabecera">
    <div class="semaforo">{luces}</div>
    <div class="porcentaje"><span class="valor">{res['puntaje']} %</span>
      <span class="etiqueta">de idoneidad</span></div>
  </div>
  <h2>{res['titulo']}</h2>
  <p class="frase">{res['frase']}</p>
  <ul>{motivos}</ul>
  {f'<h4>💡 Consejos</h4><ul>{consejos}</ul>' if consejos else ''}
  {f'<h4>🌿 Otras plantas que irían bien aquí</h4><ul>{otras}</ul>' if otras else ''}
</div>
<div class="nota">Resultado estimado con datos de satélites (NASA, ESA y otros). No reemplaza la visita de un
técnico agrícola.</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    if st.button("✏️ Revisar otra chakra", use_container_width=True):
        st.session_state["descartada"] = st.session_state.pop("chakra")["geometry"]
        st.rerun()
