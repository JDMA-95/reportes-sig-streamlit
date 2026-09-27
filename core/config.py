# ==============================================================================
# config.py
# Configuracion central del proyecto: capas base disponibles, catalogo de
# cruces (checks) que la app ofrece, y parametros generales.
# Puerto de R/00_config.R.
# ==============================================================================

import os

# ------------------------------------------------------------------------------
# Modo de operacion
#   "demo" -> usa las capas sinteticas de demo_data/ (no requiere red).
#   "real" -> cada capa se lee de una ruta local (incluye carpetas
#             sincronizadas de OneDrive/SharePoint) -- para correr en ESTE
#             equipo, donde las carpetas de datos existen.
#   "nube" -> cada capa se descarga (y cachea en disco) desde un asset de
#             GitHub Releases -- para el deploy público (Streamlit Community
#             Cloud u otro hosting sin acceso a las carpetas locales).
# Por defecto queda en "real" apuntando a la carpeta de datos de este equipo,
# igual que quedo configurado en la version R. Sobreescribible sin tocar este
# archivo con una variable de entorno:
#   os.environ["REPORTES_MODE"] = "nube"
# ------------------------------------------------------------------------------
MODO_DATOS = os.environ.get("REPORTES_MODE", "real")

RUTA_CARPETA_DATOS = os.environ.get(
    "RUTA_CARPETA_DATOS", "D:/Intento de mejorar/reportes_sig/datos"
)

# Carpeta con las capas "adicionales" (red vial + centros educativos), aparte
# de la carpeta de datos principal.
RUTA_CARPETA_DATOS_ADIC = os.environ.get(
    "RUTA_CARPETA_DATOS_ADIC", "D:/Intento de mejorar/Datos adicionales"
)

# Assets del release de GitHub con las capas reales comprimidas (modo "nube")
# -- ver README > Deploy. Repo público: cualquiera con el link puede
# descargar estos .zip, así que si en algún momento los datos dejan de poder
# ser públicos, este release debe borrarse/pasarse a un storage privado.
_URL_BASE_DATOS_NUBE = os.environ.get(
    "URL_BASE_DATOS_NUBE",
    "https://github.com/JDMA-95/reportes-sig-streamlit/releases/download/datos-v1",
)


def _ruta(env_var, *partes):
    return os.environ.get(env_var, os.path.join(RUTA_CARPETA_DATOS, *partes))


def _ruta_adic(env_var, *partes):
    return os.environ.get(env_var, os.path.join(RUTA_CARPETA_DATOS_ADIC, *partes))


def _url_nube(env_var, nombre_zip):
    return os.environ.get(env_var, f"{_URL_BASE_DATOS_NUBE}/{nombre_zip}.zip")


