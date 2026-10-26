"""Genera la demanda de la hora pico de la mañana (6–7 h) para zonas 4, 9, 10, 13, 14 y
15, con las entradas grandes del occidente (Roosevelt, San Cristóbal, Periférico, El
Naranjo) y del norte (Calle Martí, Puente Belice, zona 18).

Los únicos datos reales son volúmenes diarios por corredor (TPDA, MuniGuate 2023,
revista ANADIE dic-2024 p. 6). Se convierten a hora pico y por sentido, y
routeSampler elige rutas que reproduzcan esos volúmenes. Las calles internas se
llenan con tráfico de fondo sin calibrar. Los destinos se reparten según colegios, universidades,
oficinas, hospitales y centros comerciales de OSM, para que los viajes terminen donde
la gente va en la mañana y no solo crucen la ciudad.

Uso: uv run python -m open_jam.demanda [--scale 1.0] [--seed 42]
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import sumo
import sumolib

from . import equilibrio
from .rutas import DATA, LANDMARKS, NET, OUT, SIM

TOOLS = Path(sumo.SUMO_HOME) / "tools"
POLOS = DATA / "osm" / "polos.json"

# Estaciones de conteo: volumen diario (veh/día, ambos sentidos), MuniGuate 2023,
# trafico2.pdf p. 6. La ubicación (lat, lon) es aproximada, leída del mapa de esa página;
# las que caen fuera del área (zona 12, zona 16) se movieron al tramo más cercano dentro.
ESTACIONES = [
    # (etiqueta, calle en OSM, lat, lon, veh/día)
    ("Reforma", "Avenida Reforma", 14.6000, -90.5155, 73_300),
    ("Liberación", "Boulevard Liberación", 14.6040, -90.5245, 138_300),
    ("Diagonal 6", "Diagonal 6", 14.5940, -90.5060, 56_700),
    ("Vista Hermosa", "Boulevard Vista Hermosa", 14.5960, -90.4950, 88_600),
    ("Vista Hermosa (zona 15)", "Boulevard Vista Hermosa", 14.5850, -90.4820, 93_400),
    ("Rafael Landívar", "Boulevard Rafael Landívar", 14.6005, -90.4865, 101_300),
    ("Las Américas", "Avenida Las Américas", 14.5800, -90.5200, 116_900),
    ("Bolívar", "Avenida Bolívar", 14.6200, -90.5230, 52_100),
    ("Petapa", "Avenida Petapa", 14.6027, -90.5404, 21_000),
    ("Atanasio Tzul", "Calzada Atanasio Tzul", 14.5935, -90.5408, 88_800),
    ("Aguilar Batres", "Calzada Raúl Aguilar Batres", 14.6080, -90.5414, 77_600),
    ("Carretera a El Salvador", "Carretera a El Salvador", 14.5850, -90.4700, 76_000),
    ("Los Próceres", "Boulevard Los Próceres", 14.5799, -90.4838, 72_800),
    ("Muxbal", "Carretera a Muxbal", 14.5650, -90.4750, 45_600),
    ("Hincapié", "Avenida Hincapié", 14.5649, -90.5287, 54_000),
    # entradas del occidente (Mixco, 30% de lo que entra a la ciudad) y del norte (zona 18)
    ("Roosevelt", "Calzada Roosevelt", 14.6220, -90.5500, 134_900),
    ("Roosevelt (Mixco)", "Calzada Roosevelt", 14.6300, -90.5900, 116_550),
    ("San Cristóbal", "Bulevar San Cristóbal", 14.6050, -90.5900, 78_900),
    ("Periférico", "Anillo Periférico", 14.6280, -90.5560, 118_200),
    ("Periférico norte", "Anillo Periférico", 14.6450, -90.5250, 128_400),
    ("Periférico sur", "Anillo Periférico", 14.6000, -90.5550, 87_400),
    ("El Naranjo", "Bulevar El Naranjo", 14.6550, -90.5500, 102_350),
    ("Calle Martí", "Calle Martí", 14.6515, -90.5080, 75_200),
    ("José Milla", "Calzada José Milla y Vidaurre", 14.6500, -90.4950, 48_600),
    ("Puente Belice", "Ruta al Atlántico", 14.6492, -90.4865, 95_900),
    ("Atlántico (zona 18)", "Ruta al Atlántico", 14.6520, -90.4620, 36_300),
    # Par de avenidas de la zona 1 (6a hacia el sur, 7a hacia el norte). Entre 18 y 8a calle
    # la 6a es peatonal (Paseo de la Sexta) y no está en la red: su estación va al tramo
    # vehicular más cercano, al sur del paseo (OSM, data/osm/area.osm.xml).
    ("6a Avenida", "6a Avenida", 14.6275, -90.5159, 57_100),
    ("7a Avenida", "7a Avenida", 14.6370, -90.5130, 56_400),
]
RADIO_M = 600  # distancia máxima entre la ubicación estimada y el tramo elegido
ANCHO_SECCION_M = 80  # calzadas paralelas (auxiliares) a menos de esto de la más cercana
# Lo que pasa por un carril en una hora con el semáforo y los cruces: SUMO da ~1770 en verde
# continuo con estos conductores (medido el 2026-10-17). Un conteo mayor es de toda la sección.
CAPACIDAD_CARRIL = 1500
# Variantes del nombre de una avenida en OSM que siguen siendo la misma vía.
PREFIJOS_MISMA_CALLE = ("", "carril auxiliar ", "paso a desnivel ")


def misma_calle(calle: str, nombre: str) -> bool:
    """¿El tramo llamado `nombre` es parte de la avenida `calle` de una estación?

    Nombre igual, o su carril auxiliar o paso a desnivel; "Bulevar" y "Boulevard" valen
    lo mismo (OSM usa los dos). No basta con contener el nombre: "6a Avenida A" es otra
    calle y "Antigua Carretera a El Salvador" otra vía.
    """
    def norma(s):
        return " ".join(s.lower().replace("bulevar ", "boulevard ").split())
    calle, nombre = norma(calle), norma(nombre)
    return any(nombre == p + calle for p in PREFIJOS_MISMA_CALLE)

# Supuestos (no vienen de los PDFs).
FACTOR_HORA_PICO = 0.07  # fracción del TPDA que pasa en la hora pico
PARTE_ENTRANTE = 0.60  # en la mañana domina el sentido hacia el centro de empleo
CENTRO = (14.605, -90.515)  # lat, lon (zonas 4, 9 y 10: centro de empleo)
FONDO_VEH_H = 5000  # tráfico de fondo en calles internas, sin calibrar
# Atracción de viajes en la mañana: colegios, universidades, oficinas, hospitales y
# centros comerciales de OSM (data/osm/polos.json). Peso = llegadas relativas en hora
# pico por lugar (supuesto); cada lugar se reparte entre las calles más cercanas.
PESO_POLO = {"university": 1500, "hospital": 400, "mall": 300, "school": 250, "college": 250,
             "kindergarten": 60, "clinic": 60, "office": 40, "bld:university": 100, "bld:school": 100,
             "bld:hospital": 100, "bld:government": 100, "bld:office": 80, "bld:commercial": 60,
             "bld:retail": 40}
PESO_OTRO = 20
DIFUSO = 0.02  # destinos repartidos por metro de calle (casas, comercio pequeño)
DURACION = 3600
HILOS = os.cpu_count() or 1  # ruteo con duarouter y routeSampler en paralelo

# Mezcla vehicular. El parque nacional tiene 3.4 motos por automóvil (FUNDESA),
# pero en Zona 10 en hora pico domina el carro; pesados restringidos en hora pico.
# Conductores de Guatemala: menos distancia al de adelante, se meten en los huecos y no esperan
# a que un cruce sin semáforo quede libre. Los valores por defecto de SUMO son conductores muy corteses.
# tau no baja del paso de simulación (1 s): con tau 0.6–0.9 Krauss choca, 40k teleports en 13 min.
VTYPES = """\
    <vTypeDistribution id="mix">
        <vType id="carro" vClass="passenger" probability="0.70" minGap="1.5" tau="1.0" sigma="0.6" impatience="0.5"
               lcAssertive="1.5" lcSpeedGain="1.5" jmTimegapMinor="0.5" jmIgnoreKeepClearTime="5"/>
        <vType id="moto" vClass="motorcycle" probability="0.25" minGap="0.5" tau="1.0" sigma="0.6" impatience="0.8"
               lcAssertive="2" lcPushy="0.5" jmTimegapMinor="0.3" jmIgnoreKeepClearTime="2"/>
        <vType id="bus" vClass="bus" probability="0.03" minGap="2" impatience="0.3" lcAssertive="1.5"/>
        <vType id="camion" vClass="truck" probability="0.02" minGap="2" impatience="0.3"/>
    </vTypeDistribution>
