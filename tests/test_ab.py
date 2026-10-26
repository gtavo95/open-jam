from open_jam import ab, rutas

SIN_TIEMPOS = ("pared_s",)


def sin_tiempos(f):
    return {k: v for k, v in f.items() if k not in SIN_TIEMPOS}


def test_mismo_estado_mismo_resultado(grilla):
    base = ab.BASE.con(net=grilla.net, adicionales=grilla.adicionales, rutas=grilla.rutas)
    caso = ab.Caso(seed=1, escala=1.0, t0=300, dur=300)
    filas = ab.correr(["webster", "presion"], [caso], base, paralelo=2, out=rutas.OUT)
    estado = ab.archivo_estado(base, caso, rutas.OUT)
    antes = estado.stat().st_mtime_ns

    otra = ab.correr(["webster"], [caso], base, out=rutas.OUT)
    assert estado.stat().st_mtime_ns == antes  # el estado se reusa, no se vuelve a simular hasta t0
    webster, presion = filas
    assert sin_tiempos(otra[0]) == sin_tiempos(webster)  # A/A: sin decisiones distintas, nada cambia
    assert webster["cambios"] == 0 and presion["cambios"] > 0
    assert webster["llegaron"] > 0 and webster["parado_h"] > 0

    r = ab.comparar(filas, "webster", "presion")
    assert set(r) == set(ab.METRICAS) and all(x["n"] == 1 for x in r.values())
    assert r["parado_h"]["media"] == round(presion["parado_h"] - webster["parado_h"], 2)
