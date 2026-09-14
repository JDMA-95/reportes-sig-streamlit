# ==============================================================================
# mapas.py
# Builders de mapas (matplotlib), puerto de R/03_mapas.R (incluye las mejoras
# estéticas agregadas después: barra de escala, flecha de norte, mini-mapa de
# ubicación y paleta fija por fuente para comunidades).
#
# A diferencia de la version R (que grafica en lat/lon con ggspatial
# calculando la escala geodésica), aquí se reproyecta todo a la UTM local
# (ver procesamiento.to_utm_epsg) antes de graficar -- la barra de escala
# queda trivial (1 unidad de dato = 1 metro) y es mas preciso.
# ==============================================================================

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from matplotlib_scalebar.scalebar import ScaleBar
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from .procesamiento import align_crs, aoi_polygon, to_utm_epsg

FAMILIAS_COMUNIDAD = {
    "Comunidades BDPI": "Oranges",
    "Comunidades MIDAGRI": "Greens",
    "Comunidades COFOPRI": "Blues",
}


def _paleta_comunidad(etiqueta_capa, n):
    n = max(n, 1)
    familia = FAMILIAS_COMUNIDAD.get(etiqueta_capa)
    cmap = plt.get_cmap(familia if familia else "Set3")
    if familia:
        # tonos medios/oscuros -- evita los casi-blancos del extremo claro,
        # poco legibles sobre el fondo gris del mapa.
        vals = np.linspace(0.4, 0.9, n)
    else:
        vals = np.linspace(0.05, 0.95, n)
    return [cmap(v) for v in vals]


def _marco_zoom(aoi_m, margen=0.15):
    minx, miny, maxx, maxy = aoi_m.total_bounds
    mx = margen * (maxx - minx)
    my = margen * (maxy - miny)
    return minx - mx, miny - my, maxx + mx, maxy + my


def _norte(ax):
    ax.annotate(
        "N", xy=(0.94, 0.90), xytext=(0.94, 0.80), xycoords="axes fraction",
        ha="center", va="center", fontsize=11, fontweight="bold", color="#222",
        arrowprops=dict(arrowstyle="-|>", color="#222", lw=1.6),
    )


def _escala(ax, epsg):
    ax.add_artist(ScaleBar(1, units="m", location="lower left", box_alpha=0.75, color="#333", scale_loc="bottom"))


def _tema_base(ax, titulo, subtitulo):
    ax.set_title(titulo, fontsize=13, fontweight="bold", loc="left")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor("white")
    if subtitulo:
        ax.text(0.0, 1.06, subtitulo, transform=ax.transAxes, fontsize=10, color="grey", va="bottom")


def _leyenda(ax, ncol=3):
    # El AOI real puede traer decenas de geometrías sueltas (KML con toda la
    # infraestructura del sitio, no solo el polígono del área de estudio) --
    # geopandas dibuja cada una como un artista propio, así que sin dedup la
    # leyenda repite "Área de estudio" una vez por geometría.
    handles, labels = ax.get_legend_handles_labels()
    por_etiqueta = dict(zip(labels, handles))
    if por_etiqueta:
        leg = ax.legend(
            por_etiqueta.values(), por_etiqueta.keys(), loc="upper center", bbox_to_anchor=(0.5, -0.03), ncol=ncol,
            frameon=True, fontsize=9, title_fontsize=10, edgecolor="#d9d9d9",
        )
        return leg
    return None


def _inset_ubicacion(fig, ax_principal, distritos_ll, aoi_bbox_ll):
    """Mini-mapa de ubicación (esquina inferior derecha): la capa de distritos
    ya cargada (más amplia que el AOI -- ver io_capas._bbox_para_capa) a
    escala reducida, con un recuadro rojo marcando la vista principal. Solo
    se agrega si esa capa cubre bastante más área que el AOI (da contexto
    real, no es solo un duplicado de lo que ya se ve)."""
    minx_a, miny_a, maxx_a, maxy_a = aoi_bbox_ll
    area_a = (maxx_a - minx_a) * (maxy_a - miny_a)
    minx_d, miny_d, maxx_d, maxy_d = distritos_ll.total_bounds
    area_d = (maxx_d - minx_d) * (maxy_d - miny_d)
    if not np.isfinite(area_a) or area_a <= 0 or not np.isfinite(area_d) or area_d / area_a < 4:
        return
    axins = inset_axes(ax_principal, width="26%", height="26%", loc="lower right", borderpad=0.6)
    distritos_ll.plot(ax=axins, facecolor="#d9d9d9", edgecolor="#808080", linewidth=0.3)
    axins.add_patch(
        Rectangle((minx_a, miny_a), maxx_a - minx_a, maxy_a - miny_a, fill=False, edgecolor="red", linewidth=1.3)
    )
    axins.set_xticks([]); axins.set_yticks([])
    for spine in axins.spines.values():
        spine.set_edgecolor("#808080"); spine.set_linewidth(0.8)