"""


def landmarks(net, destino: Path, n: int = 16):
    """Puntos de referencia para A* (ALT): el tramo de auto más lejano del centro en cada uno de n sectores.

    Con ellos el reruteo calcula las rutas 5 veces más rápido (1031 s -> 204 s en 15 min de hora pico).
    """
    (x0, y0), (x1, y1) = net.getBBoxXY()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    mejor = {}
    for e in net.getEdges():
        if not e.allows("passenger"):
            continue
        x, y = e.getFromNode().getCoord()
        s = int((math.atan2(y - cy, x - cx) + math.pi) / (2 * math.pi) * n) % n
        d = math.hypot(x - cx, y - cy)
        if d > mejor.get(s, (0, None))[0]:
            mejor[s] = (d, e.getID())
    destino.write_text("".join(f"{e}\n" for _, e in mejor.values()))


def huella(cmd, archivos) -> str:
    """sha256 del comando y del contenido de los archivos de los que depende."""
    h = hashlib.sha256(" ".join(map(str, cmd)).encode())
    for a in sorted(archivos):
        h.update(a.read_bytes())
    return h.hexdigest()


def run(cmd, cwd=None):
    print("+", " ".join(str(c) for c in cmd[:3]), "...", end=" ", flush=True)
    t = time.monotonic()
    subprocess.run([str(c) for c in cmd], check=True, stdout=subprocess.DEVNULL, cwd=cwd)
    print(f"{time.monotonic() - t:.0f} s")


def sin_vtypes(rutas: Path):
    """duarouter copia los vType al archivo de rutas; ya vienen en vtypes.add.xml."""
    lineas = rutas.read_text().splitlines(keepends=True)
    rutas.write_text("".join(l for l in lineas if "<vType" not in l))


def webster(py, calibrado, fondo):
    """Ajusta los tiempos de cada semáforo a esta demanda (método de Webster). Sin esto
    SUMO usa ciclos genéricos y la red se traba aunque haya poca demanda."""
    run([py, TOOLS / "tlsCycleAdaptation.py", "-n", NET, "-r", f"{calibrado},{fondo}",
         "-o", SIM / "tls_webster.add.xml", "--min-cycle", 60, "--max-cycle", 150, "-p", "w"])


def sumo_bin(nombre: str) -> str:
    return str(Path(sumo.SUMO_HOME) / "bin" / nombre)


def puntos_de_conteo(net, scale):
    """Para cada estación elige el tramo más cercano de esa calle en cada sentido."""
    cx, cy = net.convertLonLat2XY(CENTRO[1], CENTRO[0])
    conteos = []
    for etiqueta, calle, lat, lon, tpda in ESTACIONES:
        px, py = net.convertLonLat2XY(lon, lat)
        edges = [e for e in net.getNeighboringEdges(px, py, RADIO_M)
                 if misma_calle(calle, e[0].getName()) and e[0].getLength() > 30]
        if not edges:
            print(f"! {etiqueta}: no hay tramo de '{calle}' a menos de {RADIO_M} m", file=sys.stderr)
            continue
        sentidos = {"entrante": [], "saliente": []}
        for e, d in edges:
            (x0, y0), (x1, y1) = e.getFromNode().getCoord(), e.getToNode().getCoord()
            hacia_centro = (x1 - x0) * (cx - x0) + (y1 - y0) * (cy - y0)
            sentidos["entrante" if hacia_centro > 0 else "saliente"].append((e, d))
        hora_pico = tpda * FACTOR_HORA_PICO * scale
        for sentido, cands in sentidos.items():
            if not cands:
                continue
            seccion = seccion_transversal(sorted(cands, key=lambda c: c[1]), (px, py))
            parte = PARTE_ENTRANTE if sentido == "entrante" else 1 - PARTE_ENTRANTE
            carriles = sum(e.getLaneNumber() for e, _ in seccion)
            total = round(hora_pico * parte)
            if total > carriles * CAPACIDAD_CARRIL:
                print(f"! {etiqueta} {sentido}: {total} veh/h no caben en {carriles} carriles; "
                      f"se cuentan {carriles * CAPACIDAD_CARRIL}", file=sys.stderr)
                total = carriles * CAPACIDAD_CARRIL
            for e, d in seccion:
                conteos.append((etiqueta, sentido, e.getID(), round(total * e.getLaneNumber() / carriles), round(d)))
    return conteos


def seccion_transversal(cands, punto):
    """Calzadas paralelas de la misma vía en un sentido (central y auxiliares) junto a la más cercana.

    El TPDA cuenta toda la sección; ponerlo entero en una sola calzada pide más de lo que
    cabe. Una calzada paralela corre en la misma dirección y su punto más cercano a la
    estación queda al lado del de la principal, no adelante o atrás (eso es el mismo flujo
    en serie).
    """
    def cercano(e):
        forma = e.getShape()
        return sumolib.geomhelper.positionAtShapeOffset(
            forma, sumolib.geomhelper.polygonOffsetWithMinimumDistanceToPoint(punto, forma))

    def rumbo(e):
        (x0, y0), (x1, y1) = e.getFromNode().getCoord(), e.getToNode().getCoord()
        return math.atan2(y1 - y0, x1 - x0)

    (e0, d0), elegidos = cands[0], [cands[0]]
    (x0, y0), r0 = cercano(e0), rumbo(e0)
    for e, d in cands[1:]:
        if d > d0 + ANCHO_SECCION_M:
            break
        giro = abs((rumbo(e) - r0 + math.pi) % (2 * math.pi) - math.pi)
        x, y = cercano(e)
        a_lo_largo = abs((x - x0) * math.cos(r0) + (y - y0) * math.sin(r0))
        al_lado = abs((y - y0) * math.cos(r0) - (x - x0) * math.sin(r0))
        nodos = {e.getFromNode(), e.getToNode()}
        if (giro < math.radians(30) and a_lo_largo < 30 and al_lado > 5
                and not any(nodos & {o.getFromNode(), o.getToNode()} for o, _ in elegidos)):
            elegidos.append((e, d))
    return elegidos


def polos():
    """Lugares que atraen viajes en la mañana, de OSM; se bajan una vez y se guardan."""
    if not POLOS.exists():
        from . import escena
        proj, dx, dy, (x0, y0, x1, y1) = escena.ubicacion()
        (lo0, la0), (lo1, la1) = proj(x0 - dx, y0 - dy, inverse=True), proj(x1 - dx, y1 - dy, inverse=True)
        b = f"{la0},{lo0},{la1},{lo1}"
        q = (f'[out:json][timeout:180];(nwr["amenity"~"^(school|college|university|kindergarten|hospital|clinic)$"]({b});'
             f'nwr["office"]({b});nwr["building"~"^(office|commercial|university|school|hospital|retail|government)$"]({b});'
             f'nwr["shop"="mall"]({b}););out tags center;')
        res = []
        for e in json.loads(escena.bajar(escena.OVERPASS, urllib.parse.urlencode({"data": q}).encode()))["elements"]:
            t, c = e.get("tags", {}), e.get("center", e)
            tipo = (t.get("amenity") or ("mall" if t.get("shop") == "mall" else None)
                    or ("office" if "office" in t else None) or "bld:" + t.get("building", ""))
            res.append([tipo, t.get("name", ""), round(c["lat"], 6), round(c["lon"], 6)])
        POLOS.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    return json.loads(POLOS.read_text())


def atraccion(net, destino):
    """Pesos de destino para randomTrips (<destino>.dst.xml): cada polo se reparte entre
    las 3 calles locales más cercanas (a menos de 300 m); las vías rápidas no son destino."""
    def local(e):
        return e.allows("passenger") and e.getType().removeprefix("highway.").removesuffix("_link") not in ("motorway", "trunk")
    peso = {e.getID(): e.getLength() * DIFUSO for e in net.getEdges() if local(e)}
    sueltos = 0
    for tipo, _, lat, lon in polos():
        x, y = net.convertLonLat2XY(lon, lat)
        cerca = sorted((d, e.getID()) for e, d in net.getNeighboringEdges(x, y, 300) if local(e))[:3]
        if not cerca:
            sueltos += 1
            continue
        for _, e in cerca:
            peso[e] += PESO_POLO.get(tipo, PESO_OTRO) / len(cerca)
    if sueltos:
        print(f"  {sueltos} polos sin calle a menos de 300 m")
    with open(f"{destino}.dst.xml", "w") as f:
        f.write('<edgedata>\n    <interval begin="0" end="3600">\n')
        for e, w in peso.items():
            f.write(f'        <edge id="{e}" value="{w:.1f}"/>\n')
        f.write("    </interval>\n</edgedata>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="multiplica toda la demanda")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rehacer", action="store_true", help="rehace las rutas candidatas aunque estén al día")
    args = ap.parse_args()

    net = sumolib.net.readNet(str(NET))
    conteos = puntos_de_conteo(net, args.scale)

    counts = SIM / "conteos_am.xml"
    with open(counts, "w") as f:
        f.write(f'<data>\n    <interval id="am" begin="0" end="{DURACION}">\n')
        f.writelines(f'        <edge id="{edge}" entered="{n}"/> <!-- {nombre}, {sentido} -->\n' for nombre, sentido, edge, n, _ in conteos)
        f.write("    </interval>\n</data>\n")
    for nombre, sentido, edge, n, d in conteos:
        print(f"  {nombre:25s} {sentido:9s} {n:5d} veh/h  a {d:3d} m  ({edge})")

    vtypes = SIM / "vtypes.add.xml"
    vtypes.write_text(f"<additional>\n{VTYPES}</additional>\n")
    landmarks(net, LANDMARKS)

    py = sys.executable
    pesos = SIM / "atraccion"
    atraccion(net, pesos)
    # Rutas candidatas: viajes que cruzan la red de borde a borde y viajes que entran por
    # un borde y terminan en las zonas de empleo (sin estos la zona 10 solo se atraviesa).
    cand = SIM / "candidatas.rou.xml"
    trabajo = SIM / "candidatas_trabajo.rou.xml"
    # Son el 80% del tiempo (23 de 28 min) y no dependen de los conteos ni de los conductores:
    # se rehacen solo si cambia la red, la semilla o la atracción (o con --rehacer).
    for rutas, extra, semilla in ((cand, [], args.seed), (trabajo, ["--weights-prefix", pesos], args.seed + 2)):
        cmd = [py, TOOLS / "randomTrips.py", "-n", NET, "-r", rutas, "-o", rutas.with_suffix(".trips.xml"),
               "-b", 0, "-e", DURACION, "-p", 0.05, "--fringe-factor", 20, "--min-distance", 800, *extra,
               "--validate", "--seed", semilla, "--threads", HILOS]
        clave = huella(cmd, [NET, *pesos.parent.glob(pesos.name + "*")])
        sello = rutas.with_suffix(".huella")
        if args.rehacer or not rutas.exists() or not sello.exists() or sello.read_text() != clave:
            run(cmd)
            sello.write_text(clave)
        else:
            print(f"= {rutas.name} (ya estaba, misma red y atracción)")
    # routeSampler elige rutas para que los volúmenes en los puntos de conteo coincidan.
    calibrado = SIM / "am_calibrado.rou.xml"
    muestrear = [py, TOOLS / "routeSampler.py", "-d", counts, "-o", calibrado,
                 "--prefix", "cal", "--attributes", 'type="mix" departLane="best" departSpeed="max"',
                 "--seed", args.seed, "--threads", HILOS]
    run([*muestrear, "-r", f"{cand},{trabajo}"])
    # Tráfico de fondo para las calles internas (sin calibrar).
    fondo = SIM / "am_fondo.rou.xml"
    run([py, TOOLS / "randomTrips.py", "-n", NET, "-r", fondo, "-o", SIM / "am_fondo.trips.xml",
         "-b", 0, "-e", DURACION, "-p", 3600 / (FONDO_VEH_H * args.scale), "--prefix", "bg", "--weights-prefix", pesos,
         "--trip-attributes", 'type="mix" departLane="best"', "--additional-files", vtypes, "--validate", "--seed", args.seed + 1, "--threads", HILOS])
    sin_vtypes(fondo)
    webster(py, calibrado, fondo)

    # Con los tiempos de hora pico (equilibrio en meso) se rutean otra vez las candidatas y el
    # fondo; routeSampler elige entre las rutas de flujo libre y las de hora pico.
    tiempos = equilibrio.pesos(NET, [calibrado, fondo], [vtypes, SIM / "tls_webster.add.xml"], OUT / "equilibrio",
                               TOOLS, LANDMARKS, py, HILOS, huella, run)
    hora_pico = []
    for rutas in (cand, trabajo, fondo):
        salida = rutas.with_name(rutas.name.replace(".rou.xml", "_pico.rou.xml"))
        run([sumo_bin("duarouter"), "-n", NET, "-r", rutas, "-a", vtypes, "--weight-files", tiempos,
             "-o", salida, "--routing-algorithm", "astar", "--routing-threads", HILOS, "--ignore-errors",
             "--no-step-log", "--write-costs", "false"])
        salida.with_suffix("").with_suffix(".rou.alt.xml").unlink(missing_ok=True)
        sin_vtypes(salida)
        hora_pico.append(salida)
    run([*muestrear, "-r", ",".join(map(str, [cand, trabajo, *hora_pico[:2]]))])
    hora_pico[2].replace(fondo)
    webster(py, calibrado, fondo)
    for p in SIM.glob("*.trips.xml"):
        os.remove(p)
    print(f"ok: {calibrado.name}, {fondo.name}, vtypes.add.xml, tls_webster.add.xml")


if __name__ == "__main__":
    main()
