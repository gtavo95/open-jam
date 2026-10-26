<script>
  import { onMount } from "svelte";
  import { crearFuente } from "./datos/fuente.js";
  import { describir } from "./datos/errores.js";
  import { indiceVentana } from "./datos/ventanas.js";
  import * as escena3d from "./escena/index.js";
  import { colorZona } from "./escena/index.js";
  import * as vehiculos from "./vehiculos.js";
  import { apagados, estadoSemaforos, indicePeriodo, restoDe } from "./corredores.js";

  /** @typedef {import("./tipos.js").Escenario} Escenario */
  /** @typedef {import("./tipos.js").Red} Red */

  const VELOCIDADES = [1, 10, 30, 60, 120];
  const PUBLICAR_MS = 250; // el panel se refresca a 4 Hz; la escena, a la tasa de cuadros

  /** @type {HTMLCanvasElement} */
  let lienzo;
  /** @type {Record<number, HTMLElement>} etiquetas de zona: se mueven cada cuadro sin pasar por Svelte */
  const nodos = {};

  let cargando = $state("Cargando relieve y calles…");
  let esperando = $state(""); // ventana de trayectorias que todavía no llegó
  let error = $state("");
  /** @type {{ id: string, titulo: string }[]} */
  let escenarios = $state([]);
  let nombre = $state("");
  let T = $state(0); // copia de `tiempo` para el panel, a 4 Hz
  let jugando = $state(true);
  let velocidad = $state(30);
  let vivo = $state.raw({ enRed: 0, parados: 0, kmh: 0, porZona: null });
  /** @type {Escenario | null} */
  let meta = $state.raw(null);
  /** @type {Escenario | null} el otro escenario, para comparar */
  let rival = $state.raw(null);
  /** @type {Red | null} */
  let red = $state.raw(null);
  let escalaAutos = $state(3);
  let zonas = $state.raw([]);
  /** @type {number[]} índices en `zonas`; vacío = mapa sin señalamientos */
  let elegidas = $state([]);

  let fin = $derived(meta?.fin ?? 5400);

  // fuera del estado reactivo: lo que cambia cada cuadro
  let mundo, flota, fuente, cargador;
  let tiempo = 0;
  /** @type {Record<string, Promise<{ meta: Escenario, cargador: any }>>} */
  const cache = {};
  /** @type {Uint8Array | null} */
  let luces = null;
  let clavePeriodo = "";

  async function cambiar(id) {
    nombre = id;
    error = "";
    try {
      cache[id] ??= fuente.cargarEscenario(id);
      const e = await cache[id];
      if (nombre !== id) return; // otro clic mientras cargaba
      cargador = e.cargador;
      meta = e.meta;
      clavePeriodo = "";
      if (tiempo >= meta.fin) tiempo = T = 0;
      cargarRival(id);
    } catch (e) {
      delete cache[id];
      if (nombre === id) error = describir(e, fuente.pista(id));
    }
  }

  // solo la meta del otro escenario: sus trayectorias no se piden hasta que se lo elige
  async function cargarRival(id) {
    const o = escenarios.find((e) => e.id !== id);
    rival = null;
    if (!o) return;
    try {
      cache[o.id] ??= fuente.cargarEscenario(o.id);
      const e = await cache[o.id];
      if (nombre === id) rival = e.meta;
    } catch {
      delete cache[o.id]; // sin comparación; el error se muestra si se lo elige
    }
  }

  // semáforos encendidos según las decisiones del periodo vigente (se recalcula al cambiar de periodo)
  function actualizarLuces(t) {
    const k = indicePeriodo(meta.periodos, t);
    const clave = `${meta.id}:${k}`;
    if (clave === clavePeriodo) return;
    clavePeriodo = clave;
    const p = meta.periodos[k];
    luces = estadoSemaforos(red.semaforos, red.corredores, p?.decisiones ?? {}, restoDe(p, meta.politica));
  }

  function moverEtiquetas() {
    for (const k of elegidas) {
      const el = nodos[k];
      if (!el) continue;
      const p = mundo.pantalla(...zonas[k].centro);
      el.style.visibility = p ? "visible" : "hidden";
      if (p) el.style.transform = `translate(${p[0]}px,${p[1]}px) translate(-50%,-100%)`;
    }
  }

  onMount(() => {
    let parar = false,
      prev = performance.now(),
      publicado = 0;
    fuente = crearFuente();
    (async () => {
      try {
        const m = await fuente.cargarManifest();
        const d = await fuente.cargarEscena();
        if (parar) return;
        mundo = escena3d.crear(lienzo, d);
        red = d.red;
        zonas = mundo.zonas;
        flota = vehiculos.crear(mundo.scene, mundo.altura, mundo.zonaDe, mundo.zonas.length);
        flota.escala = escalaAutos;
        escenarios = m.escenarios;
        cargando = "";
        await cambiar(m.escenarios[0].id);
      } catch (e) {
        error = describir(e, "Corré: uv run python -m open_jam.escena y uv run python -m open_jam.export on");
        cargando = "";
        return;
      }
      const cuadro = (ahora) => {
        if (parar) return;
        const dt = Math.min(0.1, (ahora - prev) / 1000);
        prev = ahora;
        let resumen = null;
        if (cargador && meta) {
          if (jugando) {
            const sig = tiempo + dt * velocidad >= meta.fin ? 0 : tiempo + dt * velocidad;
            // si la ventana siguiente no llegó, el reloj espera (y la pide)
            if (cargador.listo(sig)) tiempo = sig;
            else cargador.en(sig);
          }
          const r = cargador.en(tiempo);
          if (r.error && !error) error = describir(r.error, fuente.pista(meta.id));
          flota.usar(r.tray);
          resumen = flota.actualizar(tiempo);
          const v = meta.ventanas[r.i];
          const msg = r.tray || r.error ? "" : `Cargando trayectorias ${reloj(v.t0)}–${reloj(v.t1)}…`;
          if (msg !== esperando) esperando = msg;
          actualizarLuces(tiempo);
        }
        if (luces) mundo.semaforos.estado(luces, ahora / 1000);
        mundo.cuadro(dt, ahora / 1000);
        moverEtiquetas();
        if (ahora - publicado >= PUBLICAR_MS) {
          publicado = ahora;
          T = tiempo;
          if (resumen) {
            const z = resumen.porZona;
            vivo = { ...resumen, porZona: { n: z.n.slice(), parados: z.parados.slice(), kmh: z.kmh.slice() } };
          }
        }
        requestAnimationFrame(cuadro);
      };
      requestAnimationFrame(cuadro);
    })();
    return () => {
      parar = true;
      flota?.destruir();
      mundo?.destruir();
      fuente?.destruir();
    };
  });

  $effect(() => {
    if (flota) flota.escala = escalaAutos;
  });

  // Espacio: reproducir/pausar · 1, 2…: escenario (fuera de controles, que usan sus propias teclas)
  /** @param {KeyboardEvent} e */
  function tecla(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (/** @type {Element} */ (e.target).closest?.("input, select, textarea, button, summary")) return;
    if (e.key === " ") {
      e.preventDefault();
      jugando = !jugando;
    } else if (/^[1-9]$/.test(e.key) && escenarios[+e.key - 1]) cambiar(escenarios[+e.key - 1].id);
  }
  $effect(() => {
    const sel = new Set(elegidas); // se lee antes que `mundo` para que el efecto siga a `elegidas`
    mundo?.mostrarZonas(sel);
  });

  /** @param {Event & { currentTarget: HTMLInputElement }} e */
  function mover(e) {
    tiempo = T = +e.currentTarget.value;
  }

  // tamaño de la zona (diagonal de su caja), para elegir a qué distancia volar
  function diagonal(z) {
    let x0 = Infinity,
      y0 = Infinity,
      x1 = -Infinity,
      y1 = -Infinity;
    for (const a of z.anillos)
      for (let i = 0; i < a.length; i += 2) {
        x0 = Math.min(x0, a[i]);
        x1 = Math.max(x1, a[i]);
        y0 = Math.min(y0, a[i + 1]);
        y1 = Math.max(y1, a[i + 1]);
      }
    return Math.hypot(x1 - x0, y1 - y0);
  }
  function alternar(k) {
    if (elegidas.includes(k)) {
      elegidas = elegidas.filter((e) => e !== k);
      return;
    }
    elegidas = [...elegidas, k];
    const z = zonas[k];
    mundo.volar(z.centro[0], z.centro[1], Math.min(9000, Math.max(1400, diagonal(z) * 1.1)));
  }
  function todas() {
    elegidas = zonas.map((_, k) => k);
    mundo.volar(mundo.centro.x, -mundo.centro.z, 16000);
  }
  // resumen de los vehículos que están ahora en las zonas elegidas
  function enZonas(ks) {
    const pz = vivo.porZona;
    let n = 0,
      parados = 0,
      kmh = 0;
    if (pz)
      for (const k of ks) {
        n += pz.n[k + 1];
        parados += pz.parados[k + 1];
        kmh += pz.kmh[k + 1];
      }
    return { enRed: n, parados, kmh: n ? kmh / n : 0 };
  }
  let ahora = $derived(elegidas.length ? enZonas(elegidas) : vivo);

  const reloj = (s) => {
    const m = 6 * 60 + Math.floor(s / 60); // la simulación empieza a las 6:00
    return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
  };
  const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
  const num = (n) => Math.round(n).toLocaleString("es-GT");
  const corta = (t) => t.replace(/^Semáforos /, "");
  /**
   * diferencia contra el otro escenario; `subir` = si un número mayor es mejor
   * @returns {{ txt: string, mejor: boolean | null } | null}
   */
  function dif(a, b, subir, fmt = num) {
    if (a == null || b == null) return null;
    const d = a - b;
    const txt = fmt(Math.abs(d));
    if (txt === fmt(0)) return { txt: "igual", mejor: null };
    return { txt: `${d > 0 ? "+" : "−"}${txt}`, mejor: d > 0 === subir };
  }
  const puntos = (x) => `${Math.round(x * 100)} pts`;
  /** último punto de la curva con t <= T */
  function enCurva(c, t) {
    let p = null;
    for (const x of c) {
      if (x.t > t) break;
      p = x;
    }
    return p;
  }
  const corto = (n) => n.replace(/^(Avenida|Boulevard|Bulevar|Calzada|Carretera a) /, "");

  // decisiones del agente y fluidez medida, por periodo de 15 min (meta.periodos); si el export no
  // trae fluidez por periodo, se usa la de toda la corrida (metricas.corredores)
  let kPeriodo = $derived(meta ? indicePeriodo(meta.periodos, T) : -1);
  let decision = $derived(meta?.periodos[kPeriodo]);
  let cortados = $derived(decision && red ? apagados(red.corredores, decision.decisiones) : []);
  let nombresCortados = $derived(new Set(cortados.flatMap((c) => [c.id, c.nombre])));
  let semaforosOn = $derived.by(() => {
    if (!decision || !red) return null;
    const e = estadoSemaforos(red.semaforos, red.corredores, decision.decisiones, restoDe(decision, meta.politica));
    return e.reduce((s, x) => s + x, 0);
  });
  /** @param {Escenario | null} m */
  function fluidezDe(m, k) {
    const p = m?.periodos[k];
    if (p?.corredores) return { porPeriodo: true, red: p.red, corredores: p.corredores };
    if (m?.metricas?.corredores)
      return {
        porPeriodo: false,
        red: { fluidez: m.metricas.fluidez, parado_h: m.metricas.parado_h },
        corredores: m.metricas.corredores,
      };
    return null;
  }
  let fluidez = $derived(fluidezDe(meta, kPeriodo));
  let fluidezRival = $derived(fluidezDe(rival, kPeriodo));
  let corredores = $derived(
    fluidez
      ? Object.entries(fluidez.corredores)
          .filter(([, v]) => v.fluidez != null)
          .map(([k, v]) => ({
            id: k,
            nombre: red?.corredores.find((c) => c.id === k)?.nombre ?? k,
            f: v.fluidez,
            apagado: nombresCortados.has(k),
            d: dif(v.fluidez, fluidezRival?.corredores[k]?.fluidez, true, puntos),
          }))
          .sort((a, b) => a.f - b.f)
      : [],
  );
  const PEORES = 6;

  let m = $derived(meta?.metricas);
  let mr = $derived(rival?.metricas);
  let resultado = $derived(
    m && {
      llegaron: dif(m.llegaron, mr?.llegaron, true),
      demora: dif(m.demora_prom_s / 60, mr && mr.demora_prom_s / 60, false, (x) => `${Math.round(x)} min`),
      fluidez: dif(m.fluidez, mr?.fluidez, true, puntos),
    },
  );
  let ahoraRival = $derived(!elegidas.length && rival ? enCurva(rival.curva, T) : null);
  let curva = $derived(meta?.curva ?? []);
  let curvaRival = $derived(rival?.curva ?? []);
  let maxN = $derived(Math.max(1, ...curva.map((c) => c.n), ...curvaRival.map((c) => c.n)));
  const trazo = (c, f) => c.map((p) => `${(p.t / fin) * 1000},${40 - (f(p) / maxN) * 36}`).join(" ");
  let ventana = $derived(meta ? meta.ventanas[indiceVentana(meta.ventanas, T)] : null);
