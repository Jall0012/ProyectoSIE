const porId = (id) => document.getElementById(id);
const numero = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3 });
const porcentaje = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });
const centroInicial = [37.78, -3.79];
const maxBytesTiff = 16 * 1024 * 1024;
const maxPixelesTiff = 16_000_000;

const elementosZona = {
  formulario: porId("form-zona"),
  latitud: porId("latitud"),
  longitud: porId("longitud"),
  radio: porId("radio"),
  deslizador: porId("radio-deslizador"),
  centrar: porId("centrar-mapa"),
  estado: porId("estado-zona"),
  detalle: porId("detalle-zona"),
};
const elementosImagen = {
  formulario: porId("form-imagen"),
  formularioZona: porId("form-zona-imagen"),
  enviarZona: porId("enviar-zona-imagen"),
  archivo: porId("archivo"),
  zonaArchivo: porId("zona-archivo"),
  nombre: porId("nombre-archivo"),
  enviar: porId("enviar-imagen"),
  lienzo: porId("lienzo"),
  texto: porId("texto-visor"),
  nota: porId("nota-vista"),
  estado: porId("estado-imagen"),
  detalle: porId("detalle-imagen"),
  origen: porId("origen-imagen"),
};

let mapa;
let marcador;
let circulo;
let solicitudZona;
let solicitudImagen;
let archivoActual;
let recorteAutomatico = false;
let seleccionImagen = 0;
let cargaGeoTiff;

function configurarPestanas() {
  const pestanas = [...document.querySelectorAll('[role="tab"]')];
  function activar(pestana) {
    for (const elemento of pestanas) {
      const activa = elemento === pestana;
      elemento.setAttribute("aria-selected", String(activa));
      elemento.tabIndex = activa ? 0 : -1;
      porId(elemento.getAttribute("aria-controls")).hidden = !activa;
    }
  }

  pestanas.forEach((pestana, indice) => {
    pestana.addEventListener("click", () => activar(pestana));
    pestana.addEventListener("keydown", (evento) => {
      const destinos = {
        ArrowLeft: (indice - 1 + pestanas.length) % pestanas.length,
        ArrowRight: (indice + 1) % pestanas.length,
        Home: 0,
        End: pestanas.length - 1,
      };
      const destino = pestanas[destinos[evento.key]];
      if (destino) {
        evento.preventDefault();
        activar(destino);
        destino.focus();
      }
    });
  });
}

function datosZona() {
  const { latitud, longitud, radio } = elementosZona;
  const valores = { latitud: latitud.valueAsNumber, longitud: longitud.valueAsNumber, radio_m: radio.valueAsNumber };
  return latitud.validity.valid && longitud.validity.valid && radio.validity.valid
    && Number.isFinite(valores.radio_m) && valores.radio_m > 0 ? valores : null;
}

function sincronizarMapa(recentrar = false, zoomDetalle = false) {
  const zona = datosZona();
  if (!zona || !mapa) return;
  const centro = [zona.latitud, zona.longitud];
  marcador.setLatLng(centro);
  circulo.setLatLng(centro).setRadius(zona.radio_m);
  if (zoomDetalle) mapa.setView(centro, Math.max(13, mapa.getZoom()));
  else if (recentrar) mapa.panTo(centro);
}

function indicarCentro(posicion) {
  const centro = posicion.wrap();
  elementosZona.latitud.value = centro.lat.toFixed(5);
  elementosZona.longitud.value = centro.lng.toFixed(5);
  actualizarZona();
}

