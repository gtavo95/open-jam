"""La red como malla: cada semáforo es un nodo y las calles entre semáforos, sus enlaces.

Matrices (scipy.sparse), con los nodos en el orden de `Malla.nodos` y los tramos (edges
de SUMO) en el de `Malla.tramos`:

  entra     nodos × tramos   1 si el tramo llega al semáforo (lo controla en la entrada)
  sale      nodos × tramos   1 si el tramo sale del semáforo
  B         entra - sale     incidencia: B @ x da, por nodo, lo que entra menos lo que sale
  llega     nodos × tramos   1 si desde el nodo i se llega al tramo k, que entra a otro
                             semáforo, sin cruzar ningún semáforo en el camino
  vecinos   nodos × nodos    1 si desde i se llega a j así (sale de i → ... → entra a j)

Un tramo que entra a un semáforo después de una confluencia es alcanzable desde varios
nodos: `Lectura.entre_nodos` le asigna su flujo entero a cada uno, así que para un nodo
con varios vecinos aguas arriba es una cota superior, no un reparto.

`Malla.leer(sumo)` lee el estado de cada tramo en el paso actual (libsumo o traci).
"""

from dataclasses import dataclass

import numpy as np
from scipy import sparse

ALCANCE_M = 2000  # hasta dónde se sigue la calle desde un semáforo buscando el siguiente


@dataclass(frozen=True)
class Lectura:
    """Estado de cada tramo en un paso, en el orden de `Malla.tramos`."""

    t: float
    vehiculos: np.ndarray  # en el tramo
    parados: np.ndarray  # a menos de 0.1 m/s: la cola
    velocidad: np.ndarray  # media de los que están, m/s
    largo: np.ndarray  # m

    @property
    def flujo(self) -> np.ndarray:
        """veh/s que pasan por el tramo: densidad (veh/m) × velocidad (m/s)."""
        return self.vehiculos * self.velocidad / self.largo


@dataclass(frozen=True)
class Malla:
    nodos: tuple[str, ...]  # ids de semáforo (tls)
    tramos: tuple[str, ...]  # ids de edge
    largo: np.ndarray
    entra: sparse.csr_array
    sale: sparse.csr_array
    llega: sparse.csr_array

    @property
    def B(self) -> sparse.csr_array:
        return self.entra - self.sale

    @property
    def vecinos(self) -> sparse.csr_array:
        a = (self.llega @ self.entra.T).astype(bool).astype(np.int8)
        a.setdiag(0)
        a.eliminate_zeros()
        return a

    @classmethod
    def desde_net(cls, net, alcance_m: float = ALCANCE_M) -> "Malla":
        """Arma la malla con sumolib, sin simular: semáforos, sus tramos y quién llega a quién."""
        entradas: dict[str, set] = {}
        salidas: dict[str, set] = {}
        for tls in net.getTrafficLights():
            entradas[tls.getID()] = {c[0].getEdge() for c in tls.getConnections()}
            salidas[tls.getID()] = {c[1].getEdge() for c in tls.getConnections()}
        entra_a: dict[str, set[str]] = {}  # tramo -> semáforos a los que entra
        for n, es in entradas.items():
            for e in es:
                entra_a.setdefault(e.getID(), set()).add(n)

        alcanzados = {n: _alcanzados(n, salidas[n], entra_a, alcance_m) for n in salidas}
        bordes = set().union(*entradas.values(), *salidas.values())
        tramos = tuple(sorted(e.getID() for e in bordes))
        idx = {t: k for k, t in enumerate(tramos)}
        nodos = tuple(sorted(entradas))
        largo = np.array([net.getEdge(t).getLength() for t in tramos])

        def matriz(pares):
            filas, cols = zip(*pares) if pares else ((), ())
            return sparse.csr_array((np.ones(len(filas), np.int8), (filas, cols)), shape=(len(nodos), len(tramos)))

        return cls(nodos, tramos, largo,
                   matriz([(i, idx[e.getID()]) for i, n in enumerate(nodos) for e in entradas[n]]),
                   matriz([(i, idx[e.getID()]) for i, n in enumerate(nodos) for e in salidas[n]]),
                   matriz([(i, idx[t]) for i, n in enumerate(nodos) for t in alcanzados[n]]))

    def leer(self, sumo) -> Lectura:
        e = sumo.edge
        return Lectura(
            t=sumo.simulation.getTime(),
            vehiculos=np.array([e.getLastStepVehicleNumber(t) for t in self.tramos], float),
            parados=np.array([e.getLastStepHaltingNumber(t) for t in self.tramos], float),
            velocidad=np.array([e.getLastStepMeanSpeed(t) for t in self.tramos]),
            largo=self.largo,
        )

    def por_nodo(self, x: np.ndarray) -> dict[str, np.ndarray]:
        """De un valor por tramo a lo que entra y sale de cada nodo: {"entra", "sale", "balance"}."""
        entra, sale = self.entra @ x, self.sale @ x
        return {"entra": entra, "sale": sale, "balance": entra - sale}

    def entre_nodos(self, x: np.ndarray) -> sparse.csr_array:
        """nodos × nodos: x de los tramos que llegan a j desde i (p. ej. el flujo de i a j)."""
        m = (self.llega @ sparse.diags_array(x) @ self.entra.T).tocsr()
        m.setdiag(0)
        m.eliminate_zeros()
        return m


def _alcanzados(nodo: str, salidas, entra_a: dict[str, set[str]], alcance_m: float) -> set[str]:
    """Tramos que entran a otro semáforo y a los que se llega desde las salidas de `nodo`
    siguiendo la calle (sin cruzar otro semáforo) a menos de `alcance_m`."""
    res: set[str] = set()
    vistos: set[str] = set()
    pila = [(e, 0.0) for e in salidas]
    while pila:
        e, d = pila.pop()
        if e.getID() in vistos:
            continue
        vistos.add(e.getID())
        otros = entra_a.get(e.getID(), set()) - {nodo}
        if otros:
            res.add(e.getID())
            continue
        if nodo in entra_a.get(e.getID(), ()):  # volvió al mismo semáforo
            continue
        d += e.getLength()
        if d < alcance_m:
            pila.extend((s, d) for s in e.getOutgoing())
    return res