# ------------------------------------------------------------------------------
# Capas base. Misma estructura/rutas que CONFIG_CAPAS en el proyecto R
# (R/00_config.R) para no desincronizar ambas versiones.
# ------------------------------------------------------------------------------
CONFIG_CAPAS = {
    "distritos": {
        "tipo": "poligono",
        "fuente": "local",
        "ruta": _ruta(
            "RUTA_LOCAL_DISTRITOS",
            "Distrital INEI 2023 geogpsperu SuyoPomalia",
            "Distrital INEI 2023 geogpsperu SuyoPomalia.shp",
        ),
        "url": _url_nube("URL_DISTRITOS", "distritos"),
        "cita": "INEI, 2025 — delimitación territorial (Distritos)",
    },
    "localidades": {
        "tipo": "punto",
        "fuente": "local",
        "ruta": _ruta(
            "RUTA_LOCAL_LOCALIDADES",
            "CCPP_GEOPERU_sd",
            "CCPP_GEOPERU_2017 2-sin duplicado",
            "CCPP_PERU_2017_SOCIO.shp",
        ),
        "url": _url_nube("URL_LOCALIDADES", "localidades"),
        # Ver nota de rendimiento en el README R: esta es la capa mas pesada
        # (censo INEI 2017, cientos de columnas). "columnas" (opcional) limita
        # que columnas se leen ademas de la geometria -- ver io_capas.leer_shp_local.
        "columnas": None,
        "cita": "INEI, 2017 — Censos Nacionales 2017: XII Población, VII Vivienda y III Comunidades Indígenas",
    },
    "comunidades_bdpi": {
        "tipo": "poligono",
        "fuente": "local",
        "ruta": _ruta("RUTA_LOCAL_BDPI_COMUNIDAD", "Shapefile_PPIIOO_Comunidad", "shapeComunidad.shp"),
        "url": _url_nube("URL_COMUNIDADES_BDPI", "comunidades_bdpi"),
        "cita": "MINCUL, 2025 — Base de Datos de Pueblos Indígenas u Originarios (BDPI)",
    },
    "cp_bdpi": {
        "tipo": "punto_o_poligono",
        "fuente": "local",
        "ruta": _ruta(
            "RUTA_LOCAL_BDPI_CP", "Shapefile_PPIIOO_CentroPobladoIndigena", "shapeCentroPobladoIndigena.shp"
        ),
        "url": _url_nube("URL_CP_BDPI", "cp_bdpi"),
        "cita": "MINCUL, 2025 — Base de Datos de Pueblos Indígenas u Originarios (BDPI), Centros Poblados",
    },
    "comunidades_midagri": {
        "tipo": "poligono",
        "fuente": "local",
        "ruta": _ruta(
            "RUTA_LOCAL_MIDAGRI",
            "COMUNIDADES CAMPESINAS GEORURAL MIDAGRI GEOGPSPERU SUYOPOMALIA (1)",
            "COMUNIDADES CAMPESINAS GEORURAL MIDAGRI GEOGPSPERU.shp",
        ),
        "url": _url_nube("URL_COMUNIDADES_MIDAGRI", "comunidades_midagri"),
        "cita": "MIDAGRI, GEORURAL, 2025",
    },
    "comunidades_cofopri": {
        "tipo": "poligono",
        "fuente": "local",
        "ruta": _ruta(
            "RUTA_LOCAL_COFOPRI",
            "COMUNIDADES CAMPESINAS GEOLLAQTA COFOPRI GEOGPSPERU SUYOPOMALIA (1)",
            "COMUNIDADES CAMPESINAS GEOLLAQTA COFOPRI GEOGPSPERU.shp",
        ),
        "url": _url_nube("URL_COMUNIDADES_COFOPRI", "comunidades_cofopri"),
        "cita": "COFOPRI, 2025",
    },
    "cc_excel": {
        "tipo": "tabla",
        "fuente": "local",
        "ruta": _ruta("RUTA_LOCAL_CC_EXCEL", "Consolidado de CC.xlsx"),
        "url": _url_nube("URL_CC_EXCEL", "cc_excel"),
        "cita": "Padrón interno de comunidades campesinas (Excel)",
    },
    # --- Capas adicionales (carpeta "Datos adicionales") -----------------------
    "vias_nacional": {
        "tipo": "linea",
        "fuente": "local",
        # Se usa la versión dic. 2020 (no la de 2024 PROVÍAS, también en la
        # carpeta): esta trae superficie/estado/jerarquía como TEXTO legible
        # ("Pavimentado"/"Bueno"/"Red Nacional"), mismo esquema que la capa
        # departamental. La de 2024 solo tiene esos campos como códigos.
        "ruta": _ruta_adic("RUTA_LOCAL_VIAS_NACIONAL", "Red vial nacional", "red_vial_nacional_dic20.shp"),
        "url": _url_nube("URL_VIAS_NACIONAL", "vias_nacional"),
        "cita": "MTC, dic. 2020 — Red Vial Nacional",
    },
    "vias_departamental": {
        "tipo": "linea",
        "fuente": "local",
        "ruta": _ruta_adic(
            "RUTA_LOCAL_VIAS_DEPARTAMENTAL", "Red vial departamental", "red_vial_departamental_dic20.shp"
        ),
        "url": _url_nube("URL_VIAS_DEPARTAMENTAL", "vias_departamental"),
        "cita": "MTC, dic. 2020 — Red Vial Departamental",
    },
    "vias_vecinal": {
        "tipo": "linea",
        "fuente": "local",
        "ruta": _ruta_adic("RUTA_LOCAL_VIAS_VECINAL", "Red vial vecinal", "RVV_Eje.shp"),
        "url": _url_nube("URL_VIAS_VECINAL", "vias_vecinal"),
        "cita": "MTC, DS 2012 — Red Vial Vecinal",
    },
    "educacion": {
        "tipo": "punto",
        "fuente": "local",
        "ruta": _ruta_adic(
            "RUTA_LOCAL_EDUCACION",
            "peru_conect_educacion_",
            "peru_conect_educacion_",
            "peru_conect_educacion_.shp",
        ),
        "url": _url_nube("URL_EDUCACION", "educacion"),
        "cita": "MINEDU — Padrón de instituciones educativas (georreferenciado)",
    },
}

# ------------------------------------------------------------------------------------------------------------------------
# Catalogo de cruces (checks) que se ofrecen en la app.
# ------------------------------------------------------------------------------
CONFIG_CRUCES = [
    {"id": "distritos", "etiqueta": "Distritos que intersectan el área de estudio", "capas": ["distritos"]},
    {
        "id": "localidades",
        "etiqueta": "Localidades (centros poblados y población dispersa)",
        "capas": ["localidades", "distritos"],
    },
    {
        "id": "comunidades_bdpi",
        "etiqueta": "Comunidades indígenas u originarias (BDPI - MINCUL)",
        "capas": ["comunidades_bdpi"],
    },
    {
        "id": "cp_bdpi",
        "etiqueta": "Centros poblados indígenas (BDPI - MINCUL)",
        "capas": ["cp_bdpi", "distritos"],
    },
    {
        "id": "comunidades_midagri",
        "etiqueta": "Comunidades campesinas (MIDAGRI) + verificación con padrón Excel",
        "capas": ["comunidades_midagri", "cc_excel", "distritos"],
    },
    {
        "id": "comunidades_cofopri",
        "etiqueta": "Comunidades campesinas (COFOPRI)",
        "capas": ["comunidades_cofopri"],
    },
    {
        "id": "vias",
        "etiqueta": "Vías (red vial nacional, departamental y vecinal)",
        "capas": ["vias_nacional", "vias_departamental", "vias_vecinal", "distritos"],
    },
    {
        "id": "educacion",
        "etiqueta": "Centros educativos (instituciones educativas)",
        "capas": ["educacion", "distritos"],
    },
]

CONFIG_REPORTE = {
    "titulo_reporte": "Revisión general de información social",
    "autor_reporte": "Generado automáticamente vía Streamlit App",
    "tolerancia_bdpi_m": 0,
    "distancias_cascada_midagri": [150, 300],
}


def nombres_cruces():
    return [c["id"] for c in CONFIG_CRUCES]


def etiquetas_cruces():
    return {c["id"]: c["etiqueta"] for c in CONFIG_CRUCES}