function crearMapa() {
  if (!window.L) {
    porId("mapa").classList.add("mapa-no-disponible");
    porId("mapa").textContent = "No se pudo cargar el mapa.";
    porId("nota-mapa").textContent = "Introduce las coordenadas en el formulario.";
    elementosZona.centrar.disabled = true;
    return;
  }

  mapa = L.map("mapa", { zoomControl: false, maxZoom: 18, minZoom: 3 }).setView(centroInicial, 13);
  L.control.zoom({
    position: "bottomright", zoomInTitle: "Acercar", zoomOutTitle: "Alejar",
  }).addTo(mapa);
  L.control.scale({ imperial: false, position: "bottomleft" }).addTo(mapa);
  mapa.createPane("limite-provincial").style.zIndex = "395";

  const baseLocal = L.layerGroup().addTo(mapa);
  mapa.attributionControl.setPrefix(false);
  const atribucionLocal = '<a href="https://www.juntadeandalucia.es/datosabiertos/portal/dataset/datos-espaciales-de-referencia-andalucia-dera">IECA · DERA</a> · CapasUsadas.gpkg';
  baseLocal.on("add", () => mapa.attributionControl.addAttribution(atribucionLocal));
  baseLocal.on("remove", () => mapa.attributionControl.removeAttribution(atribucionLocal));
  mapa.attributionControl.addAttribution(atribucionLocal);

  const teselasIgn = "https://www.ign.es/wmts/ign-base?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile"
    + "&LAYER=IGNBaseTodo&STYLE=default&FORMAT=image/jpeg&TILEMATRIXSET=GoogleMapsCompatible"
    + "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
  const baseGeneral = L.tileLayer(teselasIgn, {
    attribution: 'Mapa Base de España · IGN <a href="https://www.scne.es/">CC BY 4.0 scne.es</a>',
  });
  const baseSatelital = L.tileLayer("https://tms-pnoa-ma.idee.es/1.0.0/pnoa-ma/{z}/{x}/{-y}.jpeg", {
    attribution: 'IGN · PNOA <a href="https://www.scne.es/">CC BY 4.0 scne.es</a> · Copernicus Sentinel-2',
    maxNativeZoom: 19,
  });
  const notaMapa = porId("nota-mapa");
  const indicacionesMapa = notaMapa.textContent;
  const errorLocal = "Cartografía local no disponible. Usa los campos de coordenadas o cambia de capa.";
  let falloCartografiaLocal = false;
  let avisoTeselas = false;
  for (const [capa, nombre] of [[baseGeneral, "el mapa general"], [baseSatelital, "la vista satelital"]]) {
    capa.on("tileerror", () => {
      if (avisoTeselas || !mapa.hasLayer(capa)) return;
      avisoTeselas = true;
      notaMapa.textContent = `No se pudo cargar ${nombre}. Puedes cambiar de capa o introducir las coordenadas.`;
    });
  }
  mapa.on("baselayerchange", (evento) => {
    avisoTeselas = false;
    notaMapa.textContent = evento.layer === baseLocal && falloCartografiaLocal ? errorLocal : indicacionesMapa;
  });
  L.control.layers({
    "Cartografía de Jaén": baseLocal,
    "Mapa general": baseGeneral,
    "Vista satelital": baseSatelital,
  }).addTo(mapa);
  cargarLimiteProvincial();

  const estilos = {
    curvas: { color: "#64735a", weight: 0.8, opacity: 0.35 },
    urbano: { color: "#626653", weight: 1, fillColor: "#5f6251", fillOpacity: 0.7 },
    vias: { color: "#78816e", weight: 0.85, opacity: 0.7 },
    principal: { color: "#aca27b", weight: 1.15, opacity: 0.77 },
  };
  let vistaModificada = false;
  const cambiosVista = "movestart click baselayerchange";
  const registrarCambioVista = () => { vistaModificada = true; };
  mapa.on(cambiosVista, registrarCambioVista);
  fetch("./mapa-jaen.geojson").then((respuesta) => {
    if (!respuesta.ok) throw new Error("Cartografía no disponible");
    return respuesta.json();
  }).then((datos) => {
    const cartografia = L.geoJSON(datos, { style: (elemento) => estilos[elemento.properties.capa], interactive: false });
    if (!vistaModificada) mapa.fitBounds(cartografia.getBounds(), { padding: [16, 16], animate: false });
    cartografia.addTo(baseLocal);
    const poblaciones = [
      [37.768, -3.79, "Jaén"], [38.038, -4.053, "Andújar"], [38.095, -3.636, "Linares"],
      [38.011, -3.37, "Úbeda"], [37.91, -3.0, "Cazorla"],
      [37.465, -3.924, "Alcalá la Real"], [38.298, -2.651, "Orcera"],
    ];
    for (const [lat, lon, nombre] of poblaciones) {
      L.tooltip({ permanent: true, direction: "center", className: "toponimo", interactive: false })
        .setLatLng([lat, lon]).setContent(nombre).addTo(baseLocal);
    }
    circulo.bringToFront();
  }).catch(() => {
    falloCartografiaLocal = true;
    if (mapa.hasLayer(baseLocal)) notaMapa.textContent = errorLocal;
  }).finally(() => {
    mapa.off(cambiosVista, registrarCambioVista);
  });

  const icono = L.divIcon({ className: "centro-mapa", iconSize: [14, 14] });
  marcador = L.marker(centroInicial, { draggable: true, icon: icono, title: "Centro de la zona" }).addTo(mapa);
  if (marcador.getElement()) marcador.getElement().setAttribute("aria-label", "Centro de la zona");
  circulo = L.circle(centroInicial, {
    radius: 250, color: "#ffce65", weight: 2, fillColor: "#f7cc72",
    fillOpacity: 0.32, interactive: false,
  }).addTo(mapa);

  mapa.on("click", (evento) => indicarCentro(evento.latlng));
  marcador.on("drag", () => indicarCentro(marcador.getLatLng()));
  elementosZona.centrar.addEventListener("click", () => sincronizarMapa(true, true));
}

