# ==============================================================================
# procesamiento.py
# Logica de cruce espacial. Puerto de R/02_procesamiento.R. Cada cruce (check)
# tiene una funcion que recibe el AOI (área de estudio subida por el usuario)
# + la(s) capa(s) necesaria(s), y devuelve un dict con la tabla lista para
# mostrar/reportar y, cuando aplica, el GeoDataFrame seleccionado para el mapa.
#
# Nota de dependencias: el .Rmd/app R original usa 'janitor' y 'fuzzyjoin'.
# Aqui el equivalente es unidecode (limpiar_nombres/norm_str) y
# rapidfuzz.distance.Levenshtein (fuzzy_match_por_grupo) -- mismo criterio que
# ya se uso en la version R (adist() de base R) para no depender de paquetes
# de matching difuso mas pesados.
# ==============================================================================

import re

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz.distance import Levenshtein
from shapely.geometry import box
from shapely.ops import linemerge, polygonize, unary_union
from unidecode import unidecode as _unidecode

from . import config as cfg
from .io_capas import cargar_capa

# ------------------------------------------------------------------------------
# Helpers genéricos (portados del .Rmd / R/02_procesamiento.R)
# ------------------------------------------------------------------------------


def limpiar_nombres(df):
    def _clean(nm):
        nm = _unidecode(str(nm)).lower()
        nm = re.sub(r"[^a-z0-9]+", "_", nm)
        nm = re.sub(r"^_+|_+$", "", nm)
        return nm

    limpios = [_clean(c) for c in df.columns]
    vistos, salida = {}, []
    for n in limpios:
        if n in vistos:
            vistos[n] += 1
            salida.append(f"{n}_{vistos[n]}")
        else:
            vistos[n] = 0
            salida.append(n)
    df = df.copy()
    df.columns = salida
    return df


def get_col(nms, cands):
    cands_low = {c.lower() for c in cands}
    for n in nms:
        if n.lower() in cands_low:
            return n
    return None


def to_num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", ".", "-."):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def to_num_series(s):
    return s.apply(to_num) if s is not None else s


