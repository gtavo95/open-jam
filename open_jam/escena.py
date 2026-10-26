"""Datos de la escena 3D: relieve y edificios, en las coordenadas de la red de SUMO.

  terreno.bin   uint16[filas*cols]  altura en decímetros sobre `base_m`, una celda cada
                                    `paso_m` metros, fila 0 en y = bbox.y0
  escena.json   índice del terreno, edificios [[x0,y0,x1,y1,...], alto_m] y zonas
                {"n": "Zona 10", "anillos": [[x0,y0,...]], "centro": [x, y]}, recortadas
                al área

Relieve: AWS Terrain Tiles (Terrarium, zoom 13, ~18 m por pixel acá; fuentes SRTM y
otras, atribución requerida). Edificios: OpenStreetMap vía Overpass (ODbL). En Guatemala
pocos traen altura; al resto se le estima por área (casa de 1–2 niveles, bodega o torre).
Zonas: límites administrativos de OSM (zonas de la ciudad y el municipio de Mixco).

Uso: uv run python -m open_jam.escena
"""

import hashlib
import io
import json
import math
import re
import ssl
import urllib.parse
import urllib.request

import certifi
import numpy as np
import pyproj
from PIL import Image

from . import rutas

TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS = "https://overpass-api.de/api/interpreter"
ZOOM = 13
PASO_M = 20
CACHE = rutas.DATA / "cache"


def ubicacion():
    """netOffset y proyección de la red (la línea <location> de area.net.xml)."""
    with open(rutas.NET) as f:
        for linea in f:
            if "<location" in linea:
                a = dict(re.findall(r'(\w+)="([^"]*)"', linea))
                break
    dx, dy = map(float, a["netOffset"].split(","))
    x0, y0, x1, y1 = map(float, a["convBoundary"].split(","))
    return pyproj.Proj(a["projParameter"]), dx, dy, (x0, y0, x1, y1)


def bajar(url, datos=None):
    """Descarga con caché en data/cache/: rehacer la escena no vuelve a pedirle nada a Overpass ni a AWS."""
    archivo = CACHE / hashlib.sha256(url.encode() + (datos or b"")).hexdigest()
    if archivo.exists():
        return archivo.read_bytes()
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": "open-jam/0.1"})
    with urllib.request.urlopen(req, timeout=180, context=ssl.create_default_context(cafile=certifi.where())) as r:
        cuerpo = r.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    archivo.write_bytes(cuerpo)
    return cuerpo


