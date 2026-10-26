# Práctica de algoritmos sobre la simulación

Ejercicios de estructuras de datos y algoritmos para preparar entrevistas técnicas (Google y similares), cada uno atado a una parte real de este repo. La idea es practicar un patrón dos veces: en el problema de LeetCode que lo enseña y en el código de la simulación, donde la respuesta se puede comparar con algo que ya funciona.

Esto complementa NeetCode 150, no lo reemplaza. En la entrevista los problemas son genéricos; aquí el patrón se fija porque se usa en algo propio.

## Reglas

- **Primero el problema de LeetCode**, después el ejercicio del repo.
- **Editor sin autocompletado ni IA.** En la entrevista no hay.
- **25 minutos por intento.** Si no sale, mirar la solución, entenderla y volver a escribirla de cero a los 2 o 3 días.
- **En voz alta y en inglés:** enfoque, código, complejidad en tiempo y espacio, un caso borde probado a mano.
- **Cada ejercicio con su test** contra la red de juguete (`grilla` en `tests/conftest.py`) y contra lo que el repo ya calcula.

## Estructura

```
practica/
  01_dijkstra.py
  02_astar_alt.py
  ...
tests/practica/
  test_01_dijkstra.py
  ...
```

Correr: `uv run pytest tests/practica -q`.

## Ejercicios

| # | Patrón | Problema LeetCode | Ejercicio en el repo | Cómo se verifica |
|---|---|---|---|---|
| 1 | Grafos, Dijkstra con heap | 743 Network Delay Time | Ruta más corta entre dos tramos de la red, dirigida. `corredores._distancias` es la versión sin sentido de los tramos. | Mismo largo que `net.getShortestPath` de sumolib en la grilla y en `sim/area.net.xml`. |
| 2 | A* y ALT (landmarks) | 1091 Shortest Path in Binary Matrix | A* con heurística euclidiana y después ALT con los 16 landmarks de `demanda.landmarks`, usando la desigualdad triangular. | Mismo largo que el ejercicio 1; contar nodos expandidos por cada variante y ver si sale el ~5x del README. |
| 3 | Componentes fuertemente conexas (Tarjan o Kosaraju) | 1192 Critical Connections | Tramos desde los que no se puede volver al resto de la red: callejones y rampas falsas. | La grilla es una sola componente; en el área real, revisar a mano los tramos que salgan. |
| 4 | Union-find | 684 Redundant Connection, 721 Accounts Merge | Agrupar corredores que comparten semáforos (en la grilla, los cuatro se cruzan). | Los grupos coinciden con lo que arma `corredores.con_semaforos`. |
| 5 | BFS multi-origen | 994 Rotting Oranges | Desde los tramos trabados de un periodo, cuántos cruces tarda el atasco en alcanzar cada corredor. | Comparar contra un BFS de un solo origen repetido por cada semilla. |
| 6 | Ventana deslizante, deque monotónica | 239 Sliding Window Maximum | Peor tiempo parado por corredor en los últimos 3 minutos, como la ventana que usa el reruteo. | Contra la versión ingenua que recorre la ventana entera en cada paso. |
| 7 | Heap, top-K | 347 Top K Frequent Elements | Los K corredores con menor fluidez en cada periodo, a partir de `Fluidez.ultimo()`. | Contra `sorted(...)[:K]`. |
| 8 | Merge de k listas ordenadas | 23 Merge k Sorted Lists | Unir las ventanas de 15 min de `export.py` en un solo flujo de puntos ordenado por tiempo. | Contra concatenar y ordenar todo. |
| 9 | Intervalos | 56 Merge Intervals | Intervalos parado de cada vehículo, y la trayectoria cortada en dos cuando hay teleport. | Suma de intervalos igual al tiempo parado que da `fluidez.py`. |
| 10 | Búsqueda binaria sobre la respuesta | 875 Koko Eating Bananas | El umbral de `Agente` que da mejor fluidez, corriendo en `--meso`. Primero comprobar si la fluidez es monótona en el umbral; si no lo es, explicar por qué la búsqueda binaria no sirve. | Contra un barrido de umbrales cada 0.05. |
| 11 | Programación dinámica | 198 House Robber, 309 Best Time to Buy and Sell Stock with Cooldown | Plan de encendido de un corredor en los 6 periodos de 15 min, con costo por cambiar de estado (estado × periodo). Aparte: Douglas-Peucker recursivo frente a la versión greedy de `trayectos.py`. | Contra fuerza bruta de los 2^6 planes; los puntos conservados frente a `simplificar_py`. |
| 12 | Backtracking con poda | 78 Subsets | Combinaciones on/off de los corredores, descartando una rama cuando su cota ya es peor que la mejor encontrada. | Contra probar todas las combinaciones en la grilla (2^4). |

## Orden sugerido

- **Semanas 1 a 4:** ejercicios 6, 7, 8, 9 y 10. Son arrays, heaps, intervalos y búsqueda binaria, con datos que ya salen de una corrida.
- **Semanas 5 a 7:** ejercicios 1 a 5. Son los de grafos, que es donde este repo más ayuda.
- **Semanas 8 a 10:** ejercicios 11 y 12, más problemas medios al azar con límite de 35 minutos y mock interviews.

## Bitácora

| Fecha | # | Minutos | ¿Salió solo? | Idea clave en una línea |
|---|---|---|---|---|
