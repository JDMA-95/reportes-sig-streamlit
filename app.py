# ==============================================================================
# app.py
# Streamlit app: el usuario sube el área de estudio (KML), marca qué cruces
# quiere consultar y ve una vista previa (tablas + mapas) — sin escribir
# código. Puerto de la app R/Shiny (ver ../reportes_sig/reportes_sig/app.R).
#
# Correr localmente:
#   streamlit run app.py
# ==============================================================================

import os
import tempfile

import matplotlib

matplotlib.use("Agg")

import streamlit as st
from streamlit_folium import st_folium

from core import config as cfg
from core import exportar
from core import mapas_folium as mapas
from core.io_capas import cargar_aoi_kml, cargar_capa, invalidar_cache_capas
from core.procesamiento import cruce_distritos, ejecutar_cruces, ok_resultado


def _mostrar_mapa(fig, key):
    st_folium(fig, key=key, height=500, use_container_width=True, returned_objects=[])


def _tabla(df):
    # st.dataframe() muestra CUALQUIER valor faltante (NaN, pd.NA, None) como
    # el texto literal "None" -- pasa seguido con columnas reales que no
    # tienen el candidato esperado (ej. "población"/"hogares" en comunidades
    # MIDAGRI, ver README). fillna("") lo deja en blanco, más limpio.
    st.dataframe(df.fillna(""), width="stretch", hide_index=True)


def _encabezado_sidebar(icono, texto, badge=None):
    """Header de sección del sidebar con el mismo patrón visual que GEOPERÚ:
    icono + texto en negrita + badge circular opcional con un conteo."""
    html_badge = f'<span class="count-badge">{badge}</span>' if badge else ""
    st.markdown(
        f'<div class="sidebar-heading">{icono} <span class="sidebar-heading-text">{texto}</span>{html_badge}</div>',
        unsafe_allow_html=True,
    )

st.set_page_config(page_title=cfg.CONFIG_REPORTE["titulo_reporte"], page_icon="🗺️", layout="wide")

