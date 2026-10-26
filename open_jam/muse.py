"""Muse Spark (Meta Model API) como controlador de semáforos.

`Muse` es el cliente: una llamada a `POST /v1/responses` con salida estructurada
(`text.format` json_schema) y reintentos ante 429 y 5xx. Usa solo la biblioteca estándar.
La clave sale de `MODEL_API_KEY`; sin ella no se puede llamar, y el modelo se cambia con
`MUSE_MODEL` (por defecto `muse-spark-1.3-contributor`).

`ControladorMuse` es un `ab.Controlador`: cada `cada` segundos simulados le muestra al
modelo los `NODOS` semáforos más congestionados (sus verdes de Webster, los actuales y
los parados que entran y salen en cada fase) y el modelo devuelve verdes nuevos. Cada
respuesta pasa por `tiempos.validar`; un nodo con una respuesta inválida se ignora y
queda como estaba. Los semáforos que no se muestran no se tocan.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import certifi
import numpy as np

from . import tiempos
from .ab import MaxPresion

URL = "https://api.meta.ai/v1"
MODELO = "muse-spark-1.3-contributor"  # más barato; Meta puede usar el contenido para entrenar
NODOS = 25  # semáforos que se le muestran al modelo en cada decisión

INSTRUCCIONES = f"""Eres el controlador de semáforos de una red de tráfico en hora pico.
Recibes semáforos congestionados. De cada uno: "webster" (segundos de verde de cada fase en
el ciclo fijo), "actual" (los verdes vigentes) y, por fase, "entra" (vehículos parados en las
calles que tienen verde en esa fase) y "sale" (vehículos parados en las calles a las que
esas calles desembocan; si están llenas, dar más verde no ayuda).
Devuelve para cada semáforo los nuevos verdes, uno por fase y en el mismo orden, entre
{tiempos.VERDE_MIN_S:g} y {tiempos.VERDE_MAX_S:g} segundos. Da más verde a la fase con más cola
que puede descargar y menos a la que no tiene a nadie. Mantén la suma cerca de la de
"webster": solo cambias el reparto del ciclo, no su duración. Omite los semáforos que estén bien."""

ESQUEMA = {
    "type": "json_schema",
    "name": "verdes",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"nodos": {"type": "array", "items": {
            "type": "object",
            "properties": {"tls": {"type": "string"}, "verdes": {"type": "array", "items": {"type": "number"}}},
            "required": ["tls", "verdes"], "additionalProperties": False}}},
        "required": ["nodos"], "additionalProperties": False},
}


class ErrorMuse(RuntimeError):
    pass


def _http(url: str, cuerpo: dict, clave: str, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(cuerpo).encode(), {
        "Authorization": f"Bearer {clave}", "Content-Type": "application/json"})
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.load(r)


class Muse:
    """Cliente de la API de Meta. `post(url, cuerpo, clave, timeout)` se puede reemplazar (tests)."""

    def __init__(self, modelo: str | None = None, clave: str | None = None, esfuerzo: str = "low",
                 max_salida: int = 8000, reintentos: int = 3, timeout: float = 120,
                 post: Callable[..., dict] = _http):
        self.modelo = modelo or os.environ.get("MUSE_MODEL", MODELO)
        self.clave = clave or os.environ.get("MODEL_API_KEY", "")
        self.esfuerzo, self.max_salida = esfuerzo, max_salida
        self.reintentos, self.timeout, self.post = reintentos, timeout, post
        self.llamadas = self.tokens_in = self.tokens_out = 0

    def responder(self, instrucciones: str, entrada: str, formato: dict | None = None) -> str:
        """El texto de la respuesta. Con `formato` (text.format), es el JSON que cumple el esquema."""
        if not self.clave:
            raise ErrorMuse("falta MODEL_API_KEY")
        cuerpo: dict[str, Any] = {"model": self.modelo, "instructions": instrucciones, "input": entrada,
                                  "reasoning": {"effort": self.esfuerzo}, "max_output_tokens": self.max_salida,
                                  "store": False}
        if formato:
            cuerpo["text"] = {"format": formato}
        for intento in range(self.reintentos + 1):
            try:
                r = self.post(f"{URL}/responses", cuerpo, self.clave, self.timeout)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or intento == self.reintentos:
                    raise ErrorMuse(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if intento == self.reintentos:
                    raise ErrorMuse(f"sin conexión: {e}") from e
            time.sleep(2**intento)
        self.llamadas += 1
        uso = r.get("usage", {})
        self.tokens_in += uso.get("input_tokens", 0)
        self.tokens_out += uso.get("output_tokens", 0)
        if r.get("status") not in (None, "completed"):
            raise ErrorMuse(f"respuesta {r.get('status')}: {r.get('error') or r.get('incomplete_details')}")
        texto = "".join(c["text"] for o in r.get("output", []) if o.get("type") == "message"
                        for c in o["content"] if c.get("type") == "output_text")
        if not texto:
            raise ErrorMuse("la respuesta no trae texto")
        return texto


class ControladorMuse(MaxPresion):
    """Muse decide los verdes de los semáforos más congestionados (ver el docstring del módulo)."""

    nombre = "muse"

    def __init__(self, cada: float = 300, nodos: int = NODOS, muse: Muse | None = None):
        super().__init__(cada=cada)
        self.nodos, self.muse = nodos, muse or Muse()
        self.fallos = self.invalidos = 0
        self.ultimo_error = ""

    def estado(self, lectura) -> dict[str, Any]:
        """Los `nodos` semáforos con más parados en sus fases, en el formato que lee el modelo."""
        q = lectura.parados
        filas = []
        for tls, fases in self.fases.items():
            entra = [int(q[e].sum()) for e, _ in fases]
            if sum(entra):
                filas.append((sum(entra), tls, entra, [int(q[s].sum()) for _, s in fases]))
        filas.sort(reverse=True)
        return {"t": int(lectura.t), "semaforos": [
            {"tls": tls, "webster": self.webster[tls].tolist(), "actual": np.asarray(self.actual[tls]).tolist(),
             "fases": [{"entra": e, "sale": s} for e, s in zip(entra, sale, strict=True)]}
            for _, tls, entra, sale in filas[:self.nodos]]}

    def decidir(self, lectura) -> dict[str, list[float]]:
        estado = self.estado(lectura)
        if not estado["semaforos"]:
            return {}
        try:
            resp = json.loads(self.muse.responder(INSTRUCCIONES, json.dumps(estado), ESQUEMA))
        except (ErrorMuse, json.JSONDecodeError) as e:
            self.fallos += 1  # un fallo de red no corta la simulación: los semáforos siguen como estaban
            self.ultimo_error = str(e)
            return {}
        mostrados = {s["tls"] for s in estado["semaforos"]}
        res = {}
        for n in resp.get("nodos", []):
            tls = n.get("tls")
            try:
                if tls not in mostrados:
                    raise ValueError(f"semáforo que no se mostró: {tls!r}")
                verdes = n["verdes"]
                if len(verdes) != len(self.webster[tls]):
                    raise ValueError(f"{tls}: {len(verdes)} verdes, tiene {len(self.webster[tls])} fases")
                if not all(tiempos.VERDE_MIN_S <= v <= tiempos.VERDE_MAX_S for v in verdes):
                    raise ValueError(f"{tls}: verdes fuera de rango")
            except (ValueError, KeyError, TypeError):
                self.invalidos += 1
                continue
            res[tls] = [float(v) for v in verdes]
            self.actual[tls] = np.array(res[tls])
        return res

    def resumen(self) -> dict[str, Any]:
        m = self.muse
        return {"llamadas": m.llamadas, "tokens_in": m.tokens_in, "tokens_out": m.tokens_out,
                "fallos": self.fallos, "invalidos": self.invalidos, "modelo": m.modelo,
                **({"error": self.ultimo_error} if self.ultimo_error else {})}
