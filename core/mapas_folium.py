# ==============================================================================
# mapas_folium.py
# Builders de mapas INTERACTIVOS (folium) -- mismo rol que mapas.py
# (matplotlib, estático), pero con zoom/pan, popups por elemento y mapa base
# real. Puerto de R/03b_mapas_leaflet.R.
#
# Nota de tiles: CartoDB ahora exige API key (ver README) -- se usan
# "OpenStreetMap" y "Esri.WorldImagery" como capas base, confirmadas
# funcionando sin key ni bloqueo de red en este entorno.
# ==============================================================================

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .mapas import FAMILIAS_COMUNIDAD
from .procesamiento import align_crs, aoi_polygon

_MARGEN_ZOOM = 0.15


def _paleta_hex(etiqueta_capa, nombres):
    niveles = sorted(set(nombres))
    familia = FAMILIAS_COMUNIDAD.get(etiqueta_capa)
    cmap = plt.get_cmap(familia if familia else "Set3")
    vals = np.linspace(0.4, 0.9, max(len(niveles), 1)) if familia else np.linspace(0.05, 0.95, max(len(niveles), 1))
    colores = {n: _to_hex(cmap(v)) for n, v in zip(niveles, vals)}
    return colores


def _to_hex(rgba):
    r, g, b = (int(255 * c) for c in rgba[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _contorno_aoi(aoi_ll):
    """Filas de tipo polígono/línea del AOI, para dibujar el contorno --
    tolerante a KML con geometría mixta (ver nota equivalente en R)."""
    tipos = aoi_ll.geometry.geom_type
    mask = tipos.str.contains("Polygon") | tipos.str.contains("LineString")
    return aoi_ll[mask]


def _base_folium(aoi, distritos):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    aoi_ll = aoi_p.to_crs(4326)
    dist_ll = distritos.to_crs(4326)

    minx, miny, maxx, maxy = aoi_ll.total_bounds
    mx = _MARGEN_ZOOM * (maxx - minx)
    my = _MARGEN_ZOOM * (maxy - miny)
    centro = [(miny + maxy) / 2, (minx + maxx) / 2]

    m = folium.Map(location=centro, tiles="OpenStreetMap", control_scale=True)
    folium.TileLayer("Esri.WorldImagery", name="Satélite").add_to(m)
    m.fit_bounds([[miny - my, minx - mx], [maxy + my, maxx + mx]])

    tooltip_dist = folium.GeoJsonTooltip(fields=["distrito"]) if "distrito" in dist_ll.columns else None
    folium.GeoJson(
        dist_ll, name="Distritos",
        style_function=lambda f: {"fillColor": "#e0e0e0", "color": "black", "weight": 1, "fillOpacity": 0.25},
        tooltip=tooltip_dist,
    ).add_to(m)

    contorno = _contorno_aoi(aoi_ll)
    if len(contorno):
        folium.GeoJson(
            contorno, name="Área de estudio",
            style_function=lambda f: {"color": "red", "weight": 3, "fillOpacity": 0},
        ).add_to(m)

    return m


def _limpio(v, vacio="s/d"):
    """Normaliza None/NaN/pd.NA a un placeholder legible -- para que nunca se
    vea "None"/"<NA>"/"nan" crudo en un popup (mismo problema que "None" en
    las tablas de la app, ver _tabla() en app.py, pero acá hay que limpiarlo
    a mano porque el popup es puro HTML armado con un f-string)."""
    if v is None:
        return vacio
    try:
        if pd.isna(v):
            return vacio
    except (TypeError, ValueError):
        pass
    return v


def _popup_html(campos):
    filas = "".join(f"<b>{k}</b>: {_limpio(v)}<br/>" for k, v in campos.items())
    return folium.Popup(filas, max_width=300)


def _etiqueta(lat, lon, texto, color="#222"):
    """Etiqueta de texto SIEMPRE visible (no solo al pasar el mouse como el
    tooltip) -- un Marker invisible con un DivIcon de texto, con halo blanco
    para que se lea sobre cualquier color de fondo."""
    if not texto:
        return None
    html = (
        f'<div style="font-size:11px;font-weight:600;color:{color};white-space:nowrap;'
        'text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;">'
        f"{texto}</div>"
    )
    return folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(-6, 6)),
    )