async function cargarLimiteProvincial() {
  try {
    const respuesta = await fetch("./limites-jaen.geojson?v=mapa-04-limite");
    if (!respuesta.ok) throw new Error("Límite provincial no disponible");
    const datos = await respuesta.json();
    L.geoJSON(datos, {
      pane: "limite-provincial",
      interactive: false,
      attribution: 'Obra derivada de <a href="https://centrodedescargas.cnig.es/CentroDescargas/limites-municipales-provinciales-autonomicos">BDLJE · IGN</a> CC BY 4.0',
      filter: (elemento) => elemento.properties.capa === "provincia",
      style: { className: "limite-mapa", color: "var(--limite-mapa)", dashArray: "6 4", weight: 2, fill: false },
    }).addTo(mapa);
    porId("leyenda-mapa").hidden = false;
  } catch {
    porId("aviso-limite").hidden = false;
  }
}

function indicarEstado(elemento, mensaje = "", error = false) {
  elemento.textContent = mensaje;
  elemento.dataset.error = String(error);
}

function mensajeInicial(elemento, mensaje) {
  const parrafo = document.createElement("p");
  parrafo.textContent = mensaje;
  elemento.replaceChildren(parrafo);
}

function limpiarZona() {
  solicitudZona?.abort();
  solicitudZona = undefined;
  elementosZona.formulario.querySelector('button[type="submit"]').disabled = false;
  indicarEstado(elementosZona.estado);
  mensajeInicial(elementosZona.detalle, "El resultado de la evaluación aparecerá aquí.");
}

function actualizarZona() {
  limpiarZona();
  if (recorteAutomatico) limpiarImagen();
  sincronizarMapa();
}

function categoriaResultado(valor) {
  const titulo = document.createElement("div");
  titulo.className = "categoria";
  titulo.dataset.categoria = valor;
  titulo.textContent = valor;
  return titulo;
}

function metricaResultado(etiqueta, valor, texto) {
  const contenedor = document.createElement("div");
  const fila = document.createElement("div");
  fila.className = "metrica";
  const dato = document.createElement("strong");
  dato.textContent = texto;
  fila.append(etiqueta, dato);
  const barra = document.createElement("progress");
  barra.className = "barra-medida";
  barra.max = 1;
  barra.value = valor;
  barra.setAttribute("aria-label", etiqueta);
  barra.setAttribute("aria-valuetext", texto);
  contenedor.append(fila, barra);
  return contenedor;
}

async function pedirApi(ruta, opciones) {
  let respuesta;
  try {
    respuesta = await fetch(`/api/${ruta}`, opciones);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("No se pudo conectar con la API. Inténtalo de nuevo.");
  }
  if (respuesta.ok) return respuesta.json();

  if (respuesta.status === 413) throw new Error("El archivo supera el tamaño máximo admitido.");
  const datos = await respuesta.json().catch(() => null);
  const detalle = datos?.detail;
  if (respuesta.status >= 500 && (respuesta.status !== 503 || typeof detalle !== "string")) {
    throw new Error("El servicio no está disponible. Inténtalo de nuevo.");
  }
  const mensaje = typeof detalle === "string" ? detalle : "Revisa los datos del formulario.";
  throw new Error(mensaje);
}