</script>

<svelte:window onkeydown={tecla} />

<main>
  <canvas bind:this={lienzo} aria-label="Mapa 3D de la ciudad con los vehículos de la simulación"></canvas>

  <header>
    <div class="marca">
      <span class="punto"></span>
      <strong>Tráfico GT</strong>
      <span class="sub">Hora pico de la mañana · Ciudad de Guatemala y entradas de Mixco y zona 18</span>
    </div>
    <nav aria-label="Escenario">
      {#each escenarios as e (e.id)}
        <button class:activo={nombre === e.id} aria-pressed={nombre === e.id} onclick={() => cambiar(e.id)}
          >{e.titulo}</button
        >
      {/each}
    </nav>
  </header>

  {#if zonas.length}
    <div class="zonas">
      <h2>Zonas</h2>
      <div class="acciones">
        <button class:activo={!elegidas.length} aria-pressed={!elegidas.length} onclick={() => (elegidas = [])}
          >Ninguna</button
        >
        <button
          class:activo={elegidas.length === zonas.length}
          aria-pressed={elegidas.length === zonas.length}
          onclick={todas}>Todas</button
        >
      </div>
      <div class="chips">
        {#each zonas as z, k (k)}
          <button
            class="chip"
            class:activo={elegidas.includes(k)}
            aria-pressed={elegidas.includes(k)}
            aria-label={z.n}
            style="--c:{colorZona(k)}"
            onclick={() => alternar(k)}
          >
            <i></i>{z.n.replace("Zona ", "")}
          </button>
        {/each}
      </div>
    </div>
  {/if}

  {#each elegidas as k (k)}
    {@const r = enZonas([k])}
    <div class="etiqueta" bind:this={nodos[k]} style="--c:{colorZona(k)}">
      <b>{zonas[k].n}</b>
      {#if elegidas.length <= 6}
        <small
          >{r.enRed.toLocaleString("es-GT")} veh ·
          <span class:alto={r.enRed && r.parados / r.enRed > 0.3}
            >{pct(r.enRed ? r.parados / r.enRed : 0)} detenidos</span
          ></small
        >
      {/if}
    </div>
  {/each}

  {#snippet delta(d)}
    {#if d && rival}
      <small class="dif" class:mejor={d.mejor === true} class:peor={d.mejor === false}
        >{d.txt} vs {corta(rival.titulo)}</small
      >
    {/if}
  {/snippet}

  <aside>
    {#if meta && m && resultado}
      <section class="resultado">
        <h2>Resultado de la corrida · {meta.titulo}</h2>
        <div class="duelo">
          <div>
            <span class="grande">{pct(m.llegaron / m.insertados)}</span>
            <small>llegaron a destino ({num(m.llegaron)} de {num(m.insertados)})</small>
            {@render delta(resultado.llegaron)}
          </div>
          <div>
            <span class="grande">{Math.round(m.demora_prom_s / 60)} min</span>
            <small>de demora promedio por viaje</small>
            {@render delta(resultado.demora)}
          </div>
        </div>
        <p class="nota">
          En movimiento el <b>{pct(m.fluidez)}</b> del tiempo{#if resultado.fluidez && rival}&nbsp;({resultado.fluidez
              .txt} vs {corta(rival.titulo)}){/if}.
        </p>
      </section>
    {/if}

    <section>
      <h2>
        Ahora · {reloj(T)}{elegidas.length === 1
          ? ` · ${zonas[elegidas[0]].n}`
          : elegidas.length
            ? ` · ${elegidas.length} zonas`
            : ""}
      </h2>
      <div class="kpis">
        <div>
          <span>{ahora.enRed.toLocaleString("es-GT")}</span><small
            >{elegidas.length ? "vehículos en la selección" : "vehículos en la red"}</small
          >
        </div>
        <div><span>{Math.round(ahora.kmh)}</span><small>km/h promedio</small></div>
        <div>
          <span class="rojo">{pct(ahora.enRed ? ahora.parados / ahora.enRed : 0)}</span><small>detenidos</small>
        </div>
      </div>
      {#if ahoraRival && rival}
        <p class="nota rival">
          Con {corta(rival.titulo)}: {num(ahoraRival.n)} en la red · {Math.round(ahoraRival.kmh)} km/h · {pct(
            ahoraRival.parados,
          )} detenidos
        </p>
      {/if}
    </section>

    {#if decision && red}
      <section>
        <h2>Semáforos · {reloj(decision.t0)}–{reloj(decision.t1 ?? decision.t0 + 900)}</h2>
        <p class="nota">
          <b>{semaforosOn?.toLocaleString("es-GT")}</b> de {red.semaforos.length.toLocaleString("es-GT")} encendidos.
          {#if !cortados.length}
            Ningún corredor apagado.
          {:else if cortados.length === red.corredores.length}
            Todos los corredores apagados.
          {:else}
            Corredores apagados:
          {/if}
        </p>
        {#if cortados.length && cortados.length < red.corredores.length}
          <ul class="cortados">
            {#each cortados as c (c.id)}<li>{corto(c.nombre)}</li>{/each}
          </ul>
        {/if}
      </section>
    {/if}

    <section>
      {#if fluidez}
        <h2>
          Fluidez por corredor · {fluidez.porPeriodo
            ? `${reloj(decision?.t0 ?? 0)}–${reloj(decision?.t1 ?? (decision?.t0 ?? 0) + 900)}`
            : "toda la corrida"}
        </h2>
        <p class="nota">
          Parte del tiempo que los vehículos pasan en movimiento. Red: <b>{pct(fluidez.red.fluidez)}</b>, {num(
            fluidez.red.parado_h,
          )} horas de vehículos detenidos.
        </p>
        {#snippet fila(c)}
          <li>
            <span class="nom" class:apagado={c.apagado} title={c.apagado ? `${c.nombre}: semáforos apagados` : c.nombre}
              >{corto(c.nombre)}</span
            >
            <span class="barra"><i style="width:{c.f * 100}%"></i></span>
            <span class="num">{pct(c.f)}</span>
            <span class="num dif" class:mejor={c.d?.mejor === true} class:peor={c.d?.mejor === false}
              >{c.d && c.d.mejor !== null ? c.d.txt.replace(" pts", "") : ""}</span
            >
          </li>
        {/snippet}
        <ul class="barras">
          {#each corredores.slice(0, PEORES) as c (c.id)}{@render fila(c)}{/each}
        </ul>
        {#if corredores.length > PEORES}
          <details>
            <summary>Los otros {corredores.length - PEORES} corredores</summary>
            <ul class="barras">
              {#each corredores.slice(PEORES) as c (c.id)}{@render fila(c)}{/each}
            </ul>
          </details>
        {/if}
        {#if rival}<p class="nota">La última columna compara con {corta(rival.titulo)}, en puntos de fluidez.</p>{/if}
      {:else if meta}
        <h2>Fluidez por corredor</h2>
        <p class="nota">Esta corrida no trae fluidez por corredor. Se genera con el export de métricas.</p>
      {/if}
    </section>

    <section>
      <div class="leyenda">
        <i style="background:var(--parado)"></i>detenido <i style="background:var(--lento)"></i>lento
        <i style="background:var(--fluido)"></i>fluido
      </div>
      <div class="leyenda">
        <svg viewBox="0 0 10 14" aria-hidden="true"
          ><path d="M5 6v8" /><circle cx="5" cy="4" r="3.2" fill="var(--luz-on)" /></svg
        >semáforo encendido
        <svg viewBox="0 0 10 14" aria-hidden="true"
          ><path d="M5 6v8" /><circle
            cx="5"
            cy="4"
            r="2.6"
            fill="none"
            stroke="var(--luz-off)"
            stroke-width="1.4"
          /></svg
        >apagado, parpadea
      </div>
      <details class="ajustes">
        <summary>Controles y detalles</summary>
        <p class="nota">
          Espacio: reproducir o pausar · 1 / 2: escenario · Flechas: mover · Shift + flechas: girar · + / −: acercar
        </p>
        <label>Tamaño de vehículos <input type="range" min="1" max="6" step="0.2" bind:value={escalaAutos} /></label>
        {#if m}
          <p class="nota">
            {num(m.teleports)} vehículos atascados se reubicaron en la red (teletransportes de SUMO).
          </p>
        {/if}
      </details>
    </section>
  </aside>

  <footer>
    <button class="play" onclick={() => (jugando = !jugando)} aria-label={jugando ? "Pausa" : "Reproducir"}>
      <svg viewBox="0 0 16 16" aria-hidden="true">
        {#if jugando}<rect x="3.5" y="3" width="3" height="10" rx="0.8" /><rect
            x="9.5"
            y="3"
            width="3"
            height="10"
            rx="0.8"
          />
        {:else}<path d="M4.5 2.8v10.4a.6.6 0 0 0 .9.5l8.2-5.2a.6.6 0 0 0 0-1L5.4 2.3a.6.6 0 0 0-.9.5z" />{/if}
      </svg>
    </button>
    <select bind:value={velocidad} aria-label="Velocidad">
      {#each VELOCIDADES as v (v)}<option value={v}>{v}×</option>{/each}
    </select>
    <div class="linea">
      <svg viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true">
        {#if ventana}
          <rect
            x={(ventana.t0 / fin) * 1000}
            width={((ventana.t1 - ventana.t0) / fin) * 1000}
            y="0"
            height="40"
            class="ventana"
          />
        {/if}
        {#each meta?.periodos ?? [] as p, i (i)}{#if p.t0 > 0}<line
              x1={(p.t0 / fin) * 1000}
              x2={(p.t0 / fin) * 1000}
              y1="0"
              y2="40"
              class="marca15"
            />{/if}{/each}
        <polyline class="curva red" points={trazo(curva, (c) => c.n)} />
        {#if curvaRival.length}<polyline
            class="curva fantasma"
            points={trazo(curvaRival, (c) => c.n * c.parados)}
          />{/if}
        <polyline class="curva parados" points={trazo(curva, (c) => c.n * c.parados)} />
      </svg>
      <input type="range" min="0" max={fin} step="1" value={T} oninput={mover} aria-label="Hora de la simulación" />
      <div class="horas">
        <span>6:00</span>
        <span class="claves">
          <span><i class="red"></i>en la red</span>
          <span><i class="parados"></i>detenidos</span>
          {#if rival}<span><i class="fantasma"></i>detenidos con {corta(rival.titulo)}</span>{/if}
        </span>
        <span>{reloj(fin)}</span>
      </div>
    </div>
    <span class="hora">{reloj(T)}</span>
  </footer>

  {#if cargando || error}
    <div class="velo" class:error><p>{error || cargando}</p></div>
  {:else if esperando}
    <p class="aviso" role="status">{esperando}</p>
  {/if}

  <p class="atrib">Relieve: AWS Terrain Tiles (SRTM) · Calles y edificios: © OpenStreetMap · Simulación: SUMO</p>
</main>

<style>
  :global(:root) {
    --fondo: #f3ece0;
    --panel: rgba(252, 248, 241, 0.92);
    --texto: #2a241c;
    --suave: #6b604f;
    --borde: rgba(60, 45, 25, 0.14);
    --acento: #2f8f86;
    --mejor: #23786f;
    --peor: #b8402a;
    /* mismos tonos que la escena: vehículos (vehiculos.js) y semáforos (escena/semaforos.js) */
    --parado: #e8452c;
    --lento: #e0a030;
    --fluido: #3cb8ab;
    --luz-on: #34c76f;
    --luz-off: #d98a00;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme="light"])) {
      --fondo: #15130f;
      --panel: rgba(28, 25, 20, 0.92);
      --texto: #efe7da;
      --suave: #b3a893;
      --borde: rgba(255, 240, 210, 0.12);
      --mejor: #5cc9bd;
      --peor: #ff7a5c;
      color-scheme: dark;
    }
  }
  :global(body) {
    margin: 0;
    background: var(--fondo);
    color: var(--texto);
    font:
      13px/1.45 Inter,
      system-ui,
      sans-serif;
    overflow: hidden;
    accent-color: var(--acento);
  }
  :global(::selection) {
    background: color-mix(in srgb, var(--acento) 30%, transparent);
  }
  :global(:focus-visible) {
    outline: 2px solid var(--acento);
    outline-offset: 2px;
  }
  main {
    position: fixed;
    inset: 0;
  }
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
  }
  header,
  aside,
  footer,
  .zonas {
    position: absolute;
    background: var(--panel);
    backdrop-filter: blur(14px);
    border: 1px solid var(--borde);
    border-radius: 12px;
    box-shadow: 0 8px 30px rgba(40, 25, 10, 0.12);
  }
  header {
    top: 14px;
    left: 14px;
    right: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 10px 8px 14px;
    flex-wrap: wrap;
  }
  .marca {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  .punto {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--acento);
    align-self: center;
  }
  .sub {
    color: var(--suave);
  }
  nav {
    display: flex;
    gap: 4px;
  }
  button,
  select,
  summary {
    font: inherit;
    color: var(--texto);
    background: transparent;
    border: 1px solid var(--borde);
    border-radius: 8px;
    padding: 6px 11px;
    cursor: pointer;
  }
  button:hover,
  select:hover {
    border-color: color-mix(in srgb, var(--texto) 35%, transparent);
  }
  button.activo {
    background: var(--texto);
    color: var(--fondo);
    border-color: var(--texto);
  }
  aside {
    top: 74px;
    right: 14px;
    width: 316px;
    max-height: calc(100% - 196px);
    overflow: auto;
    padding: 4px 16px;
    scrollbar-width: thin;
    scrollbar-color: var(--borde) transparent;
  }
  section {
    padding: 12px 0;
    border-bottom: 1px solid var(--borde);
  }
  section:last-child {
    border: 0;
  }
  h2 {
    font-size: 12px;
    color: var(--suave);
    margin: 0 0 8px;
    font-weight: 600;
  }
  .duelo {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 8px;
  }
  .duelo > div {
    display: grid;
    align-content: start;
    gap: 2px;
  }
  .grande {
    font:
      600 30px/1.1 Inter,
      system-ui,
      sans-serif;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
  }
  .duelo small,
  .kpis small,
  .nota {
    color: var(--suave);
    font-size: 12px;
  }
  .dif {
    font-size: 12px;
    font-weight: 600;
    color: var(--suave);
    font-variant-numeric: tabular-nums;
  }
  .dif.mejor {
    color: var(--mejor);
  }
  .dif.peor {
    color: var(--peor);
  }
  .kpis {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .kpis span {
    display: block;
    font:
      500 20px "JetBrains Mono",
      monospace;
  }
  .nota {
    margin: 0 0 8px;
  }
  .nota:last-child {
    margin-bottom: 0;
  }
  .rival {
    margin-top: 8px;
  }
  .rojo {
    color: var(--peor);
  }
  .barras {
    list-style: none;
    margin: 0 0 8px;
    padding: 0;
    display: grid;
    gap: 5px;
  }
  .barras li {
    display: grid;
    grid-template-columns: 100px 1fr 34px 30px;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .nom {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .barra {
    height: 6px;
    border-radius: 3px;
    background: var(--borde);
    overflow: hidden;
  }
  .barra i {
    display: block;
    height: 100%;
    border-radius: 3px;
    background: var(--acento);
  }
  .num {
    font-family: "JetBrains Mono", monospace;
    text-align: right;
    font-size: 12px;
  }
  details summary {
    border: 0;
    padding: 4px 0;
    color: var(--suave);
    font-size: 12px;
    list-style-position: inside;
  }
  details summary:hover {
    color: var(--texto);
  }
  details[open] summary {
    margin-bottom: 6px;
  }
  .ajustes {
    margin-top: 10px;
  }
  .ajustes label {
    display: grid;
    gap: 4px;
    margin-bottom: 8px;
    color: var(--suave);
    font-size: 12px;
  }
  .leyenda {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    color: var(--suave);
    font-size: 12px;
  }
  .leyenda + .leyenda {
    margin-top: 6px;
  }
  .leyenda i {
    width: 10px;
    height: 10px;
    border-radius: 3px;
    display: inline-block;
  }
  .leyenda svg {
    width: 10px;
    height: 14px;
    margin-left: 4px;
  }
  .leyenda svg:first-child {
    margin-left: 0;
  }
  .leyenda path {
    stroke: var(--suave);
    stroke-width: 1.4;
  }
  footer {
    left: 14px;
    right: 344px;
    bottom: 26px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
  }
  .play {
    width: 38px;
    height: 32px;
    padding: 0;
    display: grid;
    place-items: center;
  }
  .play svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }
  .linea {
    flex: 1;
    min-width: 0;
    position: relative;
  }
  .linea svg {
    width: 100%;
    height: 34px;
    display: block;
  }
  .curva {
    fill: none;
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
  }
  .curva.red {
    stroke: var(--acento);
  }
  .curva.parados {
    stroke: var(--parado);
  }
  .curva.fantasma {
    stroke: var(--suave);
    stroke-dasharray: 3 3;
    opacity: 0.8;
  }
  .marca15 {
    stroke: color-mix(in srgb, var(--texto) 22%, transparent);
    stroke-width: 1;
    stroke-dasharray: 2 3;
    vector-effect: non-scaling-stroke;
  }
  .linea input {
    width: 100%;
    margin: 2px 0 0;
  }
  .horas {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    color: var(--suave);
    font-size: 12px;
  }
  .claves {
    display: flex;
    gap: 12px;
    overflow: hidden;
    white-space: nowrap;
  }
  .claves i {
    display: inline-block;
    width: 14px;
    height: 0;
    margin-right: 5px;
    vertical-align: middle;
    border-top: 2px solid;
  }
  .claves .red {
    border-color: var(--acento);
  }
  .claves .parados {
    border-color: var(--parado);
  }
  .claves .fantasma {
    border-top-style: dashed;
    border-color: var(--suave);
  }
  .hora {
    font:
      500 18px "JetBrains Mono",
      monospace;
    min-width: 52px;
    text-align: right;
  }
  .velo {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: color-mix(in srgb, var(--fondo) 55%, transparent);
    pointer-events: none;
  }
  .velo p {
    max-width: min(560px, calc(100% - 32px));
    margin: 0;
    background: var(--panel);
    padding: 12px 18px;
    border-radius: 10px;
    border: 1px solid var(--borde);
  }
  .velo.error {
    pointer-events: auto;
  }
  .velo.error p {
    color: var(--peor);
    user-select: text;
  }
  .zonas {
    top: 74px;
    left: 14px;
    width: 214px;
    padding: 10px 12px 12px;
  }
  .acciones {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    margin-bottom: 8px;
  }
  .acciones button {
    padding: 5px 8px;
    font-size: 12px;
  }
  .chips {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
  }
  .chip {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 5px 0;
    font:
      500 12px "JetBrains Mono",
      monospace;
  }
  .chip i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--c);
    opacity: 0.55;
  }
  .chip.activo {
    background: color-mix(in srgb, var(--c) 22%, var(--panel));
    color: var(--texto);
    border-color: var(--c);
  }
  .chip.activo i {
    opacity: 1;
  }
  .etiqueta {
    position: absolute;
    left: 0;
    top: 0;
    visibility: hidden;
    pointer-events: none;
    display: grid;
    gap: 1px;
    text-align: center;
    padding: 5px 10px 6px;
    border-radius: 9px;
    background: var(--panel);
    backdrop-filter: blur(8px);
    border: 1px solid var(--c);
    box-shadow: 0 4px 18px rgba(30, 20, 10, 0.18);
    white-space: nowrap;
  }
  .etiqueta::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: -6px;
    width: 1px;
    height: 6px;
    background: var(--c);
  }
  .etiqueta b {
    font-size: 12.5px;
  }
  .etiqueta small {
    color: var(--suave);
    font-size: 12px;
  }
  .etiqueta .alto {
    color: var(--peor);
  }
  .cortados {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .cortados li {
    font-size: 12px;
    padding: 2px 7px;
    border-radius: 6px;
    border: 1px solid var(--luz-off);
    color: var(--texto);
    background: color-mix(in srgb, var(--luz-off) 14%, transparent);
  }
  .nom.apagado::after {
    content: "";
    display: inline-block;
    width: 5px;
    height: 5px;
    margin-left: 5px;
    border-radius: 50%;
    border: 1.4px solid var(--luz-off);
    vertical-align: 1px;
  }
  .ventana {
    fill: var(--acento);
    opacity: 0.08;
  }
  .aviso {
    position: absolute;
    left: 50%;
    top: 74px;
    transform: translateX(-50%);
    margin: 0;
    padding: 6px 12px;
    border-radius: 8px;
    background: var(--panel);
    border: 1px solid var(--borde);
    color: var(--suave);
    font-size: 12px;
    pointer-events: none;
  }
  .atrib {
    position: absolute;
    right: 16px;
    bottom: 6px;
    width: 316px;
    margin: 0;
    font-size: 10px;
    line-height: 1.3;
    text-align: right;
    color: var(--texto);
    opacity: 0.7;
    text-shadow: 0 0 3px var(--fondo);
  }
  @media (max-width: 760px) {
    header {
      left: 16px;
      right: 16px;
    }
    .sub {
      display: none;
    }
    aside {
      top: auto;
      bottom: 118px;
      left: 16px;
      right: 16px;
      width: auto;
      max-height: 34vh;
    }
    .zonas {
      left: 16px;
      right: 16px;
      width: auto;
      padding: 8px;
    }
    .zonas h2,
    .claves {
      display: none;
    }
    .chips {
      display: flex;
      overflow-x: auto;
    }
    .chip {
      flex: 0 0 auto;
      padding: 5px 9px;
    }
    .acciones {
      grid-template-columns: auto auto;
      justify-content: start;
    }
    footer {
      left: 16px;
      right: 16px;
      bottom: 24px;
    }
    .atrib {
      left: 16px;
      right: 16px;
      width: auto;
      bottom: 6px;
      text-align: left;
    }
  }
</style>