def tesela(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def terreno(proj, dx, dy, bbox):
    x0, y0, x1, y1 = bbox
    xs = np.arange(x0, x1 + PASO_M, PASO_M)
    ys = np.arange(y0, y1 + PASO_M, PASO_M)
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = proj(gx - dx, gy - dy, inverse=True)
    n = 2 ** ZOOM
    tx = (lon + 180) / 360 * n
    ty = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n
    cx0, cx1 = int(tx.min()), int(tx.max())
    cy0, cy1 = int(ty.min()), int(ty.max())
    mosaico = np.zeros(((cy1 - cy0 + 1) * 256, (cx1 - cx0 + 1) * 256), np.float32)
    for cx in range(cx0, cx1 + 1):
        for cy in range(cy0, cy1 + 1):
            png = np.asarray(Image.open(io.BytesIO(bajar(TERRARIUM.format(z=ZOOM, x=cx, y=cy)))).convert("RGB"), np.float32)
            alto = png[..., 0] * 256 + png[..., 1] + png[..., 2] / 256 - 32768
            mosaico[(cy - cy0) * 256:(cy - cy0 + 1) * 256, (cx - cx0) * 256:(cx - cx0 + 1) * 256] = alto
    # bilineal sobre el mosaico (pixel k cubre [k, k+1), su centro está en k + 0.5)
    px = (tx - cx0) * 256 - 0.5
    py = (ty - cy0) * 256 - 0.5
    i, j = np.floor(py).astype(int), np.floor(px).astype(int)
    fy, fx = py - i, px - j
    m = mosaico
    z = (m[i, j] * (1 - fx) * (1 - fy) + m[i, j + 1] * fx * (1 - fy)
         + m[i + 1, j] * (1 - fx) * fy + m[i + 1, j + 1] * fx * fy)
    base = float(np.floor(z.min()))
    return np.round((z - base) * 10).astype(np.uint16), base, len(ys), len(xs)


def alto_estimado(poly, tags):
    if "height" in tags:
        try:
            return float(tags["height"].split()[0])
        except ValueError:
            pass
    if "building:levels" in tags:
        try:
            return float(tags["building:levels"]) * 3.2
        except ValueError:
            pass
    xs, ys = poly[0::2], poly[1::2]
    area = abs(sum(xs[k] * ys[k + 1] - xs[k + 1] * ys[k] for k in range(len(xs) - 1))) / 2
    # determinista por forma: una casa no cambia de altura entre exportes
    h = (int(abs(xs[0] * 7 + ys[0] * 13)) % 100) / 100
    if area < 150:
        return 3.5 + 3 * h
    if area < 1500:
        return 6 + 9 * h
    return 8 + 30 * h ** 3


def edificios(proj, dx, dy, bbox):
    x0, y0, x1, y1 = bbox
    (lo0, la0), (lo1, la1) = proj(x0 - dx, y0 - dy, inverse=True), proj(x1 - dx, y1 - dy, inverse=True)
    q = f'[out:json][timeout:180];way["building"]({la0},{lo0},{la1},{lo1});out tags geom;'
    datos = json.loads(bajar(OVERPASS, urllib.parse.urlencode({"data": q}).encode()))
    res = []
    for w in datos["elements"]:
        g = w.get("geometry")
        if not g or len(g) < 4:
            continue
        x, y = proj([p["lon"] for p in g], [p["lat"] for p in g])
        poly = [round(v, 1) for xy in zip(np.add(x, dx), np.add(y, dy)) for v in xy]
        res.append([poly, round(alto_estimado(poly, w.get("tags", {})), 1)])
    return res


def unir(trazos):
    """Une los trazos (way) de una relación en anillos cerrados, por sus extremos."""
    trazos = [list(t) for t in trazos]
    anillos = []
    while trazos:
        a = trazos.pop()
        cambio = True
        while a[0] != a[-1] and cambio:
            cambio = False
            for k, t in enumerate(trazos):
                if t[0] == a[-1]:
                    a += t[1:]
                elif t[-1] == a[-1]:
                    a += t[-2::-1]
                elif t[-1] == a[0]:
                    a = t[:-1] + a
                elif t[0] == a[0]:
                    a = t[:0:-1] + a
                else:
                    continue
                trazos.pop(k)
                cambio = True
                break
        if len(a) > 3:
            anillos.append(a)
    return anillos


def recortar(pts, bbox):
    """Sutherland–Hodgman contra el rectángulo del área."""
    x0, y0, x1, y1 = bbox
    lados = [(lambda p: p[0] >= x0, lambda p, q: x0, 0), (lambda p: p[0] <= x1, lambda p, q: x1, 0),
             (lambda p: p[1] >= y0, lambda p, q: y0, 1), (lambda p: p[1] <= y1, lambda p, q: y1, 1)]
    for dentro, corte, eje in lados:
        res = []
        for k, q in enumerate(pts):
            p = pts[k - 1]
            if dentro(q):
                if not dentro(p):
                    res.append(cruce(p, q, corte(p, q), eje))
                res.append(q)
            elif dentro(p):
                res.append(cruce(p, q, corte(p, q), eje))
        pts = res
        if not pts:
            break
    return pts


def cruce(p, q, v, eje):
    f = (v - p[eje]) / (q[eje] - p[eje])
    r = [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f]
    r[eje] = v
    return r


def zonas(proj, dx, dy, bbox):
    x0, y0, x1, y1 = bbox
    (lo0, la0), (lo1, la1) = proj(x0 - dx, y0 - dy, inverse=True), proj(x1 - dx, y1 - dy, inverse=True)
    q = (f'[out:json][timeout:180];(rel["boundary"="administrative"]["admin_level"="8"]["name"~"^Zona [0-9]+$"]'
         f'({la0},{lo0},{la1},{lo1});rel["boundary"="administrative"]["name"="Mixco"]({la0},{lo0},{la1},{lo1}););out geom;')
    datos = json.loads(bajar(OVERPASS, urllib.parse.urlencode({"data": q}).encode()))
    res = []
    for r in datos["elements"]:
        trazos = [[(p["lon"], p["lat"]) for p in m["geometry"]]
                  for m in r["members"] if m["type"] == "way" and m.get("role") in ("outer", "") and "geometry" in m]
        anillos = []
        for a in unir(trazos):
            x, y = proj([p[0] for p in a], [p[1] for p in a])
            pts = recortar([[xi + dx, yi + dy] for xi, yi in zip(x, y)], bbox)
            if len(pts) > 2:
                anillos.append(pts)
        if not anillos:
            continue
        # centro: centroide por área del anillo más grande
        a = max(anillos, key=lambda p: abs(area(p)))
        sa = area(a)
        cx = sum((a[k - 1][0] + a[k][0]) * (a[k - 1][0] * a[k][1] - a[k][0] * a[k - 1][1]) for k in range(len(a))) / (6 * sa)
        cy = sum((a[k - 1][1] + a[k][1]) * (a[k - 1][0] * a[k][1] - a[k][0] * a[k - 1][1]) for k in range(len(a))) / (6 * sa)
        res.append({"n": r["tags"]["name"], "anillos": [[round(v, 1) for p in a for v in p] for a in anillos],
                    "centro": [round(cx, 1), round(cy, 1)]})
    res.sort(key=lambda z: (z["n"] == "Mixco", int(z["n"].split()[-1]) if z["n"] != "Mixco" else 0))
    return res


def area(a):
    return sum(a[k - 1][0] * a[k][1] - a[k][0] * a[k - 1][1] for k in range(len(a))) / 2


def main():
    proj, dx, dy, bbox = ubicacion()
    dest = rutas.VIZ / "data"
    dest.mkdir(parents=True, exist_ok=True)
    z, base, filas, cols = terreno(proj, dx, dy, bbox)
    (dest / "terreno.bin").write_bytes(z.tobytes())
    print(f"terreno {filas}x{cols}, {base:.0f}–{base + z.max() / 10:.0f} m")
    eds = edificios(proj, dx, dy, bbox)
    print(f"edificios {len(eds)}")
    zs = zonas(proj, dx, dy, bbox)
    print("zonas", ", ".join(z["n"] for z in zs))
    meta = {"terreno": {"filas": filas, "cols": cols, "paso_m": PASO_M, "base_m": base, "x0": bbox[0], "y0": bbox[1]},
            "edificios": eds,
            "zonas": zs,
            "atribucion": "Relieve: AWS Terrain Tiles (SRTM, NASA). Edificios y calles: © OpenStreetMap contributors"}
    (dest / "escena.json").write_text(json.dumps(meta, separators=(",", ":")))


if __name__ == "__main__":
    main()