function configurarZona() {
  const { latitud, longitud, radio, deslizador, formulario, estado, detalle } = elementosZona;
  porId("form-seleccion-zona").addEventListener("submit", (evento) => {
    evento.preventDefault();
    const modoDeterminista = porId("tab-zona").getAttribute("aria-selected") === "true";
    const destino = modoDeterminista ? formulario : elementosImagen.formularioZona;
    if (!destino.querySelector('button[type="submit"]').disabled) destino.requestSubmit();
  });
  for (const entrada of [latitud, longitud]) {
    entrada.addEventListener("input", actualizarZona);
    entrada.addEventListener("change", () => sincronizarMapa(true));
  }
  radio.addEventListener("input", () => {
    if (Number.isFinite(radio.valueAsNumber)) deslizador.value = radio.value;
    actualizarZona();
  });
  deslizador.addEventListener("input", () => {
    radio.value = deslizador.value;
    actualizarZona();
  });
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const zona = datosZona();
    if (!zona) {
      indicarEstado(estado, "Introduce coordenadas válidas y un radio mayor que cero.", true);
      return;
    }
    sincronizarMapa(true);
    limpiarZona();
    const solicitud = new AbortController();
    solicitudZona = solicitud;
    const enviar = formulario.querySelector('button[type="submit"]');
    enviar.disabled = true;
    indicarEstado(estado, "Evaluando zona…");
    try {
      const resultado = await pedirApi("evaluar-zona", {
        method: "POST", signal: solicitud.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(zona),
      });
      if (solicitudZona !== solicitud) return;
      detalle.replaceChildren(categoriaResultado(resultado.categoria));
      if (typeof resultado.puntuacion === "number") {
        const valor = numero.format(resultado.puntuacion);
        detalle.append(metricaResultado("Puntuación TOPSIS", resultado.puntuacion, `${valor} / 1`));
      } else {
        const mensaje = document.createElement("p");
        mensaje.textContent = "La zona no dispone de los datos necesarios para evaluarla.";
        detalle.append(mensaje);
      }
      indicarEstado(estado);
    } catch (error) {
      if (solicitudZona === solicitud) indicarEstado(estado, error.message, true);
    } finally {
      if (solicitudZona === solicitud) {
        solicitudZona = undefined;
        enviar.disabled = false;
      }
    }
  });
}

function obtenerGeoTiff() {
  if (!cargaGeoTiff) {
    cargaGeoTiff = new Promise((resolver, rechazar) => {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/geotiff@2.1.3/dist-browser/geotiff.js";
      script.onload = () => window.GeoTIFF ? resolver(window.GeoTIFF) : rechazar(new Error("GeoTIFF no disponible"));
      script.onerror = () => rechazar(new Error("GeoTIFF no disponible"));
      document.head.append(script);
    }).catch((error) => {
      cargaGeoTiff = undefined;
      throw error;
    });
  }
  return cargaGeoTiff;
}

