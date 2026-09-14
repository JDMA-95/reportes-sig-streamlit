# ==============================================================================
# io_capas.py
# Capa de acceso a datos. Puerto de R/01_conexion_datos.R. Expone:
#   cargar_capa(cache, nombre, aoi=None)  -> GeoDataFrame/DataFrame de la capa
#   cargar_aoi_kml(ruta_kml)              -> GeoDataFrame del área de estudio
#
# `cache` es un dict explícito (no un global del módulo): en Streamlit un solo
# proceso Python atiende a TODOS los usuarios a la vez, así que el caché tiene
# que vivir en st.session_state (por sesión/navegador) y no en una variable de
# módulo -- si no, el filtro espacial de un usuario (ver .bbox_para_capa)
# quedaría "pegado" para el área de estudio de otro usuario distinto.
# ==============================================================================

import os

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

from . import config as cfg


def cargar_aoi_kml(ruta_kml):
    aoi = gpd.read_file(ruta_kml)
    if len(aoi) == 0:
        raise ValueError("El KML no contiene geometrías legibles.")
    aoi["geometry"] = aoi.geometry.make_valid()
    aoi["geometry"] = shapely.force_2d(aoi.geometry)
    return aoi


def _bbox_para_capa(aoi, ruta_capa, margen_grados=0.05):
    """Bbox (en el CRS de la capa) con margen de seguridad a partir del AOI.

    Usado como `bbox=` de gpd.read_file() para que GDAL descarte durante la
    LECTURA las features que no pueden intersectar el AOI, en vez de traer la
    capa completa (potencialmente todo el Perú) a memoria y filtrar despues.
    Margen de 0.05grados (~5 km en el ecuador), generoso frente a las
    distancias de cascada que usa cruce_comunidad() (hasta 300 m).
    """
    if aoi is None:
        return None
    try:
        info = pyogrio.read_info(ruta_capa)
        crs_capa = info.get("crs")
    except Exception:
        return None
    if crs_capa is None:
        return None
    try:
        aoi_ll = aoi.to_crs(4326)
        minx, miny, maxx, maxy = aoi_ll.total_bounds
        rect = gpd.GeoSeries(
            [shapely.box(minx - margen_grados, miny - margen_grados, maxx + margen_grados, maxy + margen_grados)],
            crs=4326,
        )
        rect_t = rect.to_crs(crs_capa)
        return tuple(rect_t.total_bounds)
    except Exception:
        return None


def leer_shp_local(ruta, columnas=None, bbox=None):
    """Lee un shapefile local (o en una carpeta sincronizada de OneDrive/SharePoint).

    `columnas`: opcional, lista de columnas a leer (ademas de la geometria) --
    util para capas MUY pesadas (censo de localidades/CCPP). `bbox`: opcional,
    filtro espacial (ver _bbox_para_capa) en el CRS de la capa.
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"No se encontró el shapefile en la ruta configurada: {ruta}\n"
            "Ajuste CONFIG_CAPAS en core/config.py (o la variable de entorno "
            "correspondiente) con la ruta real (carpeta local o sincronizada "
            "de OneDrive/SharePoint)."
        )
    try:
        gdf = gpd.read_file(ruta, columns=columnas, bbox=bbox) if columnas else gpd.read_file(ruta, bbox=bbox)
    except UnicodeDecodeError:
        # Algunas capas reales declaran UTF-8 en el .cpg pero el .dbf quedó
        # corrupto al escribirse sin locale UTF-8 activo (ver nota en
        # README/00_config.R del proyecto R) -- pyogrio es estricto y falla
        # duro; GDAL/R lo tolera. latin1 nunca lanza (mapea 1 a 1 cualquier
        # byte), así que garantiza poder leer la capa aunque algunos
        # caracteres con tilde/ñ salgan mal en esas filas puntuales.
        kwargs = dict(bbox=bbox, encoding="latin1")
        if columnas:
            kwargs["columns"] = columnas
        gdf = gpd.read_file(ruta, **kwargs)
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf["geometry"] = shapely.force_2d(gdf.geometry)
    return gdf


def _raiz_demo():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cargar_capa_demo(nombre, capa_cfg):
    raiz = _raiz_demo()
    if capa_cfg["tipo"] == "tabla":
        ruta = os.path.join(raiz, "demo_data", "excel", f"{nombre}.xlsx")
        if not os.path.exists(ruta):
            raise FileNotFoundError(f"No se encontró el Excel demo: {ruta}")
        return pd.read_excel(ruta)
    ruta = os.path.join(raiz, "demo_data", "capas", nombre, f"{nombre}.shp")
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No se encontró el shapefile demo: {ruta}")
    gdf = gpd.read_file(ruta)
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf["geometry"] = shapely.force_2d(gdf.geometry)
    return gdf


def cargar_capa(cache, nombre, aoi=None):
    """Carga una capa base, opcionalmente acotada al área de estudio.

    `cache`: dict (normalmente st.session_state["cache_capas"]) donde queda
    memorizada la capa ya cargada para esta sesión.
    `aoi`: opcional, GeoDataFrame del área de estudio -- si se pasa (y la
    fuente es un shapefile local), se usa como filtro espacial al leer.
    """
    if nombre in cache:
        return cache[nombre]

    capa_cfg = cfg.CONFIG_CAPAS.get(nombre)
    if capa_cfg is None:
        raise ValueError(f"Capa no definida en CONFIG_CAPAS: {nombre}")

    if cfg.MODO_DATOS == "demo":
        valor = _cargar_capa_demo(nombre, capa_cfg)
    elif capa_cfg["fuente"] == "local":
        if capa_cfg["tipo"] == "tabla":
            valor = pd.read_excel(capa_cfg["ruta"])
        else:
            bbox = _bbox_para_capa(aoi, capa_cfg["ruta"]) if aoi is not None else None
            valor = leer_shp_local(capa_cfg["ruta"], columnas=capa_cfg.get("columnas"), bbox=bbox)
    else:
        raise ValueError(f"Fuente desconocida para la capa '{nombre}': {capa_cfg['fuente']}")

    cache[nombre] = valor
    return valor


def invalidar_cache_capas(cache):
    """Fuerza recarga -- p.ej. cuando el usuario sube un KML nuevo cuyo área de
    estudio ya no calza con lo que haya quedado cacheado de un AOI anterior
    filtrado espacialmente."""
    cache.clear()