def _finalizar(fig, ax, distritos, aoi_p, epsg, titulo, subtitulo):
    _tema_base(ax, titulo, subtitulo)
    _norte(ax)
    _escala(ax, epsg)
    _leyenda(ax)
    aoi_bbox_ll = aoi_p.to_crs(4326).total_bounds if aoi_p.crs is not None else aoi_p.total_bounds
    try:
        _inset_ubicacion(fig, ax, distritos.to_crs(4326), aoi_bbox_ll)
    except Exception:
        pass
    # No fig.tight_layout(): no es compatible con el inset_axes de la mini-
    # ubicación (tira un warning y no ajusta bien). En su lugar, quien llame a
    # st.pyplot()/fig.savefig() debe pasar bbox_inches="tight".
    return fig


# ------------------------------------------------------------------------------
# Mapa: distritos intersectados
# ------------------------------------------------------------------------------
def mapa_distritos(aoi, distritos, dist_int):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    aoi_m, dist_m, epsg = _prep(aoi_p, distritos)
    _, dist_int_m, _ = _prep(aoi_p, dist_int, epsg_fijo=epsg)

    fig, ax = plt.subplots(figsize=(9, 7), dpi=120)
    dist_m.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.6, label="Límite distrital")
    if len(dist_int_m):
        dist_int_m.plot(ax=ax, facecolor="steelblue", alpha=0.35, edgecolor="none")
        for _, row in dist_int_m.iterrows():
            etiqueta = row.get("distrito") if row.get("distrito") else None
            if etiqueta:
                c = row.geometry.representative_point()
                ax.annotate(etiqueta, (c.x, c.y), fontsize=8, ha="center",
                            path_effects=None)
    aoi_m.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.6, linestyle=(0, (6, 3)), label="Área de estudio")

    xlim = _marco_zoom(aoi_m)
    ax.set_xlim(xlim[0], xlim[2]); ax.set_ylim(xlim[1], xlim[3])
    ax.set_aspect("equal")
    return _finalizar(fig, ax, dist_m, aoi_m, epsg, "Distritos superpuestos con el Área de Estudio",
                       f"Intersectados: {len(dist_int)}")


def _prep(aoi_p, capa, epsg_fijo=None):
    """Reproyecta aoi_p y capa a una UTM comun (o a epsg_fijo si se pasa, para
    que todas las capas de un mismo mapa queden en el MISMO CRS)."""
    epsg = epsg_fijo or to_utm_epsg(aoi_p.to_crs(4326))
    aoi_m = aoi_p.to_crs(epsg)
    capa_m = capa.to_crs(epsg) if len(capa) else capa.set_crs(epsg, allow_override=True)
    return aoi_m, capa_m, epsg


