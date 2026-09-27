# ==============================================================================
# exportar.py
# Arma un único archivo Excel (una hoja por cruce ejecutado) a partir del
# `resultado` guardado en session_state -- reemplaza en espíritu al reporte
# PDF que tenía la versión R (descontinuado por problemas de LaTeX en la red
# del usuario, ver README).
# ==============================================================================

import io
import re

import pandas as pd

from .procesamiento import ok_resultado

# Nombres cortos por cruce para las hojas del Excel (las etiquetas completas
# de CONFIG_CRUCES son muy largas para el límite de 31 caracteres de Excel).
_NOMBRE_CORTO = {
    "distritos": "Distritos",
    "localidades": "Localidades",
    "comunidades_bdpi": "Comunidades BDPI",
    "cp_bdpi": "Centros poblados BDPI",
    "comunidades_midagri": "Comunidades MIDAGRI",
    "comunidades_cofopri": "Comunidades COFOPRI",
    "vias": "Vías",
    "educacion": "Centros educativos",
}

_INVALIDOS_HOJA = re.compile(r"[\[\]:\*\?/\\]")


def _nombre_hoja(nombre, usados):
    """Nombre de hoja válido para Excel (máx. 31 caracteres, sin
    [ ] : * ? / \\, único dentro del archivo)."""
    limpio = _INVALIDOS_HOJA.sub(" ", nombre).strip()[:31] or "Hoja"
    base, i = limpio, 1
    while limpio in usados:
        sufijo = f" ({i})"
        limpio = (base[: 31 - len(sufijo)] + sufijo) if len(base) + len(sufijo) > 31 else base + sufijo
        i += 1
    usados.add(limpio)
    return limpio


def construir_excel(resultado):
    """Arma un .xlsx en memoria con una hoja por tabla de cada cruce
    ejecutado (y con resultado válido). Devuelve los bytes del archivo, o
    None si no hay ninguna tabla con datos para exportar."""
    resultados = resultado["resultados"]
    usados = set()
    buffer = io.BytesIO()
    hubo_contenido = False

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for id_ in resultado["checks"]:
            r = resultados.get(id_)
            if not ok_resultado(r) or not isinstance(r, dict):
                continue
            nombre_base = _NOMBRE_CORTO.get(id_, id_)

            tabla = r.get("tabla")
            if tabla is not None and len(tabla):
                tabla.fillna("").to_excel(writer, sheet_name=_nombre_hoja(nombre_base, usados), index=False)
                hubo_contenido = True

            resumen = r.get("resumen")
            if resumen is not None and len(resumen):
                resumen.fillna("").to_excel(
                    writer, sheet_name=_nombre_hoja(f"{nombre_base} (resumen)", usados), index=False
                )
                hubo_contenido = True

            if id_ == "comunidades_midagri":
                midagri_excel = resultados.get("midagri_excel")
                if midagri_excel is not None and len(midagri_excel):
                    midagri_excel.fillna("").to_excel(
                        writer, sheet_name=_nombre_hoja("MIDAGRI vs padrón Excel", usados), index=False
                    )
                    hubo_contenido = True

    if not hubo_contenido:
        return None
    return buffer.getvalue()