# ------------------------------------------------------------------------------
# Mapa: distritos intersectados
# ------------------------------------------------------------------------------
def mapa_folium_distritos(aoi, distritos, dist_int):
    m = _base_folium(aoi, distritos)
    dist_ll = dist_int.to_crs(4326)
    grupo = folium.FeatureGroup(name="Distritos intersectados")
    for _, row in dist_ll.iterrows():
        folium.GeoJson(
            gpd.GeoSeries([row.geometry], crs=4326),
            style_function=lambda f: {"fillColor": "steelblue", "color": "steelblue", "weight": 2, "fillOpacity": 0.35},
            tooltip=str(row.get("distrito") or ""),
            popup=_popup_html(
                {"Distrito": row.get("distrito"), "Provincia": row.get("provincia"), "Departamento": row.get("departamento")}
            ),
        ).add_to(grupo)
        c = row.geometry.representative_point()
        etiqueta = _etiqueta(c.y, c.x, row.get("distrito"), color="#1a4971")
        if etiqueta:
            etiqueta.add_to(grupo)
    grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ------------------------------------------------------------------------------
# Mapa: localidades (Centro poblado / Población dispersa)
# ------------------------------------------------------------------------------
def mapa_folium_localidades(aoi, distritos, loc_sel):
    m = _base_folium(aoi, distritos)
    loc_ll = loc_sel.to_crs(4326)
    colores = {"Centro poblado": "#d1495b", "Población dispersa": "#1b998b"}
    grupo = folium.FeatureGroup(name="Localidades")
    for _, row in loc_ll.iterrows():
        cat = row.get("categoria") or "Localidad"
        color = colores.get(cat, "#666666")
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x], radius=6, color="white", weight=1,
            fill=True, fill_color=color, fill_opacity=0.9,
            tooltip=str(row.get("nom_ccpp") or ""),
            popup=_popup_html(
                {"Localidad": row.get("nom_ccpp"), "Categoría": cat, "Hogares": row.get("num_hogares"), "Distrito": row.get("distrito")}
            ),
        ).add_to(grupo)
        etiqueta = _etiqueta(row.geometry.y, row.geometry.x, row.get("nom_ccpp"), color=color)
        if etiqueta:
            etiqueta.add_to(grupo)
    grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ------------------------------------------------------------------------------
# Mapa: comunidades (BDPI / MIDAGRI / COFOPRI) — genérico
# ------------------------------------------------------------------------------
def mapa_folium_comunidad(aoi, distritos, sf_sel, etiqueta_capa="Comunidad"):
    m = _base_folium(aoi, distritos)
    sel_ll = sf_sel.to_crs(4326)
    nombres = sel_ll["cc_nombre"].fillna("Sin nombre") if "cc_nombre" in sel_ll.columns else ["Sin nombre"] * len(sel_ll)
    colores = _paleta_hex(etiqueta_capa, nombres)
    # Agrupadas en un solo FeatureGroup con nombre: sin esto, cada comunidad
    # queda como una capa suelta con un id autogenerado feo en el control de
    # capas, en vez de un único interruptor con el nombre de la fuente.
    grupo = folium.FeatureGroup(name=etiqueta_capa)
    for (_, row), nom in zip(sel_ll.iterrows(), nombres):
        color = colores.get(nom, "#999999")
        folium.GeoJson(
            gpd.GeoSeries([row.geometry], crs=4326),
            style_function=lambda f, c=color: {"fillColor": c, "color": c, "weight": 2, "fillOpacity": 0.55},
            tooltip=str(nom),
            popup=_popup_html({etiqueta_capa: nom, "Distrito": row.get("cc_dist"), "Provincia": row.get("cc_prov")}),
        ).add_to(grupo)
        c_pt = row.geometry.representative_point()
        etiqueta = _etiqueta(c_pt.y, c_pt.x, nom, color=color)
        if etiqueta:
            etiqueta.add_to(grupo)
    grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ------------------------------------------------------------------------------