async function generarVistaPrevia(archivo, seleccion) {
  const { lienzo, texto, nota } = elementosImagen;
  const geotiff = await obtenerGeoTiff();
  if (seleccion !== seleccionImagen) return;
  const tiff = await geotiff.fromBlob(archivo);
  const imagen = await tiff.getImage();
  const ancho = imagen.getWidth();
  const alto = imagen.getHeight();
  const bandas = imagen.getSamplesPerPixel();
  if (ancho * alto > maxPixelesTiff || bandas === 2) {
    const mensaje = ancho * alto > maxPixelesTiff ? "El TIFF supera los 16 millones de píxeles." : "El TIFF debe tener una banda o al menos tres.";
    throw new RangeError(mensaje);
  }
  if (seleccion !== seleccionImagen) return;
  const escala = Math.min(1, 640 / Math.max(ancho, alto));
  const dimensiones = { width: Math.max(1, Math.round(ancho * escala)), height: Math.max(1, Math.round(alto * escala)) };
  const color = [2, 3, 5, 6, 8, 9].includes(imagen.fileDirectory.PhotometricInterpretation);
  let pixeles;
  if (color) {
    pixeles = await imagen.readRGB(dimensiones);
  } else {
    pixeles = await imagen.readRasters({ ...dimensiones, samples: [0], interleave: true });
  }
  if (seleccion !== seleccionImagen) return;

  lienzo.width = dimensiones.width;
  lienzo.height = dimensiones.height;
  const contexto = lienzo.getContext("2d");
  const cuadro = contexto.createImageData(lienzo.width, lienzo.height);
  const escalaGris = Math.max(1, 2 ** (imagen.fileDirectory.BitsPerSample?.[0] || 8) - 1);
  for (let i = 0; i < cuadro.data.length / 4; i++) {
    const gris = pixeles[i] * 255 / escalaGris;
    cuadro.data[i * 4] = color ? pixeles[i * 3] : gris;
    cuadro.data[i * 4 + 1] = color ? pixeles[i * 3 + 1] : gris;
    cuadro.data[i * 4 + 2] = color ? pixeles[i * 3 + 2] : gris;
    cuadro.data[i * 4 + 3] = 255;
  }
  contexto.putImageData(cuadro, 0, 0);
  lienzo.hidden = false;
  texto.hidden = true;
  nota.hidden = false;
  nota.textContent = `${ancho} × ${alto} píxeles · Vista previa local`;
}

function limpiarImagen() {
  const { texto, lienzo, enviar, enviarZona, nota, nombre, detalle, estado, origen } = elementosImagen;
  seleccionImagen++;
  solicitudImagen?.abort();
  solicitudImagen = undefined;
  archivoActual = undefined;
  recorteAutomatico = false;
  lienzo.hidden = true;
  texto.hidden = false;
  texto.textContent = "La vista previa del recorte aparecerá aquí.";
  nota.hidden = true;
  nombre.hidden = true;
  origen.hidden = true;
  enviar.disabled = true;
  enviarZona.disabled = false;
  indicarEstado(estado);
  mensajeInicial(detalle, "Las probabilidades del modelo aparecerán aquí.");
}

async function seleccionarImagen(archivo) {
  const { texto, enviar, nota, nombre, estado } = elementosImagen;
  limpiarImagen();
  if (!archivo) return;
  const seleccion = seleccionImagen;

  if (archivo.size > maxBytesTiff) {
    indicarEstado(estado, "El TIFF supera el límite de 16 MiB.", true);
    return;
  }
  if (!/\.tiff?$/i.test(archivo.name)) {
    indicarEstado(estado, "Selecciona un archivo con extensión .tif o .tiff.", true);
    return;
  }

  const cabecera = new Uint8Array(await archivo.slice(0, 4).arrayBuffer());
  if (seleccion !== seleccionImagen) return;
  const firma = Array.from(cabecera).join(",");
  if (!["73,73,42,0", "77,77,0,42", "73,73,43,0", "77,77,0,43"].includes(firma)) {
    indicarEstado(estado, "El archivo no tiene una cabecera TIFF válida.", true);
    return;
  }
  texto.textContent = "Preparando la vista previa…";
  const mib = archivo.size / 1024 ** 2;
  nombre.textContent = `${archivo.name} · ${numero.format(mib)} MiB`;
  nombre.hidden = false;
  try {
    await generarVistaPrevia(archivo, seleccion);
  } catch (error) {
    if (seleccion !== seleccionImagen) return;
    if (error instanceof RangeError) {
      indicarEstado(estado, error.message, true);
      texto.textContent = "No se puede mostrar este archivo.";
      return;
    }
    texto.textContent = "Vista previa no disponible.";
    nota.hidden = false;
    nota.textContent = "Puedes enviar el TIFF para que el servidor lo compruebe.";
  }
  if (seleccion === seleccionImagen) {
    archivoActual = archivo;
    enviar.disabled = false;
  }
}

function mostrarResultadoImagen(resultado, fuente) {
  const { detalle, origen } = elementosImagen;
  origen.textContent = fuente;
  origen.hidden = false;
  detalle.replaceChildren(categoriaResultado(resultado.categoria));
  for (const clase of ["Buenos", "Normales", "Malos"]) {
    const probabilidad = resultado.probabilidades[clase];
    detalle.append(metricaResultado(clase, probabilidad, porcentaje.format(probabilidad)));
  }
  const veto = metricaResultado("Veto estimado por IA", resultado.probabilidad_veto, porcentaje.format(resultado.probabilidad_veto));
  veto.classList.add("veto");
  detalle.append(veto);
}

