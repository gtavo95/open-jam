"""Simulación de la hora pico de Ciudad de Guatemala en SUMO.

Módulos:
  rutas      dónde vive cada archivo
  config     `Corrida`: qué se corre y con qué opciones de SUMO
  sim        arranca SUMO (libsumo o TraCI), avanza y llama a la política
  politicas  `Politica` (on, off, el `Agente` de ejemplo) y cómo se aplica una decisión
  corredores los corredores del agente (data/corredores.json) y sus semáforos
  fluidez    tiempo parado por periodo, para la red y por corredor
  metricas   lee las estadísticas de una corrida
  demanda    arma rutas calibradas con los conteos (antes scripts/make_demand.py)
  export     datos para la visualización web (viz/data/, por ventanas de 15 min)
  escena     relieve, edificios y zonas para el visor 3D
  bench      benchmarks de rendimiento
"""