# Mapa: centros poblados indígenas BDPI (puntos)
# ------------------------------------------------------------------------------
def mapa_folium_cp_bdpi(aoi, distritos, cp_sel):
    m = _base_folium(aoi, distritos)
    cp_ll = cp_sel.to_crs(4326)
    grupo = folium.FeatureGroup(name="Centros poblados indígenas")
    for _, row in cp_ll.iterrows():
        nom = row.get("nom_label") or ""
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x], radius=6, color="white", weight=1,
            fill=True, fill_color="firebrick", fill_opacity=0.9,
            tooltip=str(nom), popup=_popup_html({"Centro poblado indígena": nom}),
        ).add_to(grupo)
        etiqueta = _etiqueta(row.geometry.y, row.geometry.x, nom, color="firebrick")
        if etiqueta:
            etiqueta.add_to(grupo)
    grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ------------------------------------------------------------------------------
# Mapa: vías (red vial nacional / departamental / vecinal) — líneas
# ------------------------------------------------------------------------------
_COLOR_VIA = {"Nacional": "#c0392b", "Departamental": "#e67e22", "Vecinal": "#7f8c8d"}


def mapa_folium_vias(aoi, distritos, sf_sel):
    m = _base_folium(aoi, distritos)
    vias_ll = sf_sel.to_crs(4326)
    jerarquias = (
        vias_ll["via_jerarquia"].fillna("Otra") if "via_jerarquia" in vias_ll.columns else ["Otra"] * len(vias_ll)
    )
    for jer in sorted(set(jerarquias)):
        color = _COLOR_VIA.get(jer, "#555555")
        grupo = folium.FeatureGroup(name=f"Vías — {jer}")
        sub = vias_ll[jerarquias == jer] if hasattr(jerarquias, "__len__") else vias_ll
        for _, row in sub.iterrows():
            cod = row.get("via_codigo")
            nom = row.get("via_nombre")
            folium.GeoJson(
                gpd.GeoSeries([row.geometry], crs=4326),
                style_function=lambda f, c=color: {"color": c, "weight": 3, "opacity": 0.9},
                tooltip=str(cod or nom or ""),
                popup=_popup_html({"Código": cod, "Tramo": nom, "Jerarquía": jer}),
            ).add_to(grupo)
        grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ------------------------------------------------------------------------------
# Mapa: centros educativos (instituciones educativas) — puntos
# ------------------------------------------------------------------------------
_COLOR_NIVEL_EDU = {
    "Inicial": "#2e86de",
    "Primaria": "#10ac84",
    "Secundaria": "#ee5253",
    "Superior / Técnica": "#8e44ad",
    "Básica Especial": "#f39c12",
    "Básica Alternativa / Otros": "#576574",
}


def mapa_folium_educacion(aoi, distritos, sf_sel):
    m = _base_folium(aoi, distritos)
    edu_ll = sf_sel.to_crs(4326)
    niveles = (
        edu_ll["ie_nivel_grupo"].fillna("Otros") if "ie_nivel_grupo" in edu_ll.columns else ["Otros"] * len(edu_ll)
    )
    for niv in sorted(set(niveles)):
        color = _COLOR_NIVEL_EDU.get(niv, "#576574")
        grupo = folium.FeatureGroup(name=f"IE — {niv}")
        sub = edu_ll[niveles == niv] if hasattr(niveles, "__len__") else edu_ll
        for _, row in sub.iterrows():
            nom = row.get("ie_nombre") or ""
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x], radius=5, color="white", weight=1,
                fill=True, fill_color=color, fill_opacity=0.9,
                tooltip=str(nom), popup=_popup_html({"Institución educativa": nom, "Nivel": niv}),
            ).add_to(grupo)
            etiqueta = _etiqueta(row.geometry.y, row.geometry.x, nom, color=color)
            if etiqueta:
                etiqueta.add_to(grupo)
        grupo.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m