async function analizarZonaImagen(evento) {
  evento.preventDefault();
  const { archivo, enviarZona, estado, texto } = elementosImagen;
  const zona = datosZona();
  if (!zona) {
    indicarEstado(estado, "Introduce coordenadas válidas y un radio mayor que cero.", true);
    return;
  }
  const { min, max } = elementosZona.deslizador;
  if (zona.radio_m < Number(min) || zona.radio_m > Number(max)) {
    indicarEstado(estado, "El recorte automático admite radios entre 50 y 2.000 m.", true);
    return;
  }
  limpiarImagen();
  archivo.value = "";
  recorteAutomatico = true;
  const seleccion = seleccionImagen;
  const solicitud = new AbortController();
  solicitudImagen = solicitud;
  enviarZona.disabled = true;
  sincronizarMapa(true);
  texto.textContent = "Preparando el recorte…";
  indicarEstado(estado, "Recortando la imagen Sentinel-2 y analizando el círculo…");
  try {
    const resultado = await pedirApi("analizar-zona-imagen", {
      method: "POST", signal: solicitud.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(zona),
    });
    if (solicitudImagen !== solicitud) return;
    mostrarResultadoImagen(resultado, `Copernicus Sentinel-2 · Mosaico PNT (IGN) · Radio de ${numero.format(zona.radio_m)} m`);
    indicarEstado(estado);
    try {
      const datos = Uint8Array.from(atob(resultado.recorte_tiff), (caracter) => caracter.charCodeAt(0));
      await generarVistaPrevia(new Blob([datos], { type: "image/tiff" }), seleccion);
    } catch {
      if (solicitudImagen === solicitud) texto.textContent = "Vista previa no disponible.";
    }
  } catch (error) {
    if (solicitudImagen === solicitud) {
      texto.textContent = "La vista previa del recorte aparecerá aquí.";
      indicarEstado(estado, error.message, true);
    }
  } finally {
    if (solicitudImagen === solicitud) {
      solicitudImagen = undefined;
      enviarZona.disabled = false;
    }
  }
}

function configurarImagen() {
  const { archivo, zonaArchivo, formulario, formularioZona, estado, enviar } = elementosImagen;
  formularioZona.addEventListener("submit", analizarZonaImagen);
  archivo.addEventListener("change", () => seleccionarImagen(archivo.files[0]));
  zonaArchivo.addEventListener("dragover", (evento) => {
    if (!evento.dataTransfer.types.includes("Files")) return;
    evento.preventDefault();
    zonaArchivo.dataset.arrastre = "true";
  });
  zonaArchivo.addEventListener("dragleave", (evento) => {
    if (!zonaArchivo.contains(evento.relatedTarget)) zonaArchivo.dataset.arrastre = "false";
  });
  zonaArchivo.addEventListener("drop", (evento) => {
    evento.preventDefault();
    zonaArchivo.dataset.arrastre = "false";
    archivo.value = "";
    if (evento.dataTransfer.files.length !== 1) {
      limpiarImagen();
      indicarEstado(estado, "Selecciona un TIFF cada vez.", true);
      return;
    }
    seleccionarImagen(evento.dataTransfer.files[0]);
  });

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!archivoActual) return;

    const solicitud = new AbortController();
    solicitudImagen = solicitud;
    enviar.disabled = true;
    indicarEstado(estado, "Analizando imagen…");

    const datos = new FormData();
    datos.append("archivo", archivoActual);
    try {
      const resultado = await pedirApi("analizar-imagen", { method: "POST", signal: solicitud.signal, body: datos });
      if (solicitudImagen !== solicitud) return;
      mostrarResultadoImagen(resultado, archivoActual.name);
      indicarEstado(estado);
    } catch (error) {
      if (solicitudImagen === solicitud) indicarEstado(estado, error.message, true);
    } finally {
      if (solicitudImagen === solicitud) {
        solicitudImagen = undefined;
        enviar.disabled = false;
      }
    }
  });
}

configurarPestanas();
configurarZona();
configurarImagen();
crearMapa();