# ------------------------------------------------------------------------------
# Mapa: localidades (Centro poblado / Población dispersa)
# ------------------------------------------------------------------------------
def mapa_localidades(aoi, distritos, loc_sel):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    aoi_m, dist_m, epsg = _prep(aoi_p, distritos)
    _, loc_m, _ = _prep(aoi_p, loc_sel, epsg_fijo=epsg)

    fig, ax = plt.subplots(figsize=(9, 7), dpi=120)
    dist_m.plot(ax=ax, facecolor="#f7f7f7", edgecolor="black", linewidth=0.35)
    aoi_m.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.6, linestyle=(0, (6, 3)), label="Área de estudio")

    if len(loc_m):
        categorias = loc_m["categoria"].fillna("Localidad") if "categoria" in loc_m.columns else "Localidad"
        marcadores = {"Centro poblado": "o", "Población dispersa": "^"}
        for cat, sub in loc_m.groupby(categorias):
            marker = marcadores.get(cat, "o")
            sub.plot(ax=ax, marker=marker, markersize=45, color="#d1495b" if cat == "Centro poblado" else "#1b998b",
                     label=cat)
            for _, row in sub.iterrows():
                nom = row.get("nom_ccpp")
                if nom:
                    ax.annotate(nom, (row.geometry.x, row.geometry.y), fontsize=8, xytext=(4, 4),
                                textcoords="offset points")

    xlim = _marco_zoom(aoi_m)
    ax.set_xlim(xlim[0], xlim[2]); ax.set_ylim(xlim[1], xlim[3])
    ax.set_aspect("equal")
    return _finalizar(fig, ax, dist_m, aoi_m, epsg, "Localidades dentro del Área de Estudio", f"n = {len(loc_sel)}")


# ------------------------------------------------------------------------------
# Mapa: comunidades (BDPI / MIDAGRI / COFOPRI) — genérico
# ------------------------------------------------------------------------------
def mapa_comunidad(aoi, distritos, sf_sel, etiqueta_capa="Comunidad"):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    aoi_m, dist_m, epsg = _prep(aoi_p, distritos)
    _, sel_m, _ = _prep(aoi_p, sf_sel, epsg_fijo=epsg)

    fig, ax = plt.subplots(figsize=(9, 7), dpi=120)
    dist_m.plot(ax=ax, facecolor="#f7f7f7", edgecolor="black", linewidth=0.35)
    aoi_m.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.6, linestyle=(0, (6, 3)), label="Área de estudio")

    if len(sel_m):
        nombres = sel_m["cc_nombre"].fillna("Sin nombre") if "cc_nombre" in sel_m.columns else "Sin nombre"
        niveles = sorted(nombres.unique()) if hasattr(nombres, "unique") else [nombres]
        colores = dict(zip(niveles, _paleta_comunidad(etiqueta_capa, len(niveles))))
        for nom in niveles:
            sub = sel_m[nombres == nom]
            sub.plot(ax=ax, facecolor=colores[nom], edgecolor=colores[nom], linewidth=1.2, alpha=0.75, label=nom)

    xlim = _marco_zoom(aoi_m)
    ax.set_xlim(xlim[0], xlim[2]); ax.set_ylim(xlim[1], xlim[3])
    ax.set_aspect("equal")
    return _finalizar(fig, ax, dist_m, aoi_m, epsg, f"{etiqueta_capa} en el Área de Estudio", f"n = {len(sf_sel)}")


# ------------------------------------------------------------------------------
# Mapa: centros poblados indígenas BDPI (puntos)
# ------------------------------------------------------------------------------
def mapa_cp_bdpi(aoi, distritos, cp_sel):
    aoi_p = align_crs(aoi_polygon(aoi), distritos)
    aoi_m, dist_m, epsg = _prep(aoi_p, distritos)
    _, cp_m, _ = _prep(aoi_p, cp_sel, epsg_fijo=epsg)

    fig, ax = plt.subplots(figsize=(9, 7), dpi=120)
    dist_m.plot(ax=ax, facecolor="#f7f7f7", edgecolor="black", linewidth=0.35)
    aoi_m.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.6, linestyle=(0, (6, 3)), label="Área de estudio")

    if len(cp_m):
        cp_m.plot(ax=ax, marker="o", markersize=45, color="firebrick", label="CP indígena")
        for _, row in cp_m.iterrows():
            nom = row.get("nom_label")
            if nom:
                ax.annotate(nom, (row.geometry.x, row.geometry.y), fontsize=8, xytext=(4, 4), textcoords="offset points")

    xlim = _marco_zoom(aoi_m)
    ax.set_xlim(xlim[0], xlim[2]); ax.set_ylim(xlim[1], xlim[3])
    ax.set_aspect("equal")
    return _finalizar(fig, ax, dist_m, aoi_m, epsg, "Centros Poblados Indígenas (BDPI) dentro del Área de Estudio",
                       f"n = {len(cp_sel)}")
