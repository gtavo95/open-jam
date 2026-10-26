# open-jam: tráfico de Ciudad de Guatemala

Simulación en SUMO de la hora pico de la mañana (salidas de 6 a 7 h, 90 min simulados) en el área ampliada alrededor de la zona 10 (zonas 1, 4, 5, 9, 10, 13, 14, 15, Roosevelt hasta Mixco, Periférico y Belice), con un visor 3D en el navegador. El objetivo es probar si un agente que enciende o apaga los semáforos de cada corredor cada 15 minutos administra mejor el tráfico que la configuración actual.

La red se atasca, como la ciudad real en hora pico. Lo que se elimina son los artefactos: calles que faltan, rampas falsas, rutas fijas desde la salida y conductores demasiado corteses.

## Uso

Hace falta [uv](https://docs.astral.sh/uv/), [just](https://just.systems/) y, para el visor, pnpm.

```sh
uv sync
just todo        # red, corredores, demanda, escena y export de on/off (~1 h)
just web         # visor en http://localhost:5173
just test        # ruff, pytest (red de juguete) y lint/check/tests del visor
```

Pasos sueltos (`just --list`):

| receta | qué hace |
|---|---|
| `just red` | descarga el OSM si falta (`scripts/bajar_osm.sh`) y lo convierte en `sim/area.net.xml` |
| `just corredores` | `data/corredores.json`: un corredor por estación de conteo, con sus tramos y semáforos |
| `just demanda` | rutas calibradas con los conteos (routeSampler), tipos de conductor, landmarks del A* y semáforos Webster |
| `just escena` | relieve, edificios y zonas para el visor |
| `just exportar on off agente` | simula cada política y escribe los datos del visor en `viz/data/` |
| `just correr off --meso` | una política, con métricas en la terminal |
| `just bench --lista` | benchmarks de rendimiento |
| `just deploy` | datos a R2 y visor a Cloudflare Pages (configuración en `scripts/deploy.sh`) |

Extensión en Rust (opcional; comprime las trayectorias que se exportan):

```sh
uv run maturin develop -r -m rust/trayectos/Cargo.toml
```

## Simulación

- **Demanda**: 100 % del TPDA de hora pico por corredor (`open_jam/demanda.py` documenta datos y supuestos), con los destinos en colegios, universidades y oficinas de OSM.
- **Rutas como Waze**: la mitad de los conductores recalcula su ruta cada 5 min con el tráfico de los últimos 3 min. Usa A* con 16 landmarks (`sim/landmarks.txt`), que es 5 veces más rápido que el A* simple con el mismo resultado.
- **Conductores**: menos distancia al de adelante, más impaciencia y cambios de carril agresivos; las motos se meten en huecos más chicos (`VTYPES` en `open_jam/demanda.py`).
- **Atascos**: un vehículo trabado 10 min se teletransporta (`teleport` en `open_jam/config.py`). El visor no lo dibuja cruzando manzanas: corta la trayectoria en dos tramos.
- **Puntos de control**: `just exportar` guarda el estado cada 15 min simulados (`--control`) en `out/<escenario>.control/`. Si la corrida se corta, al relanzarla con la misma configuración retoma desde el último punto. Para pausar sin cortar: `pkill -STOP -f "bin/sumo -n"` y después `pkill -CONT -f "bin/sumo -n"`.
- **Meso**: `--meso` corre en ~15 s lo que micro hace en ~5 min. Está calibrado contra micro y da el mismo orden entre políticas. Sirve para explorar políticas en paralelo; lo que salga bien se confirma en micro.

## Agente

Una política (`open_jam/politicas.py`) recibe cada `cada` segundos una observación serializable a JSON (fluidez y tiempo parado por corredor) y devuelve `{corredor: bool}`. Un semáforo compartido entre corredores queda encendido si alguno de sus corredores lo está. Los semáforos fuera de los corredores siguen con `resto`. `Agente` es un ejemplo con umbral, sin LLM.

## Módulos

| módulo | qué hace |
|---|---|
| `open_jam/config.py` | `Corrida`: red, rutas, horizonte, política y opciones de SUMO |
| `open_jam/sim.py` | arranca SUMO y le da el control a la política en cada periodo |
| `open_jam/politicas.py` | on, off, `Agente`, validación de decisiones y `aplicar()` |
| `open_jam/corredores.py` | corredores del agente: generación, carga y validación contra la red |
| `open_jam/fluidez.py` | fluidez y tiempo parado por corredor y periodo |
| `open_jam/malla.py` | la red como malla de semáforos: matrices de incidencia y vecinos, y estado de cada tramo en vivo |
| `open_jam/tiempos.py` | verdes de cada semáforo: leerlos y cambiarlos sin saltarse amarillos |
| `open_jam/metricas.py` | lee las estadísticas de SUMO |
| `open_jam/demanda.py` | demanda de hora pico, conductores y landmarks |
| `open_jam/escena.py` | relieve (AWS Terrain Tiles), edificios y zonas (OSM) para el visor |
| `open_jam/export.py` | trayectorias por ventanas de 15 min en binario, red y manifest |
| `open_jam/trayectos.py` | simplificación de trayectorias (Python, o Rust si está compilado) |
| `open_jam/bench.py` | benchmarks: cada variante en su proceso |
| `open_jam/ab.py` | A/B de controladores: el mismo tramo, desde el mismo estado, con Webster y con el agente |

## Visor (`web/`)

Svelte 5 y Three.js. Lee `manifest.json`, la red, la escena y las ventanas de cada escenario desde `VITE_DATA_URL` (por defecto `/data/`, que en desarrollo sirve `viz/data/`; otra carpeta con `DATOS_DIR` o `?datos=`). Las ventanas se decodifican en un worker y, con `VITE_VERIFICAR_SHA256`, se verifica su hash. `pnpm fixture` arma un escenario mínimo para los tests.

## Licencias de datos

El código está bajo la licencia MIT (`LICENSE`). Los datos de terceros tienen sus propias licencias:

- **`data/osm/`**: datos de [OpenStreetMap](https://www.openstreetmap.org/copyright), © colaboradores de OpenStreetMap, disponibles bajo la [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Los dos se descargan de Overpass: `area.osm.xml` es el extracto del área (`scripts/bajar_osm.sh`) y `polos.json`, los lugares que atraen viajes en la mañana (colegios, universidades, hospitales, oficinas y comercios; `polos()` en `open_jam/demanda.py`). Las bases de datos derivadas de ellos (la red de SUMO y `data/corredores.json`) se distribuyen bajo la misma licencia, y el visor muestra la atribución a OpenStreetMap.
- **Relieve**: AWS Terrain Tiles (SRTM y otras fuentes).
