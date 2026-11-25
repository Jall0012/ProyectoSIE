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
  archivo: porId("archivo"),
  zonaArchivo: porId("zona-archivo"),
  nombre: porId("nombre-archivo"),
  enviar: porId("enviar-imagen"),
  lienzo: porId("lienzo"),
  vacio: porId("visor-vacio"),
  texto: porId("texto-visor"),
  nota: porId("nota-vista"),
  estado: porId("estado-imagen"),
  detalle: porId("detalle-imagen"),
};

let mapa;
let marcador;
let circulo;
let solicitudZona;
let solicitudImagen;
let archivoActual;
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
    if (pestana.id === "tab-zona") requestAnimationFrame(() => mapa?.invalidateSize());
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

function sincronizarMapa(recentrar = false) {
  const zona = datosZona();
  if (!zona || !mapa) return;
  const centro = [zona.latitud, zona.longitud];
  marcador.setLatLng(centro);
  circulo.setLatLng(centro).setRadius(zona.radio_m);
  if (recentrar) mapa.panTo(centro);
}

function indicarCentro(posicion) {
  const centro = posicion.wrap();
  elementosZona.latitud.value = centro.lat.toFixed(5);
  elementosZona.longitud.value = centro.lng.toFixed(5);
  limpiarZona();
  sincronizarMapa();
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

  const estilos = {
    curvas: { color: "#64735a", weight: 0.8, opacity: 0.35 },
    urbano: { color: "#626653", weight: 1, fillColor: "#5f6251", fillOpacity: 0.7 },
    vias: { color: "#78816e", weight: 0.85, opacity: 0.7 },
    principal: { color: "#aca27b", weight: 1.15, opacity: 0.77 },
  };
  fetch("./mapa-jaen.geojson").then((respuesta) => {
    if (!respuesta.ok) throw new Error("Cartografía no disponible");
    return respuesta.json();
  }).then((datos) => {
    L.geoJSON(datos, { style: (elemento) => estilos[elemento.properties.capa], interactive: false }).addTo(baseLocal);
    for (const [lat, lon, nombre] of [[37.768, -3.79, "Jaén"], [37.774, -3.896, "Torredelcampo"], [37.738, -3.969, "Torredonjimeno"], [37.723, -3.853, "Jamilena"], [37.795, -3.705, "La Guardia de Jaén"]]) {
      L.tooltip({ permanent: true, direction: "center", className: "toponimo", interactive: false })
        .setLatLng([lat, lon]).setContent(nombre).addTo(baseLocal);
    }
    circulo.bringToFront();
  }).catch(() => {
    falloCartografiaLocal = true;
    if (mapa.hasLayer(baseLocal)) notaMapa.textContent = errorLocal;
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
  elementosZona.centrar.addEventListener("click", () => sincronizarMapa(true));
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
  if (respuesta.status >= 500) throw new Error("El servicio no está disponible. Inténtalo de nuevo.");
  const datos = await respuesta.json().catch(() => null);
  const detalle = datos?.detail;
  const mensaje = typeof detalle === "string" ? detalle : "Revisa los datos del formulario.";
  throw new Error(mensaje);
}

function configurarZona() {
  const { latitud, longitud, radio, deslizador, formulario, estado, detalle } = elementosZona;
  for (const entrada of [latitud, longitud]) {
    entrada.addEventListener("input", () => {
      limpiarZona();
      sincronizarMapa();
    });
    entrada.addEventListener("change", () => sincronizarMapa(true));
  }
  radio.addEventListener("input", () => {
    limpiarZona();
    if (Number.isFinite(radio.valueAsNumber)) deslizador.value = radio.value;
    sincronizarMapa();
  });
  deslizador.addEventListener("input", () => {
    radio.value = deslizador.value;
    limpiarZona();
    sincronizarMapa();
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
  const { lienzo, vacio, nota } = elementosImagen;
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
  vacio.hidden = true;
  nota.textContent = `${ancho} × ${alto} píxeles · Vista previa local`;
}

async function seleccionarImagen(archivo) {
  const { texto, lienzo, vacio, enviar, nota, nombre, detalle, estado } = elementosImagen;
  const seleccion = ++seleccionImagen;
  solicitudImagen?.abort();
  solicitudImagen = undefined;
  archivoActual = undefined;
  lienzo.hidden = true;
  vacio.hidden = false;
  nota.textContent = "La vista previa se genera en el navegador.";
  nombre.hidden = true;
  enviar.disabled = true;
  indicarEstado(estado);
  mensajeInicial(detalle, "Las probabilidades del modelo aparecerán aquí.");
  texto.textContent = "Selecciona un TIFF para previsualizarlo.";
  if (!archivo) return;

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
    nota.textContent = "Puedes enviar el TIFF para que el servidor lo compruebe.";
  }
  if (seleccion === seleccionImagen) {
    archivoActual = archivo;
    enviar.disabled = false;
  }
}

function configurarImagen() {
  const { archivo, zonaArchivo, formulario, estado, detalle, enviar } = elementosImagen;
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
      seleccionarImagen();
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
      detalle.replaceChildren(categoriaResultado(resultado.categoria));
      for (const clase of ["Buenos", "Normales", "Malos"]) {
        const probabilidad = resultado.probabilidades[clase];
        detalle.append(metricaResultado(clase, probabilidad, porcentaje.format(probabilidad)));
      }
      const veto = metricaResultado("Probabilidad de veto", resultado.probabilidad_veto, porcentaje.format(resultado.probabilidad_veto));
      veto.classList.add("veto");
      detalle.append(veto);
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