# ------------------------------------------------------------------------------
# Estilos -- réplica del lenguaje visual del visor GEOPERÚ (visor.geoperu.gob.pe):
# navbar blanca con logo+wordmark, paneles tipo tarjeta blanca con sombra suave,
# headers en negrita con color de acento, badges numerados circulares, pills de
# navegación sólidas cuando están activas -- pero con los colores de marca de
# Ausenco (cian #1AAFE2 + negro, tomados de ausenco.com) en vez del azul gob.pe.
# Son 3 cosas SEGURAS (no dependen de clases internas de Streamlit, que cambian
# entre versiones): 1) un header propio (<div> nuestro, control total),
# 2) CSS sobre selectores por ROL/ARIA o data-testid (estables entre versiones),
# 3) recorte del padding-top por defecto.
# ------------------------------------------------------------------------------
_AUSENCO_CIAN = "#1AAFE2"
_AUSENCO_NEGRO = "#101820"
st.markdown(
    f"""
    <style>
    .block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1200px; }}

    /* ---- Navbar estilo GEOPERÚ: blanca, logo + wordmark, borde inferior ---- */
    .app-header {{
        display: flex; align-items: center; gap: 0.9rem;
        padding: 0.9rem 1.3rem; border-radius: 14px; margin-bottom: 1.1rem;
        background: #ffffff; border: 1px solid #E5E9EB;
        box-shadow: 0 2px 10px rgba(16,24,32,0.06);
    }}
    .app-header-icon {{
        font-size: 1.5rem; line-height: 1; width: 2.6rem; height: 2.6rem;
        display: flex; align-items: center; justify-content: center;
        background: {_AUSENCO_NEGRO}; border-radius: 10px; flex-shrink: 0;
    }}
    .app-header-title {{ color: {_AUSENCO_NEGRO}; font-size: 1.35rem; font-weight: 800; margin: 0; letter-spacing: -0.01em; }}
    .app-header-subtitle {{ color: #667085; font-size: 0.85rem; margin-top: 0.1rem; }}

    /* ---- Eyebrow / micro-etiqueta tipo "NAVEGACIÓN" del sidebar GEOPERÚ ---- */
    .eyebrow {{
        color: #98A2B3; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
        text-transform: uppercase; margin: 0.2rem 0 0.4rem 0;
    }}
    .sidebar-heading {{ display: flex; align-items: center; gap: 0.45rem; margin: 0; }}
    .sidebar-heading-text {{ color: {_AUSENCO_NEGRO}; font-weight: 700; font-size: 1rem; }}
    .count-badge {{
        background: {_AUSENCO_CIAN}; color: #fff; font-size: 0.68rem; font-weight: 700;
        border-radius: 999px; min-width: 1.3rem; height: 1.3rem; padding: 0 0.4rem;
        display: inline-flex; align-items: center; justify-content: center;
    }}

    /* ---- Navegación por secciones: pills (igual criterio que filas activas
    de GEOPERÚ: sólidas con el color de acento cuando están seleccionadas) ---- */
    div[role="radiogroup"] {{ gap: 0.4rem; flex-wrap: wrap; row-gap: 0.5rem; }}
    div[role="radiogroup"] label {{
        background: #ffffff; border: 1px solid #E5E9EB; border-radius: 999px;
        padding: 0.45rem 1rem; transition: border-color .15s ease, background .15s ease;
    }}
    div[role="radiogroup"] label:hover {{ border-color: {_AUSENCO_CIAN}; }}
    div[role="radiogroup"] label > div:first-child {{ display: none; }}
    div[role="radiogroup"] label:has(input:checked) {{ background: {_AUSENCO_CIAN}; border-color: {_AUSENCO_CIAN}; }}
    div[role="radiogroup"] label:has(input:checked) p {{ color: #ffffff !important; font-weight: 600; }}

    /* ---- Tarjetas (métricas, contenedores, expanders, dataframes): mismo
    look de "panel flotante" blanco + sombra suave que usa GEOPERÚ para la
    leyenda/notificaciones ---- */
    [data-testid="stMetric"] {{
        background: #ffffff; border: 1px solid #E5E9EB; border-radius: 12px;
        padding: 0.7rem 1rem; box-shadow: 0 2px 8px rgba(16,24,32,0.04);
    }}
    [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; border: 1px solid #E5E9EB; }}
    [data-testid="stVerticalBlockBorderWrapper"] {{ box-shadow: 0 2px 8px rgba(16,24,32,0.04); }}
    [data-testid="stExpander"] {{
        border: 1px solid #E5E9EB !important; border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(16,24,32,0.04);
    }}

    /* ---- Botones primarios: cian sólido, mismo peso que "Entrar al visor" ---- */
    .stButton > button[kind="primary"], .stDownloadButton > button {{
        background: {_AUSENCO_CIAN}; border-color: {_AUSENCO_CIAN}; font-weight: 600;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Estado de sesión (equivalente a las reactives de Shiny)
# ------------------------------------------------------------------------------
st.session_state.setdefault("cache_capas", {})
st.session_state.setdefault("resultado", None)
st.session_state.setdefault("identidad_kml", None)
st.session_state.setdefault("kml_tmp_path", None)
st.session_state.setdefault("ubicacion_tabla", None)

ETIQUETAS = cfg.etiquetas_cruces()

_SUBTITULO_MODO = {
    "real": "Capas base: carpeta local",
    "demo": "Capas base: datos de demostración (local)",
    "nube": "Capas base: descargadas desde almacenamiento en la nube",
}
st.markdown(
    f"""
    <div class="app-header">
        <div class="app-header-icon">🗺️</div>
        <div>
            <p class="app-header-title">{cfg.CONFIG_REPORTE["titulo_reporte"]}</p>
            <p class="app-header-subtitle">{_SUBTITULO_MODO.get(cfg.MODO_DATOS, "")}</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<p class="eyebrow">Navegación</p>', unsafe_allow_html=True)
    _encabezado_sidebar("📂", "1. Área de estudio")
    kml_file = st.file_uploader("Subir archivo KML", type=["kml"])

    if kml_file is not None:
        identidad = (kml_file.name, kml_file.size)
        if identidad != st.session_state.identidad_kml:
            # KML nuevo: cualquier capa cacheada quedó filtrada espacialmente
            # al área de estudio ANTERIOR y ya no sirve para esta.
            st.session_state.identidad_kml = identidad
            invalidar_cache_capas(st.session_state.cache_capas)
            st.session_state.resultado = None

            tmp_dir = tempfile.mkdtemp(prefix="reportes_sig_")
            tmp_path = os.path.join(tmp_dir, kml_file.name)
            with open(tmp_path, "wb") as f:
                f.write(kml_file.getbuffer())
            st.session_state.kml_tmp_path = tmp_path

            # --- Validación rápida de ubicación: solo el cruce de distritos
            # (el más liviano) para mostrar de inmediato dónde cae el área de
            # estudio, sin esperar a "Ejecutar análisis". De paso deja la capa
            # de distritos ya en caché para cuando corra el análisis completo.
            try:
                aoi_previa = cargar_aoi_kml(tmp_path)
                distritos_previa = cargar_capa(st.session_state.cache_capas, "distritos", aoi_previa)
                st.session_state.ubicacion_tabla = cruce_distritos(aoi_previa, distritos_previa)["tabla"]
            except Exception:
                st.session_state.ubicacion_tabla = None

        tabla_ubi = st.session_state.ubicacion_tabla
        if tabla_ubi is not None and len(tabla_ubi):
            st.info(
                "**Área de estudio ubicada en:**  \n"
                f"Distrito(s): {', '.join(tabla_ubi['Distrito'].dropna().astype(str).unique())}  \n"
                f"Provincia(s): {', '.join(tabla_ubi['Provincia'].dropna().astype(str).unique())}  \n"
                f"Departamento(s): {', '.join(tabla_ubi['Departamento'].dropna().astype(str).unique())}"
            )

    st.markdown("---")
    _n_activos = sum(1 for cid in cfg.nombres_cruces() if st.session_state.get(f"chk_{cid}", True))
    _encabezado_sidebar("🧭", "2. Cruces a consultar", badge=_n_activos)
    checks_sel = [
        cid for cid in cfg.nombres_cruces() if st.checkbox(ETIQUETAS[cid], value=True, key=f"chk_{cid}")
    ]

    ejecutar = st.button(
        "▶ Ejecutar análisis", type="primary", use_container_width=True, disabled=(kml_file is None)
    )

# ------------------------------------------------------------------------------
# Ejecuta todos los cruces seleccionados al presionar el botón
# ------------------------------------------------------------------------------
if ejecutar:
    if not checks_sel:
        st.error("Seleccione al menos un cruce para ejecutar.")
    else:
        with st.spinner("Ejecutando cruces espaciales..."):
            try:
                aoi = cargar_aoi_kml(st.session_state.kml_tmp_path)
                salida = ejecutar_cruces(st.session_state.cache_capas, aoi, checks_sel)
                st.session_state.resultado = {
                    "aoi": aoi,
                    "checks": checks_sel,
                    "resultados": salida["resultados"],
                    "distritos_capa": salida["distritos_capa"],
                }
            except Exception as e:
                st.error(f"No se pudo leer el KML: {e}")
                st.session_state.resultado = None

resultado = st.session_state.resultado

# ------------------------------------------------------------------------------
# Resumen del estado de la ejecución (qué se corrió, qué falló)
# ------------------------------------------------------------------------------
if resultado is None:
    st.info('Sube un KML, elige los cruces y presiona "Ejecutar análisis".')
else:
    errores = [k for k, v in resultado["resultados"].items() if isinstance(v, Exception)]
    ok_count = len(resultado["checks"]) - len(errores)

    col_m1, col_m2, col_m3 = st.columns([1, 1, 2])
    col_m1.metric("✅ Cruces con resultado", ok_count)
    col_m2.metric("⚠️ Con errores", len(errores))
    with col_m3:
        excel_bytes = exportar.construir_excel(resultado)
        if excel_bytes:
            st.write("")  # alinea verticalmente el botón con las métricas
            st.download_button(
                "⬇ Descargar todo (Excel)",
                data=excel_bytes,
                file_name="reportes_sig_resultados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if errores:
        st.markdown(f":red[No se pudieron calcular: {', '.join(ETIQUETAS.get(k, k) for k in errores)}]")


def chequear(id_):
    """Valida que un check haya sido seleccionado y calculado sin error --
    equivalente a chequear() en app.R. Devuelve el resultado o None (y ya deja
    el mensaje correspondiente renderizado en la pestaña)."""
    if resultado is None or id_ not in resultado["checks"]:
        st.caption(f'Active "{ETIQUETAS[id_]}" en el panel izquierdo y presione "Ejecutar análisis".')
        return None
    r = resultado["resultados"].get(id_)
    if not ok_resultado(r):
        st.warning(f"No fue posible calcular este cruce: {r}" if isinstance(r, Exception) else "No fue posible calcular este cruce.")
        return None
    return r


# st.tabs() de Streamlit mantiene TODAS las pestañas montadas en el DOM
# (ocultas por CSS, no desmontadas) -- un mapa folium creado dentro de una
# pestaña oculta se inicializa con el contenedor a tamaño 0 y queda con el
# zoom/centro roto (el mismo bug que ya vimos con leaflet en Shiny+Bootstrap).
# Con un selector + if/elif, en cambio, solo se ejecuta (y solo existe en el
# DOM) el bloque de la sección activa -- su mapa nunca se crea oculto.
SECCIONES = [
    "Distritos", "Localidades", "Comunidades", "Vías", "Centros educativos", "Salud",
]
_ICONO_SECCION = {
    "Distritos": "🗺️",
    "Localidades": "🏘️",
    "Comunidades": "🌿",
    "Vías": "🛣️",
    "Centros educativos": "🎓",
    "Salud": "🏥",
}
seccion = st.radio(
    "Sección",
    SECCIONES,
    horizontal=True,
    label_visibility="collapsed",
    format_func=lambda s: f"{_ICONO_SECCION.get(s, '')}  {s}",
)
st.markdown("---")

if seccion == "Distritos":
    r = chequear("distritos")
    if r is not None:
        _tabla(r["tabla"])
        if len(r["sf_sel"]):
            _mostrar_mapa(mapas.mapa_folium_distritos(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"]), "mapa_distritos")
        else:
            st.caption("No hay distritos para mapear.")

elif seccion == "Localidades":
    r = chequear("localidades")
    if r is not None:
        if len(r["tabla"]):
            _tabla(r["tabla"])
            st.markdown("##### Resumen por distrito y categoría")
            _tabla(r["resumen"])
            _mostrar_mapa(mapas.mapa_folium_localidades(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"]), "mapa_localidades")
        else:
            st.caption("No se encontraron localidades en el área de estudio.")

elif seccion == "Comunidades":
    _SUB_COMUNIDADES = ["BDPI", "Centros poblados BDPI", "MIDAGRI", "COFOPRI"]
    _ICONO_SUB_COMUNIDADES = {"BDPI": "🌿", "Centros poblados BDPI": "📍", "MIDAGRI": "🌾", "COFOPRI": "🏞️"}
    sub = st.radio(
        "Comunidad",
        _SUB_COMUNIDADES,
        horizontal=True,
        label_visibility="collapsed",
        format_func=lambda s: f"{_ICONO_SUB_COMUNIDADES.get(s, '')}  {s}",
        key="sub_comunidades",
    )
    st.write("")

    if sub == "BDPI":
        r = chequear("comunidades_bdpi")
        if r is not None:
            if len(r["tabla"]):
                _tabla(r["tabla"])
                _mostrar_mapa(
                    mapas.mapa_folium_comunidad(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"], "Comunidades BDPI"),
                    "mapa_bdpi",
                )
            else:
                st.caption("No se identifican comunidades BDPI en el área de estudio.")

    elif sub == "Centros poblados BDPI":
        r = chequear("cp_bdpi")
        if r is not None:
            if len(r["tabla"]):
                _tabla(r["tabla"])
                _mostrar_mapa(mapas.mapa_folium_cp_bdpi(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"]), "mapa_cpbdpi")
            else:
                st.caption("No se identifican centros poblados indígenas en el área de estudio.")

    elif sub == "MIDAGRI":
        r = chequear("comunidades_midagri")
        if r is not None:
            if len(r["tabla"]):
                _tabla(r["tabla"])
                midagri_excel = resultado["resultados"].get("midagri_excel")
                if midagri_excel is not None and len(midagri_excel):
                    st.markdown("##### Verificación contra padrón Excel")
                    _tabla(midagri_excel)
                _mostrar_mapa(
                    mapas.mapa_folium_comunidad(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"], "Comunidades MIDAGRI"),
                    "mapa_midagri",
                )
            else:
                st.caption("No se identifican comunidades MIDAGRI dentro/cerca del área de estudio.")

    elif sub == "COFOPRI":
        r = chequear("comunidades_cofopri")
        if r is not None:
            if len(r["tabla"]):
                _tabla(r["tabla"])
                _mostrar_mapa(
                    mapas.mapa_folium_comunidad(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"], "Comunidades COFOPRI"),
                    "mapa_cofopri",
                )
            else:
                st.caption("No se identifican comunidades COFOPRI en el área de estudio.")

elif seccion == "Vías":
    r = chequear("vias")
    if r is not None:
        if len(r["tabla"]):
            _tabla(r["tabla"])
            _mostrar_mapa(mapas.mapa_folium_vias(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"]), "mapa_vias")
        else:
            st.caption("No se identifican vías en el área de estudio.")

elif seccion == "Centros educativos":
    r = chequear("educacion")
    if r is not None:
        if len(r["tabla"]):
            _tabla(r["tabla"])
            st.markdown("##### Resumen por distrito y nivel")
            _tabla(r["resumen"])
            _mostrar_mapa(mapas.mapa_folium_educacion(resultado["aoi"], resultado["distritos_capa"], r["sf_sel"]), "mapa_educacion")
        else:
            st.caption("No se identifican centros educativos en el área de estudio.")

elif seccion == "Salud":
    # A diferencia de las demás secciones, esta NO es un cruce con tabla: son
    # capas de referencia visual (WMS, IDEP/GeoPerú) -- el WFS de ese
    # geoserver está bloqueado por Cloudflare, así que no se puede traer como
    # datos por establecimiento, solo mostrarse superpuesta en el mapa.
    st.caption(
        "Hospitales, institutos, centros y puestos de salud (IDEP/GeoPerú) -- "
        "capas de referencia visual, activables/desactivables desde el control "
        "de capas. No hay tabla porque el servidor no permite descargar los "
        "datos por establecimiento (solo la imagen del mapa)."
    )
    if resultado is None:
        st.caption('Sube un KML y presiona "Ejecutar análisis" para centrar el mapa en tu área de estudio.')
    else:
        _mostrar_mapa(mapas.mapa_folium_salud(resultado["aoi"], resultado["distritos_capa"]), "mapa_salud")
