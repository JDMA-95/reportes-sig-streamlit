# Reportes SIG (Streamlit)

Migración a Python/Streamlit de la app R/Shiny `reportes_sig` (ver
`../reportes_sig/reportes_sig/`): el usuario sube el **área de estudio
(KML)**, marca qué **cruces** de información social quiere consultar
(distritos, localidades, comunidades BDPI/MIDAGRI/COFOPRI, centros poblados
indígenas, duplicidades entre fuentes, **vías** y **centros educativos**) y
ve tablas + mapas por cada uno.

Las dos últimas capas (vías + centros educativos) no existen en la versión
R: sus shapefiles viven en `../Datos adicionales/` y se configuran con
`RUTA_CARPETA_DATOS_ADIC` (ver `core/config.py`).

La versión R sigue siendo la fuente de verdad para el reporte en PDF (que
usa `rmarkdown`, sin equivalente directo aquí) — esta versión Streamlit es
para la vista previa interactiva, con el mismo motor de cálculo portado a
Python/`geopandas`.

## Estructura

```
reportes_sig_streamlit/
├── app.py                # App Streamlit (KML + checkboxes + vista previa)
├── requirements.txt
├── core/
│   ├── config.py          # ÚNICO archivo a editar para producción: capas, cruces
│   ├── io_capas.py         # Acceso a datos (demo local o ruta local), con filtro espacial
│   ├── procesamiento.py    # Lógica de cruce espacial (puerto de R/02_procesamiento.R)
│   └── mapas.py            # Builders de mapas (matplotlib)
└── demo_data/              # Capas sintéticas + KML de ejemplo (copiado del proyecto R)
```

## 1. Probar en modo demo

```bash
set REPORTES_MODE=demo
python -m streamlit run app.py
```

## 2. Modo real (datos reales)

Por defecto (`core/config.py`) ya apunta a `RUTA_CARPETA_DATOS =
"D:/Intento de mejorar/reportes_sig/datos"`, la misma carpeta que usa la
versión R. Para usar otra carpeta:

```bash
set RUTA_CARPETA_DATOS=D:\ruta\a\la\carpeta
python -m streamlit run app.py
```

## 3. Dependencias

```bash
pip install -r requirements.txt
```

`geopandas`/`pyogrio` traen sus propias dependencias de GDAL/GEOS/PROJ
precompiladas (wheels) — no hace falta instalar nada del sistema aparte.

## 4. Diferencias conocidas frente a la versión R

- **Sin reporte PDF**: la versión R ya tampoco lo expone en su interfaz (se
  quitó por problemas de LaTeX en la red del usuario); si se necesita en
  algún momento en Python, la opción más directa sería `WeasyPrint` o
  `reportlab` a partir de las mismas tablas/mapas.
- **Mapa interactivo (`folium`)**: a diferencia de la versión R (que usaba
  `leaflet` y se descartó porque CartoDB, el proveedor de tiles usado ahí,
  ahora exige API key para su capa gratuita), aquí se usan `OpenStreetMap` +
  `Esri.WorldImagery` como capas base — confirmado que cargan sin necesitar
  key ni tener problemas de red. `core/mapas.py` (matplotlib, estático)
  sigue disponible por si en algún momento se necesita una versión sin
  dependencia de tiles de internet.
- **Codificación de la capa de Localidades**: el `.dbf` de esa capa declara
  UTF-8 en su `.cpg` pero el contenido real está corrupto (mismo problema
  documentado en el README R) — `io_capas.leer_shp_local()` reintenta con
  `latin1` si falla la lectura UTF-8, igual que R/GDAL toleran esto de forma
  más permisiva por defecto.
- **Caché por sesión vía `st.session_state`** (no una variable de módulo):
  un proceso Streamlit atiende a todos los usuarios a la vez, así que el
  caché de capas (con filtro espacial por área de estudio) debe vivir por
  sesión/navegador para no mezclar el filtro de un usuario con el de otro.
