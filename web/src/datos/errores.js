// @ts-check
// Errores de carga con causa explícita, para mostrarle al usuario qué falló de verdad.

/** @typedef {"red" | "http" | "faltante" | "formato" | "integridad"} TipoError */

export class ErrorDatos extends Error {
  /**
   * @param {TipoError} tipo
   * @param {string} mensaje
   * @param {string} [url]
   */
  constructor(tipo, mensaje, url) {
    super(mensaje);
    this.name = "ErrorDatos";
    this.tipo = tipo;
    this.url = url;
  }

  /** forma plana para cruzar el postMessage del worker */
  plano() {
    return { tipo: this.tipo, mensaje: this.message, url: this.url };
  }

  /** @param {{ tipo: TipoError, mensaje: string, url?: string }} p */
  static desde(p) {
    return new ErrorDatos(p.tipo, p.mensaje, p.url);
  }
}

/**
 * fetch que distingue sin conexión, 404 (o el index.html que devuelve Vite cuando el
 * archivo no existe) y otros códigos HTTP.
 * @param {string} url
 * @param {"json" | "binario"} como
 */
export async function pedir(url, como) {
  let r;
  try {
    r = await fetch(url);
  } catch (e) {
    throw new ErrorDatos("red", `No se pudo bajar ${url}: ${e instanceof Error ? e.message : e}`, url);
  }
  if (r.status === 404) throw new ErrorDatos("faltante", `${url} no existe (404)`, url);
  if (!r.ok) throw new ErrorDatos("http", `${url} respondió ${r.status} ${r.statusText}`.trim(), url);
  // el servidor de desarrollo responde index.html para archivos que no existen
  if ((r.headers.get("content-type") ?? "").includes("text/html"))
    throw new ErrorDatos("faltante", `${url} no existe (el servidor devolvió una página HTML)`, url);
  if (como === "binario") return r.arrayBuffer();
  const texto = await r.text();
  try {
    return JSON.parse(texto);
  } catch (e) {
    throw new ErrorDatos("formato", `${url} no es JSON válido: ${e instanceof Error ? e.message : e}`, url);
  }
}

/**
 * Texto para mostrar en pantalla.
 * @param {unknown} e
 * @param {string} [pista]  qué hacer si el archivo falta (p. ej. el comando de export)
 */
export function describir(e, pista) {
  if (e instanceof ErrorDatos) return e.tipo === "faltante" && pista ? `${e.message}. ${pista}` : e.message;
  return e instanceof Error ? `${e.name}: ${e.message}` : String(e);
}