def norm_str(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    x = _unidecode(str(x)).lower()
    return re.sub(r"\s+", " ", x.strip())


def std_cat(x):
    x1 = norm_str(x)
    if "dispers" in x1:
        return "Población dispersa"
    if re.search(r"centro|c\.?p\.?|\bcp\b", x1):
        return "Centro poblado"
    if "caser" in x1:
        return "Caserío"
    if "anex" in x1:
        return "Anexo"
    return x1.title() if x1 else x1


def aoi_polygon(gdf):
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.make_valid()
    tipos = set(gdf.geometry.geom_type.unique())
    if not any("Polygon" in t for t in tipos):
        lineas = [g for g in gdf.geometry if g is not None and "LineString" in g.geom_type]
        if lineas:
            merged = linemerge(unary_union(lineas))
            piezas = [merged] if merged.geom_type == "LineString" else list(merged.geoms)
            polys = list(polygonize(piezas))
            if polys:
                return gpd.GeoDataFrame(geometry=polys, crs=gdf.crs)
    return gdf


def align_crs(x, target):
    return x.to_crs(target.crs) if x.crs != target.crs else x


def to_utm_epsg(g_ll):
    try:
        c = g_ll.geometry.union_all().centroid
        lon, lat = c.x, c.y
        zona = int((lon + 180) // 6) + 1
        if not np.isfinite(zona):
            return 3857
        return (32700 + zona) if lat < 0 else (32600 + zona)
    except Exception:
        return 3857


def preparar_utm(aoi_poly, capa):
    """Proyecta AOI + capa a la UTM local (en metros), saneando geometría."""
    aoi_ll = aoi_poly.to_crs(4326)
    capa_ll = capa.copy()
    capa_ll["geometry"] = capa_ll.geometry.make_valid()
    capa_ll = capa_ll.to_crs(4326)
    epsg = to_utm_epsg(aoi_ll)
    aoi_m = aoi_ll.to_crs(epsg)
    aoi_m["geometry"] = aoi_m.buffer(0)
    capa_m = capa_ll.to_crs(epsg)
    capa_m["geometry"] = capa_m.buffer(0)
    return aoi_m, capa_m, epsg


def seleccionar_por_metodo(capa_m, aoi_m, metodo="interseccion", tol_m=0, distancias=(150, 300)):
    """Selección espacial: "interseccion" (con tolerancia opcional en metros)
    o "cascada" (contención > intersección > distancias de respaldo -- la
    lógica que usa MIDAGRI)."""
    aoi_u = aoi_m.geometry.union_all()
    if metodo == "cascada":
        sel = capa_m.geometry.within(aoi_u)
        if not sel.any():
            sel = capa_m.geometry.intersects(aoi_u)
        for d in distancias:
            if sel.any():
                break
            sel = capa_m.geometry.distance(aoi_u) <= d
        return sel
    aoi_buf = aoi_u.buffer(tol_m) if tol_m > 0 else aoi_u
    return capa_m.geometry.intersects(aoi_buf)


# ------------------------------------------------------------------------------
# 1) Distritos que intersectan el AOI
# ------------------------------------------------------------------------------
def cruce_distritos(aoi, distritos):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    dist_v = distritos.copy()
    dist_v["geometry"] = dist_v.geometry.make_valid()
    aoi_u = aoi_p.geometry.union_all()
    dist_int = dist_v[dist_v.geometry.intersects(aoi_u)].copy().reset_index(drop=True)

    df = limpiar_nombres(dist_int.drop(columns="geometry"))
    nm = list(df.columns)
    c_dis = get_col(nm, ["distrito", "dist", "dist_name"])
    c_pro = get_col(nm, ["provincia", "prov", "prov_name"])
    c_dep = get_col(nm, ["departamento", "depto", "dpto", "departamen"])

    tabla = pd.DataFrame(
        {
            "Distrito": df[c_dis] if c_dis else pd.Series([pd.NA] * len(df)),
            "Provincia": df[c_pro] if c_pro else pd.Series([pd.NA] * len(df)),
            "Departamento": df[c_dep] if c_dep else pd.Series([pd.NA] * len(df)),
        }
    ).drop_duplicates().reset_index(drop=True)

    # Columnas estandarizadas también sobre el GeoDataFrame (no solo en
    # `tabla`, que puede tener menos filas por el drop_duplicates) -- así los
    # mapas pueden usar directamente distrito/provincia/departamento.
    dist_int["distrito"] = df[c_dis].values if c_dis else pd.NA
    dist_int["provincia"] = df[c_pro].values if c_pro else pd.NA
    dist_int["departamento"] = df[c_dep].values if c_dep else pd.NA

    return {"tabla": tabla, "sf_sel": dist_int}


# ------------------------------------------------------------------------------
# 2) Localidades (Centro poblado / Población dispersa) en el AOI
# ------------------------------------------------------------------------------
def cruce_localidades(aoi, localidades):
    aoi_p = align_crs(aoi_polygon(aoi), localidades)
    aoi_u = aoi_p.geometry.union_all()

    loc0 = localidades[~localidades.geometry.is_empty & localidades.geometry.notna()].copy()
    loc0["geometry"] = loc0.geometry.make_valid()
    loc_hit = loc0[loc0.geometry.intersects(aoi_u)].copy().reset_index(drop=True)
    if not len(loc_hit):
        vacio = gpd.GeoDataFrame(geometry=[], crs=localidades.crs)
        return {"tabla": pd.DataFrame(), "resumen": pd.DataFrame(), "sf_sel": vacio}

    df = limpiar_nombres(loc_hit.drop(columns="geometry"))
    nm = list(df.columns)
    c_nom = get_col(nm, ["nom_ccpp", "nomb_ccpp", "nombre_ccpp", "ccpp", "nombre"])
    c_cat = get_col(nm, ["categoria", "categoria_", "tipo_loc", "tipo", "clase"])
    c_hog = get_col(nm, ["num_hogare", "num_hogares", "n_hogares", "hogares", "hogar", "tot_hogares"])
    c_dis = get_col(nm, ["nom_dist", "distrito", "nomb_dist", "nom_distrito"])
    c_pro = get_col(nm, ["nom_prov", "provincia", "nomb_prov", "nom_provincia"])
    c_dep = get_col(nm, ["nom_dpto", "departamento", "dpto", "nom_depa", "depart", "departamen"])

    tabla_completa = pd.DataFrame(
        {
            "nom_ccpp": df[c_nom] if c_nom else pd.Series([pd.NA] * len(df)),
            "categoria": df[c_cat].apply(std_cat) if c_cat else pd.Series([pd.NA] * len(df)),
            "num_hogares": to_num_series(df[c_hog]) if c_hog else pd.Series([np.nan] * len(df)),
            "distrito": df[c_dis] if c_dis else pd.Series([pd.NA] * len(df)),
            "provincia": df[c_pro] if c_pro else pd.Series([pd.NA] * len(df)),
            "departamento": df[c_dep] if c_dep else pd.Series([pd.NA] * len(df)),
        }
    )

    keep = tabla_completa["categoria"].isin(["Centro poblado", "Población dispersa"])
    tabla = (
        tabla_completa[keep]
        .drop_duplicates()
        .sort_values(["provincia", "distrito", "categoria", "nom_ccpp"])
        .reset_index(drop=True)
    )

    # Todas las columnas de tabla_completa, también sobre el GeoDataFrame (no
    # solo nom_ccpp/categoria) -- el mapa interactivo (popup de folium) usa
    # num_hogares/distrito directamente desde sf_sel, no desde `tabla`.
    for col in ["nom_ccpp", "categoria", "num_hogares", "distrito", "provincia", "departamento"]:
        loc_hit[col] = tabla_completa[col].values
    sf_sel = loc_hit[keep.values].reset_index(drop=True)

    resumen = (
        tabla.groupby(["departamento", "provincia", "distrito", "categoria"], dropna=False)
        .agg(Localidades=("nom_ccpp", "size"), Hogares=("num_hogares", "sum"))
        .reset_index()
        .rename(
            columns={
                "departamento": "Departamento",
                "provincia": "Provincia",
                "distrito": "Distrito",
                "categoria": "Categoría",
            }
        )
    )

    return {"tabla": tabla, "resumen": resumen, "sf_sel": sf_sel}


# ------------------------------------------------------------------------------
# 3) Comunidades (BDPI / MIDAGRI / COFOPRI) — función genérica
# ------------------------------------------------------------------------------
def cruce_comunidad(aoi, capa, fuente, metodo="interseccion", tol_m=0, distancias_cascada=(150, 300)):
    capa0 = capa[~capa.geometry.is_empty & capa.geometry.notna()].copy()
    capa0["geometry"] = capa0.geometry.make_valid()
    capa0["geometry"] = capa0.geometry.force_2d() if hasattr(capa0.geometry, "force_2d") else capa0.geometry

    aoi_m, capa_m, _ = preparar_utm(aoi_polygon(aoi), capa0)
    sel = seleccionar_por_metodo(capa_m, aoi_m, metodo, tol_m, distancias_cascada)
    hit = capa_m[sel].copy().reset_index(drop=True)
    # Quedarse solo con partes poligonales si algo quedó como colección mixta.
    hit["geometry"] = hit.geometry.apply(
        lambda g: g if g is None or "Polygon" in g.geom_type else g
    )

    df = limpiar_nombres(hit.drop(columns="geometry"))
    nm = list(df.columns)
    c_nom = get_col(nm, ["nom_comuni", "nom_comun", "nom_comunidad", "nombre", "nomb_comu", "nombre_cc", "nomcc", "nom_cc", "nomcom"])
    c_pob = get_col(nm, ["poblacion", "pob_total", "pobl_tot", "poblaci", "pob"])
    c_hog = get_col(nm, ["hogares", "n_hogares", "num_hogares", "num_hogare", "tot_hogares", "hogar"])
    c_dis = get_col(nm, ["nom_dist", "distrito", "nom_distrito", "nomb_dist", "nodist"])
    c_pro = get_col(nm, ["nom_prov", "provincia", "nom_provincia", "nomb_prov", "noprov"])
    c_dep = get_col(nm, ["nom_dpto", "departamento", "nom_departamento", "dpto", "depa", "departamen", "nodpto", "nomdpto"])

    n_hit = len(hit)
    hit["cc_nombre"] = df[c_nom].values if c_nom else pd.array([pd.NA] * n_hit)
    hit["cc_dpto"] = df[c_dep].values if c_dep else pd.array([pd.NA] * n_hit)
    hit["cc_prov"] = df[c_pro].values if c_pro else pd.array([pd.NA] * n_hit)
    hit["cc_dist"] = df[c_dis].values if c_dis else pd.array([pd.NA] * n_hit)
    hit["cc_fuente"] = fuente

    tabla = pd.DataFrame(
        {
            "nombre": hit["cc_nombre"].values,
            "poblacion": to_num_series(df[c_pob]).values if c_pob else np.full(n_hit, np.nan),
            "hogares": to_num_series(df[c_hog]).values if c_hog else np.full(n_hit, np.nan),
            "distrito": hit["cc_dist"].values,
            "provincia": hit["cc_prov"].values,
            "departamento": hit["cc_dpto"].values,
        }
    ).drop_duplicates().sort_values(["provincia", "distrito", "nombre"]).reset_index(drop=True)

    return {"tabla": tabla, "sf_sel": hit}


# ------------------------------------------------------------------------------
# 4) Centros poblados indígenas BDPI (puntos)
# ------------------------------------------------------------------------------
def cruce_cp_bdpi(aoi, cp_bdpi):
    aoi_p = align_crs(aoi_polygon(aoi), cp_bdpi)
    aoi_u = aoi_p.geometry.union_all()

    cp0 = cp_bdpi[~cp_bdpi.geometry.is_empty & cp_bdpi.geometry.notna()].copy()
    cp0["geometry"] = cp0.geometry.make_valid()
    tipos = set(cp0.geometry.geom_type.unique())
    cp_pts = cp0.copy()
    if "MultiPoint" in tipos:
        cp_pts = cp_pts.explode(index_parts=False).reset_index(drop=True)
    if tipos & {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        cp_pts["geometry"] = cp_pts.geometry.representative_point()

    cp_hit = cp_pts[cp_pts.geometry.intersects(aoi_u)].copy().reset_index(drop=True)
    if not len(cp_hit):
        vacio = gpd.GeoDataFrame(geometry=[], crs=cp_bdpi.crs)
        return {"tabla": pd.DataFrame(), "sf_sel": vacio}

    df = limpiar_nombres(cp_hit.drop(columns="geometry"))
    c_nom = get_col(list(df.columns), ["nombcp", "nom_ccpp", "nomb_ccpp", "nombre_ccpp", "ccpp", "nombre", "localidad", "nomcom"])
    if c_nom:
        nom_vec = df[c_nom].astype(str).where(df[c_nom].notna() & (df[c_nom].astype(str).str.strip() != ""), None)
        nom_vec = [v if v else f"BDPI_{i+1}" for i, v in enumerate(nom_vec)]
    else:
        nom_vec = [f"BDPI_{i+1}" for i in range(len(df))]

    cp_hit["nom_label"] = nom_vec
    tabla = pd.DataFrame({"Centro poblado indígena": nom_vec}).drop_duplicates().reset_index(drop=True)
    return {"tabla": tabla, "sf_sel": cp_hit}


# ------------------------------------------------------------------------------
# 4b) Vías (red vial nacional / departamental / vecinal) — función genérica,
#     una llamada por jerarquía (igual patrón que cruce_comunidad()).
# ------------------------------------------------------------------------------
def cruce_vias(aoi, capa, jerarquia):
    aoi_p = align_crs(aoi_polygon(aoi), capa)
    aoi_u = aoi_p.geometry.union_all()

    vias0 = capa[~capa.geometry.is_empty & capa.geometry.notna()].copy()
    vias0["geometry"] = vias0.geometry.make_valid()
    hit = vias0[vias0.geometry.intersects(aoi_u)].copy().reset_index(drop=True)
    if not len(hit):
        vacio = gpd.GeoDataFrame(geometry=[], crs=capa.crs)
        return {"tabla": pd.DataFrame(), "sf_sel": vacio}

    df = limpiar_nombres(hit.drop(columns="geometry"))
    nm = list(df.columns)
    c_cod = get_col(nm, ["codruta", "ccodruta", "cod_ds12", "cod_ds11", "cod_ruta", "codigo"])
    c_nom = get_col(nm, ["trayectori", "tray_ds12", "tray_ds11", "cnomruta", "nombre", "trayecto"])
    # Las capas del MTC traen el dato dos veces: un campo con el CÓDIGO
    # numérico (ej. "SUPERFIC") y otro con la ETIQUETA de texto ("SUPERFIC_L").
    # Solo se buscan las versiones de texto (get_col devuelve la primera
    # columna que matchea por ORDEN, no por prioridad de la lista).
    c_sup = get_col(nm, ["superfic_l", "superficie_l", "sup_l", "tipo_super"])
    c_est = get_col(nm, ["estado_l", "est_l", "estado_via"])
    c_lon = get_col(nm, ["longitud", "long_km", "dlongitud", "shape_leng"])
    c_dep = get_col(nm, ["departamen", "cdepartame", "departamento", "dep"])

    n_hit = len(hit)
    hit["via_codigo"] = df[c_cod].values if c_cod else pd.array([pd.NA] * n_hit)
    hit["via_nombre"] = df[c_nom].values if c_nom else pd.array([pd.NA] * n_hit)
    hit["via_jerarquia"] = jerarquia

    tabla = pd.DataFrame(
        {
            "codigo": hit["via_codigo"].values,
            "nombre_tramo": hit["via_nombre"].values,
            "jerarquia": jerarquia,
            "superficie": df[c_sup].values if c_sup else pd.array([pd.NA] * n_hit),
            "estado": df[c_est].values if c_est else pd.array([pd.NA] * n_hit),
            "longitud_km": to_num_series(df[c_lon]).values if c_lon else np.full(n_hit, np.nan),
            "departamento": df[c_dep].values if c_dep else pd.array([pd.NA] * n_hit),
        }
    ).drop_duplicates().sort_values(["jerarquia", "codigo"]).reset_index(drop=True)

    return {"tabla": tabla, "sf_sel": hit}


# ------------------------------------------------------------------------------
# 4c) Centros educativos (instituciones educativas, puntos)
# ------------------------------------------------------------------------------
def _nivel_educacion(x):
    x1 = norm_str(x)
    if not x1:
        return "Sin especificar"
    if "inicial" in x1 or "inical" in x1 or "cuna" in x1 or "jardin" in x1:
        return "Inicial"
    if "primaria" in x1:
        return "Primaria"
    if "secundaria" in x1:
        return "Secundaria"
    if "superior" in x1 or "tecnic" in x1 or "tecnico" in x1 or "pedagog" in x1 or "tecnolog" in x1:
        return "Superior / Técnica"
    if "especial" in x1:
        return "Básica Especial"
    if "alternativa" in x1 or "adultos" in x1 or "ocupacional" in x1 or "artesanal" in x1:
        return "Básica Alternativa / Otros"
    return "Otros"


def cruce_educacion(aoi, educacion):
    aoi_p = align_crs(aoi_polygon(aoi), educacion)
    aoi_u = aoi_p.geometry.union_all()

    edu0 = educacion[~educacion.geometry.is_empty & educacion.geometry.notna()].copy()
    edu0["geometry"] = edu0.geometry.make_valid()
    tipos = set(edu0.geometry.geom_type.unique())
    if "MultiPoint" in tipos:
        edu0 = edu0.explode(index_parts=False).reset_index(drop=True)
    if tipos & {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        edu0["geometry"] = edu0.geometry.representative_point()

    hit = edu0[edu0.geometry.intersects(aoi_u)].copy().reset_index(drop=True)
    if not len(hit):
        vacio = gpd.GeoDataFrame(geometry=[], crs=educacion.crs)
        return {"tabla": pd.DataFrame(), "resumen": pd.DataFrame(), "sf_sel": vacio}

    df = limpiar_nombres(hit.drop(columns="geometry"))
    nm = list(df.columns)
    c_nom = get_col(nm, ["cenedu", "nombre_ie", "nombre", "ie", "nom_ie", "cen_edu"])
    c_niv = get_col(nm, ["nivmod_val", "nivmod", "nivel_modalidad", "nivel", "niv_mod"])
    c_dis = get_col(nm, ["nom_dist", "distrito", "nomb_dist"])
    c_pro = get_col(nm, ["nom_prov", "provincia", "nomb_prov"])
    c_dep = get_col(nm, ["nom_dpto", "departamento", "dpto", "departamen"])

    n_hit = len(hit)
    nombres = (
        df[c_nom].astype(str).str.strip().replace({"": None, "nan": None, "None": None})
        if c_nom
        else pd.Series([None] * n_hit)
    )
    nombres = [v if v else f"IE {i + 1}" for i, v in enumerate(nombres)]
    nivel_raw = df[c_niv] if c_niv else pd.Series([pd.NA] * n_hit)
    nivel_grupo = [_nivel_educacion(v) for v in nivel_raw]

    hit["ie_nombre"] = nombres
    hit["ie_nivel_grupo"] = nivel_grupo

    tabla = pd.DataFrame(
        {
            "nombre": nombres,
            "nivel_modalidad": nivel_raw.values if hasattr(nivel_raw, "values") else nivel_raw,
            "nivel_grupo": nivel_grupo,
            "distrito": df[c_dis].values if c_dis else pd.array([pd.NA] * n_hit),
            "provincia": df[c_pro].values if c_pro else pd.array([pd.NA] * n_hit),
            "departamento": df[c_dep].values if c_dep else pd.array([pd.NA] * n_hit),
        }
    ).drop_duplicates().sort_values(["distrito", "nivel_grupo", "nombre"]).reset_index(drop=True)

    resumen = (
        tabla.groupby(["distrito", "nivel_grupo"], dropna=False)
        .agg(Instituciones=("nombre", "size"))
        .reset_index()
        .rename(columns={"distrito": "Distrito", "nivel_grupo": "Nivel"})
        .sort_values(["Distrito", "Nivel"])
        .reset_index(drop=True)
    )

    return {"tabla": tabla, "resumen": resumen, "sf_sel": hit}


# ------------------------------------------------------------------------------
# 5) Localidades dentro de Comunidades Campesinas (BDPI+MIDAGRI+COFOPRI) +
#    tabla de posibles duplicidades (misma localidad, más de una fuente)
# ------------------------------------------------------------------------------
def cruce_localidades_en_comunidades(loc_cruce, lista_comunidades_sel):
    loc_sel = loc_cruce.get("sf_sel")
    if loc_sel is None or not len(loc_sel):
        return {"detalle": pd.DataFrame(), "duplicidades": pd.DataFrame()}

    cc_all_list = [x["sf_sel"] for x in lista_comunidades_sel.values() if len(x["sf_sel"])]
    if not cc_all_list:
        return {"detalle": pd.DataFrame(), "duplicidades": pd.DataFrame()}
    cc_all = pd.concat([align_crs(x, loc_sel) for x in cc_all_list], ignore_index=True)
    cc_all = gpd.GeoDataFrame(cc_all, geometry="geometry", crs=loc_sel.crs)

    loc_att = loc_cruce["tabla"].copy().reset_index(drop=True)
    loc_att["loc_id"] = range(len(loc_att))
    loc_pts = loc_sel.copy().reset_index(drop=True)
    loc_pts["loc_id"] = range(len(loc_pts))
    loc_pts = loc_pts[["loc_id", "geometry"]]

    ov = gpd.sjoin(
        loc_pts, cc_all[["cc_nombre", "cc_dpto", "cc_prov", "cc_dist", "cc_fuente", "geometry"]],
        how="inner", predicate="within",
    )
    if not len(ov):
        return {"detalle": pd.DataFrame(), "duplicidades": pd.DataFrame()}

    detalle = (
        ov.drop(columns="geometry")
        .merge(loc_att, on="loc_id", how="left")[
            ["nom_ccpp", "categoria", "num_hogares", "distrito", "provincia", "departamento", "cc_nombre", "cc_dist", "cc_fuente"]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    def _resumen_grupo(g):
        return pd.Series(
            {
                "n_cc": g["cc_nombre"].nunique(dropna=True),
                "fuentes": ", ".join(sorted(g["cc_fuente"].dropna().unique())),
                "cc_list": " | ".join(sorted(g["cc_nombre"].dropna().unique())),
            }
        )

    duplicidades = (
        detalle.groupby(["nom_ccpp", "categoria", "distrito", "provincia", "departamento"], dropna=False)
        .apply(_resumen_grupo, include_groups=False)
        .reset_index()
    )
    duplicidades["posible_duplicidad"] = duplicidades["n_cc"] > 1
    duplicidades = duplicidades.sort_values(
        ["n_cc", "provincia", "distrito", "nom_ccpp"], ascending=[False, True, True, True]
    ).reset_index(drop=True)

    return {"detalle": detalle, "duplicidades": duplicidades}


# ------------------------------------------------------------------------------
# 6) Verificación de comunidades MIDAGRI contra el padrón Excel (exacto + fuzzy)
# ------------------------------------------------------------------------------
def fuzzy_match_por_grupo(pendientes, candidatos, max_dist=2):
    ids = []
    if not len(pendientes):
        return ids
    for dep in pendientes["dep_key"].unique():
        psub = pendientes[pendientes["dep_key"] == dep]
        xsub = candidatos[candidatos["dep_key"] == dep]
        if not len(psub) or not len(xsub):
            continue
        xsub_keys = xsub["nom_key"].tolist()
        xsub_rowids = xsub["row_id"].tolist()
        for nom_key in psub["nom_key"]:
            dists = [Levenshtein.distance(nom_key, k) for k in xsub_keys]
            j = int(np.argmin(dists))
            if dists[j] <= max_dist:
                ids.append(xsub_rowids[j])
    return list(dict.fromkeys(ids))


def cruce_midagri_excel(tabla_midagri, cc_excel):
    if not len(tabla_midagri) or cc_excel is None or not len(cc_excel):
        return pd.DataFrame()

    keys_mid = tabla_midagri.assign(
        nom_key=tabla_midagri["nombre"].apply(norm_str),
        dep_key=tabla_midagri["departamento"].apply(norm_str),
    )
    keys_mid = keys_mid[(keys_mid["nom_key"] != "") & (keys_mid["dep_key"] != "")].drop_duplicates(
        subset=["nom_key", "dep_key"]
    )

    xl = limpiar_nombres(cc_excel)
    c_nom = get_col(list(xl.columns), ["comunidad", "nom_comunidad", "nom_comuni", "nom_comun", "nombre", "nombre_cc", "nomcc", "nom_cc"])
    c_dep = get_col(list(xl.columns), ["departamento", "nom_dpto", "dpto", "depa", "depart", "departamen"])
    if not c_nom or not c_dep:
        return pd.DataFrame()

    xl_keys = xl.copy()
    xl_keys["nom_key"] = xl_keys[c_nom].apply(norm_str)
    xl_keys["dep_key"] = xl_keys[c_dep].apply(norm_str)
    xl_keys["row_id"] = range(len(xl_keys))
    xl_keys = xl_keys[(xl_keys["nom_key"] != "") & (xl_keys["dep_key"] != "")]

    ids_exact = xl_keys.merge(
        keys_mid[["dep_key", "nom_key"]].drop_duplicates(), on=["dep_key", "nom_key"], how="inner"
    )["row_id"].tolist()

    pend = keys_mid.merge(
        xl_keys[["dep_key", "nom_key"]].drop_duplicates(), on=["dep_key", "nom_key"], how="left", indicator=True
    )
    pend = pend[pend["_merge"] == "left_only"]
    ids_fuzzy = fuzzy_match_por_grupo(pend, xl_keys, max_dist=2)

    final_ids = list(dict.fromkeys(ids_exact + ids_fuzzy))
    return xl_keys[xl_keys["row_id"].isin(final_ids)].drop(columns=["nom_key", "dep_key", "row_id"]).reset_index(drop=True)


# ------------------------------------------------------------------------------
# 7) Orquestador: corre TODOS los cruces seleccionados (checks) sobre un AOI.
#    Devuelve dict(resultados=<dict por check>, distritos_capa=<GeoDataFrame o None>).
#    Cada elemento de `resultados` puede ser una excepción (instancia de
#    Exception) si ese cruce falló -- revisar con `ok_resultado()` antes de usarlo.
# ------------------------------------------------------------------------------
def ok_resultado(x):
    return x is not None and not isinstance(x, Exception)


def ejecutar_cruces(cache, aoi, checks):
    resultados = {}
    distritos_capa = None

    def intentar_cruce(nombre_capa, fn_cruce):
        try:
            capa = cargar_capa(cache, nombre_capa, aoi)
            return fn_cruce(capa)
        except Exception as e:
            return e

    necesita_distritos = any(
        c in checks
        for c in [
            "distritos", "localidades", "cp_bdpi", "comunidades_midagri", "comunidades_bdpi",
            "comunidades_cofopri", "vias", "educacion",
        ]
    )
    if necesita_distritos:
        try:
            distritos_capa = cargar_capa(cache, "distritos", aoi)
        except Exception:
            distritos_capa = None

    if "distritos" in checks:
        if distritos_capa is None:
            resultados["distritos"] = RuntimeError("No se pudo cargar la capa de distritos.")
        else:
            try:
                resultados["distritos"] = cruce_distritos(aoi, distritos_capa)
            except Exception as e:
                resultados["distritos"] = e

    if "localidades" in checks or "duplicidades" in checks:
        resultados["localidades"] = intentar_cruce("localidades", lambda capa: cruce_localidades(aoi, capa))

    if "comunidades_bdpi" in checks or "duplicidades" in checks:
        resultados["comunidades_bdpi"] = intentar_cruce(
            "comunidades_bdpi",
            lambda capa: cruce_comunidad(aoi, capa, "BDPI", metodo="interseccion", tol_m=cfg.CONFIG_REPORTE["tolerancia_bdpi_m"]),
        )

    if "comunidades_midagri" in checks or "duplicidades" in checks:
        resultados["comunidades_midagri"] = intentar_cruce(
            "comunidades_midagri",
            lambda capa: cruce_comunidad(
                aoi, capa, "MIDAGRI", metodo="cascada", distancias_cascada=cfg.CONFIG_REPORTE["distancias_cascada_midagri"]
            ),
        )

    if "comunidades_cofopri" in checks or "duplicidades" in checks:
        resultados["comunidades_cofopri"] = intentar_cruce(
            "comunidades_cofopri", lambda capa: cruce_comunidad(aoi, capa, "COFOPRI", metodo="interseccion")
        )

    if "cp_bdpi" in checks:
        resultados["cp_bdpi"] = intentar_cruce("cp_bdpi", lambda capa: cruce_cp_bdpi(aoi, capa))

    if "vias" in checks:
        # 3 redes viales (nacional/departamental/vecinal), mismo patrón que
        # cruce_comunidad(): una llamada por jerarquía y se combinan. Cada
        # subcapa se intenta por separado -- si una falla o no está, las otras
        # igual se muestran.
        partes_tabla, partes_sf, errs = [], [], []
        for nombre_capa, jerarquia in [
            ("vias_nacional", "Nacional"),
            ("vias_departamental", "Departamental"),
            ("vias_vecinal", "Vecinal"),
        ]:
            r = intentar_cruce(nombre_capa, lambda capa, j=jerarquia: cruce_vias(aoi, capa, j))
            if isinstance(r, Exception):
                errs.append(f"{jerarquia}: {r}")
                continue
            if len(r["tabla"]):
                partes_tabla.append(r["tabla"])
            if len(r["sf_sel"]):
                partes_sf.append(r["sf_sel"].to_crs(4326))
        if not partes_tabla and errs:
            resultados["vias"] = RuntimeError("No se pudo calcular ninguna red vial. " + " | ".join(errs))
        else:
            tabla = pd.concat(partes_tabla, ignore_index=True) if partes_tabla else pd.DataFrame()
            sf_sel = (
                gpd.GeoDataFrame(pd.concat(partes_sf, ignore_index=True), geometry="geometry", crs=4326)
                if partes_sf
                else gpd.GeoDataFrame(geometry=[], crs=4326)
            )
            resultados["vias"] = {"tabla": tabla, "sf_sel": sf_sel}

    if "educacion" in checks:
        resultados["educacion"] = intentar_cruce("educacion", lambda capa: cruce_educacion(aoi, capa))

    if "duplicidades" in checks:
        fuentes_com = ["comunidades_bdpi", "comunidades_midagri", "comunidades_cofopri"]
        lista_com = {k: resultados[k] for k in fuentes_com if k in resultados and ok_resultado(resultados[k])}
        if ok_resultado(resultados.get("localidades")):
            try:
                resultados["duplicidades"] = cruce_localidades_en_comunidades(resultados["localidades"], lista_com)
            except Exception as e:
                resultados["duplicidades"] = e
        else:
            resultados["duplicidades"] = RuntimeError(
                "No se pudo calcular porque depende del cruce de localidades, que no se pudo calcular."
            )

    if "comunidades_midagri" in checks and ok_resultado(resultados.get("comunidades_midagri")):
        try:
            cc_excel = cargar_capa(cache, "cc_excel")
        except Exception:
            cc_excel = None
        try:
            resultados["midagri_excel"] = cruce_midagri_excel(resultados["comunidades_midagri"]["tabla"], cc_excel)
        except Exception:
            resultados["midagri_excel"] = pd.DataFrame()

    return {"resultados": resultados, "distritos_capa": distritos_capa}
