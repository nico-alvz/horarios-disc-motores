// Sitio de resultados: carga data/resultados.json y arma gráficos SVG, tablas, grilla horaria y descargas.
const DIAS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sa"];
const BLOQ = "ABCDEFG".split("");
const HORAS = ["08:10", "09:50", "11:30", "13:10", "14:50", "16:30", "18:10"];   // referencia visual; la hoja de laboratorios define las reales
const COLOR_MOTOR = { "FET": "var(--fet)", "CP-SAT": "var(--cp)" };
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, html = "") => { const n = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); n.innerHTML = html; return n; };
const svgNS = "http://www.w3.org/2000/svg";
const sv = (tag, attrs = {}, txt) => { const n = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (txt != null) n.textContent = txt; return n; };
const fmt = (n, d = 0) => n == null ? "-" : Number(n).toLocaleString("es-CL", { maximumFractionDigits: d, minimumFractionDigits: d });
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- tema
const btnTema = $("#tema");
btnTema.addEventListener("click", () => {
  const actual = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const nuevo = actual === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento */ }
});

// ---------- tooltip
const tip = $("#tip");
const mostrarTip = (ev, html) => { tip.innerHTML = html; tip.style.opacity = 1; const x = Math.min(ev.clientX + 14, innerWidth - 300); tip.style.left = x + "px"; tip.style.top = (ev.clientY + 14) + "px"; };
const ocultarTip = () => { tip.style.opacity = 0; };

// ---------- reveal al entrar en pantalla
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("visto"); io.unobserve(e.target); } }), { threshold: .12 });
document.querySelectorAll(".rv").forEach(n => io.observe(n));

// ---------- menu activo
const secciones = [...document.querySelectorAll("main section[id]")];
const links = [...document.querySelectorAll("#menu a")];
const ioMenu = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) links.forEach(a => a.classList.toggle("activo", a.getAttribute("href") === "#" + e.target.id));
}), { rootMargin: "-45% 0px -50% 0px" });
secciones.forEach(s => ioMenu.observe(s));

// ---------- carga de datos
async function cargar(ruta) { const r = await fetch(ruta); if (!r.ok) throw new Error(ruta + " " + r.status); return r.json(); }
let R, cacheH = {};
try { R = await cargar("data/resultados.json"); R.reglas = await cargar("data/reglas.json"); } catch (e) {
  document.querySelector("main").insertAdjacentHTML("afterbegin", `<div class="wrap vacio" style="margin-top:40px">No se pudieron cargar los datos (${esc(e.message)}). Abre el sitio desde un servidor web (GitHub Pages o <code>python -m http.server</code>).</div>`);
  throw e;
}
const RENOMBRE = {
  cpsat_optimo: ["CP-SAT, óptimo", "Menor costo posible con las reglas S1 a S3, probado por el solver. No considera parecerse al horario original."],
  cpsat_factible: ["CP-SAT, solo válido", "Cualquier horario sin choques, sin intentar mejorarlo."],
  cpsat_A_estable: ["CP-SAT A, muy parecido al original", "Peso 8 por sesión movida: cambia lo mínimo necesario."],
  cpsat_B_balance: ["CP-SAT B, equilibrado", "Peso 4 por sesión movida: equilibrio entre parecido y calidad."],
  cpsat_C_calidad: ["CP-SAT C, más calidad", "Peso 1 por sesión movida: prioriza huecos y ventanas."],
  cpsat_libre_S1S3: ["CP-SAT, sala libre", "Cualquier sala con capacidad suficiente; sin reglas de laboratorio ni disponibilidad."],
  cpsat_libre_extras: ["CP-SAT, sala libre con reglas", "Agrega laboratorios y disponibilidad de docentes por hora."],
  cpsat_libre_extras_S10: ["CP-SAT, capacidad ajustada", "Además minimiza los asientos libres de cada sala."],
};
R.horarios.forEach(h => { const r = RENOMBRE[h.id]; if (r) { h.nombre = r[0]; h.descripcion = r[1]; } });
const H = Object.fromEntries(R.horarios.map(h => [h.id, h]));
async function horario(id) { return cacheH[id] ??= await cargar(`data/horarios/${id}.json`); }

// ---------- KPIs
$("#kpis").innerHTML = [
  [R.meta.sesiones, "sesiones semanales a ubicar"], [R.meta.docentes, "docentes"], [R.meta.salas, "salas"],
].map(([n, t]) => `<div><b>${fmt(n)}</b><span>${t}</span></div>`).join("");

// ---------- grilla horaria
function pintarGrid(cont, sesiones, { mini = false, etiqueta = "asignatura" } = {}) {
  cont.innerHTML = "";
  cont.classList.toggle("mini", mini);
  const dias = sesiones.some(s => s.dia === 5) ? 6 : 5;
  cont.style.gridTemplateColumns = `${mini ? 34 : 42}px repeat(${dias}, minmax(0, 1fr))`;
  cont.append(el("div", { class: "dh" }));
  for (let d = 0; d < dias; d++) cont.append(el("div", { class: "dh" }, DIAS[d]));
  const mapa = {};
  sesiones.forEach(s => { for (let k = 0; k < s.dur; k++) (mapa[`${s.dia},${s.bloque + k}`] ??= []).push({ s, primero: k === 0 }); });
  const ocupados = new Set();
  const colores = new Map();
  const tono = nom => { if (!colores.has(nom)) { let h = 0; for (const c of nom) h = (h * 31 + c.charCodeAt(0)) % 360; colores.set(nom, h); } return colores.get(nom); };
  let idx = 0;
  for (let b = 0; b < 7; b++) {
    if (b === 3) { const sep = el("div", { class: "celda almuerzo", "aria-hidden": "true" }); sep.style.gridColumn = `1 / span ${dias + 1}`; cont.append(sep); }
    cont.append(el("div", { class: "bh" }, BLOQ[b]));
    for (let d = 0; d < dias; d++) {
      const k = `${d},${b}`; const lista = mapa[k];
      if (!lista) { cont.append(el("div", { class: "celda vacia" })); continue; }
      const { s, primero } = lista[0];
      const celda = el("div", { class: "celda nuevo" + (lista.length > 1 || s.choque ? " choque" : "") });
      celda.style.setProperty("--i", idx++);
      const h = tono(s.asignatura);
      celda.style.background = `color-mix(in srgb, hsl(${h} 55% 52%) 24%, var(--surface))`;
      celda.style.color = "var(--text)";
      const nombre = etiqueta === "docente" ? (s.docentes || []).join(", ") : s.asignatura;
      celda.innerHTML = primero ? `<b>${esc(nombre)}</b><small>${esc(s.sala || "sin sala")}${lista.length > 1 ? " +" + (lista.length - 1) : ""}</small>` : `<small>continúa</small>`;
      celda.addEventListener("mousemove", ev => mostrarTip(ev, lista.map(({ s: q }) => `${esc(q.asignatura)}<br>NRC ${esc(q.nrc)} - ${esc(q.sala || "sin sala")}<br>cupo ${q.cupo}${q.capacidad_sala ? " / capacidad " + q.capacidad_sala : ""}<br>${esc((q.docentes || []).join(", "))}`).join("<hr>")));
      celda.addEventListener("mouseleave", ocultarTip);
      cont.append(celda);
    }
  }
}

// ---------- hero: mini grilla real
(async () => {
  const id = H.cpsat_B_balance ? "cpsat_B_balance" : R.horarios.find(h => h.valido)?.id;
  const d = await horario(id);
  const sem = d.grupos.find(g => g === "ICCI-S6") || d.grupos[0];
  const ses = d.sesiones.filter(s => s.grupos.includes(sem));
  $("#hero-titulo").textContent = `Semestre ${sem}`;
  $("#hero-chip").textContent = `${H[id].violaciones} choques`;
  $("#hero-grid").parentElement.querySelector("#hero-pie").textContent = `${H[id].nombre}: ${H[id].descripcion}`;
  pintarGrid($("#hero-grid"), ses, { mini: true });
})();

// ---------- tabla del juguete
(() => {
  const t = $("#tabla-juguete");
  t.innerHTML = `<thead><tr><th>Motor</th><th class="num">Choques</th><th class="num">Costo</th><th class="num">Cota</th><th class="num">Seg</th></tr></thead><tbody>` +
    R.juguete.map(j => { const mejor = j.costo != null && j.costo === Math.min(...R.juguete.filter(x => x.costo != null).map(x => x.costo));
      return `<tr class="${mejor ? "mejor" : ""}"><td>${esc(j.motor)}</td><td class="num">${j.costo == null ? "sin resultado" : j.violaciones}</td><td class="num">${j.costo == null ? "-" : fmt(j.costo)}</td><td class="num">${j.cota == null ? "-" : fmt(j.cota)}</td><td class="num">${j.costo == null ? "&gt;" + fmt(j.segundos, 0) : fmt(j.segundos, 2)}</td></tr>`; }).join("") + "</tbody>";
})();

// ---------- costo: desglose y glosario
(() => {
  const sel = $("#d-horario");
  const cand = R.horarios.filter(h => h.huecos != null);
  sel.innerHTML = cand.map(h => `<option value="${h.id}">${esc(h.nombre)}</option>`).join("");
  sel.value = H.fet_base_V03 ? "fet_base_V03" : cand[0].id;
  const pintar = () => {
    const h = H[sel.value], f = [["Huecos", "bloques libres de estudiantes", h.huecos, 3], ["Ventanas", "bloques libres de docentes", h.ventanas, 2], ["Bloques F o G", "sesiones desde las 18:00", h.fg, 1]];
    const tope = Math.max(...cand.flatMap(x => [x.huecos * 3, x.ventanas * 2, x.fg]), 1);
    $("#desglose").innerHTML = f.map(([n, sub, v, w]) => `<div class="d-fila"><span class="nom">${n}<small>${v} x ${w}</small></span><span class="d-pista"><i style="width:${Math.max(v * w / tope * 100, v ? 2 : 0)}%"></i></span><b>${v * w}</b></div>`).join("") +
      `<div class="d-total"><span>${h.valido ? "Horario válido" : h.violaciones + " choques: no es válido"}, costo total</span><b>${fmt(h.huecos * 3 + h.ventanas * 2 + h.fg)}</b></div>`;
  };
  sel.addEventListener("change", pintar); pintar();

  const G = [
    ["Lo básico", "Bloque", "Tramo de clase de 90 minutos. Hay siete por día: A 08:10, B 09:55, C 11:40, D 14:30, E 16:15, F 18:00 y G 19:45. El almuerzo cae entre C y D."],
    ["Lo básico", "Sesión", "Una clase semanal ubicada en un día y un bloque. Una asignatura con dos clases por semana tiene dos sesiones."],
    ["Lo básico", "Semestre", "Grupo de estudiantes que cursan juntos, por ejemplo ICCI-S6. Dos clases de un mismo semestre no pueden coincidir."],
    ["Lo básico", "Curso compartido", "Asignatura que se dicta a la vez en varios programas. Su cupo es la suma de los cupos de todas sus secciones, y eso decide qué sala sirve."],
    ["Lo básico", "Cupo y capacidad", "El cupo es cuántos estudiantes tiene la clase. La capacidad es cuántos caben en la sala. La capacidad debe alcanzar para el cupo."],
    ["Validez", "Regla dura", "Condición que no se puede romper. Si se rompe, el horario no es válido."],
    ["Validez", "Regla blanda", "Preferencia que se puede incumplir a cambio de puntos de costo. El motor intenta cumplir la mayor cantidad posible."],
    ["Validez", "Choque", "Algo que no puede ocurrir a la vez: un docente en dos salas, una sala con dos clases, o estudiantes con dos clases en el mismo bloque."],
    ["Validez", "Horario válido o factible", "Horario sin choques que cumple todas las reglas duras. Es lo que pide el encargo. Factible es el término técnico que usan los motores."],
    ["Costo", "Costo", "Puntos de incomodidad de un horario válido: 3 por cada hueco, 2 por cada ventana y 1 por cada sesión en F o G. Menos es mejor. Es la vara común con la que se comparan todos los motores."],
    ["Costo", "Hueco", "Bloque libre entre dos clases de un mismo semestre en un mismo día. Obliga a esperar sin clase."],
    ["Costo", "Ventana", "Bloque libre entre dos clases de un mismo docente en un mismo día."],
    ["Costo", "Peso", "Cuántos puntos vale cada incomodidad. Los pesos 3, 2 y 1 son supuestos de trabajo: ninguna fuente del cliente los respalda todavía."],
    ["Costo", "Objetivo", "Lo que el motor realmente minimiza. Puede incluir más que el costo: estabilidad, asientos libres o preferencias de docentes. Por eso objetivo y costo pueden ser distintos."],
    ["Costo", "Estabilidad", "Qué tanto se parece el horario nuevo al original. Se mide en sesiones movidas y en porcentaje de sesiones iguales. El peso por sesión movida se llama w5."],
    ["Costo", "Asientos libres", "Capacidad de la sala menos cupo de la clase, sumado sobre todas las sesiones. Mide cuánto se desperdician las salas grandes."],
    ["Motores", "Heurístico", "Motor que busca un buen horario sin garantías. FET lo es: entrega uno válido rápido, pero no dice qué tan lejos está del mejor."],
    ["Motores", "Exacto", "Motor que puede demostrar que no existe nada mejor. CP-SAT, HiGHS y Gurobi lo son, si terminan dentro del tiempo."],
    ["Motores", "Óptimo probado", "El mejor horario posible bajo las reglas y los pesos usados, con prueba: la cota inferior es igual al costo encontrado."],
    ["Motores", "Cota y brecha", "La cota es el mejor valor que podría existir según el motor. La brecha es la distancia entre el horario encontrado y la cota. Brecha cero significa óptimo probado."],
    ["Motores", "Sin solución en el tiempo", "El motor no encontró nada antes del límite. No significa que el problema sea imposible, solo que no alcanzó."],
    ["Datos", "Datos inventados", "Información que no viene del cliente y se usa solo para la demostración: la disponibilidad de docentes por hora y la lista de salas de laboratorio."],
    ["Datos", "Anonimización", "Los docentes aparecen como Docente 01, Docente 02 y así. No se publica ningún RUT. Salas, asignaturas, cupos y bloques son los reales."],
  ];
  const cats = ["Todo", ...new Set(G.map(g => g[0]))]; let cat = "Todo", q = "";
  const norm = t => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const lista = () => {
    $("#g-cats").innerHTML = cats.map(c => `<button class="tab" role="tab" aria-selected="${c === cat}" data-c="${c}" style="height:34px;padding:0 12px">${c}</button>`).join("");
    $("#g-cats").querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => { cat = b.dataset.c; lista(); }));
    const vis = G.filter(([c, t, d]) => (cat === "Todo" || c === cat) && (!q || norm(t + " " + d).includes(q)));
    $("#g-lista").innerHTML = vis.length ? vis.map(([c, t, d]) => `<div class="glos-item"><dt>${esc(t)} <span class="chip">${esc(c)}</span></dt><dd>${esc(d)}</dd></div>`).join("") : `<div class="vacio" style="grid-column:1/-1">Ningún término coincide con la búsqueda.</div>`;
  };
  $("#g-buscar").addEventListener("input", e => { q = norm(e.target.value.trim()); lista(); });
  lista();
})();

// ---------- reglas con pestañas
(() => {
  const tabs = $("#tabs-reglas"), lista = $("#lista-reglas");
  const defs = [["dura", "Duras"], ["blanda", "Blandas"]];
  let activa = "dura";
  const pintar = () => {
    tabs.innerHTML = defs.map(([k, t]) => `<button class="tab" role="tab" aria-selected="${k === activa}" data-k="${k}">${t} (${R.reglas.filter(r => r.tipo === k).length})</button>`).join("");
    lista.innerHTML = R.reglas.filter(r => r.tipo === activa).map(r =>
      `<div class="regla"><span class="id">${esc(r.id)}</span><p>${esc(r.texto)}</p><span class="chip ${r.proc === "E" ? "ok" : r.proc === "B" ? "aviso" : ""}" title="Procedencia">${esc(r.proc)}</span></div>`).join("");
    tabs.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => { activa = b.dataset.k; pintar(); }));
  };
  pintar();
})();

// ---------- motores (carrusel)
const ENLACE = {
  "FET": "https://www.lalescu.ro/liviu/fet/", "OR-Tools CP-SAT": "https://developers.google.com/optimization/cp/cp_solver",
  "MiniZinc + Gecode / Chuffed": "https://www.minizinc.org/", "MiniZinc + HiGHS": "https://highs.dev/", "Gurobi": "https://www.gurobi.com/",
  "HiGHS directo": "https://highs.dev/", "SCIP": "https://www.scipopt.org/", "Timefold Solver": "https://timefold.ai/", "UniTime": "https://www.unitime.org/",
};
const MARCA = { "OR-Tools CP-SAT": "img/google.svg", "Gurobi": "img/gurobi.svg" };   // logos reales de Simple Icons; el resto, monograma
const MONO = { "FET": "F", "MiniZinc + Gecode / Chuffed": "Mz", "MiniZinc + HiGHS": "Mz", "HiGHS directo": "Hi", "SCIP": "S", "Timefold Solver": "T", "UniTime": "U" };
const marca = n => MARCA[n] ? `<span class="logo" style="--src:url(${new URL(MARCA[n], document.baseURI).href})" role="img" aria-label="Logo de ${esc(n)}"></span>` : `<span class="logo mono-marca" aria-hidden="true">${MONO[n] || n[0]}</span>`;
const MOTORES = [
  { n: "FET", t: "Aplicación especializada", ej: true, lic: "AGPL-3.0, sin límite de tamaño", mod: "Actividades, docentes, grupos y salas en un archivo XML con pesos.", cert: "Heurístico: entrega un horario válido, sin cota de qué tan lejos está del mejor.", aqui: "Ejecutado. Es la referencia del prototipo." },
  { n: "OR-Tools CP-SAT", t: "Solver de restricciones", ej: true, dest: true, lic: "Apache-2.0, sin límite de tamaño", mod: "Variables booleanas de asignación, un costo entero explícito y restricciones de no solape.", cert: "Encuentra válidos, mejora y puede probar el óptimo con una cota.", aqui: "Ejecutado sobre los datos reales. Recomendado como primer motor alternativo." },
  { n: "MiniZinc + Gecode / Chuffed", t: "Lenguaje de modelado + CP", ej: true, lic: "MPL-2.0 el compilador, MIT los solvers", mod: "Un modelo declarativo que se puede ejecutar con varios solvers.", cert: "Puede probar óptimo si termina la búsqueda.", aqui: "Ejecutado en la instancia pequeña: válidos, pero lejos del mejor en 30 s." },
  { n: "MiniZinc + HiGHS", t: "Lenguaje de modelado + MIP", ej: true, lic: "MIT", mod: "El mismo modelo traducido a programación entera.", cert: "Entrega cota y brecha cuando la formulación lo permite.", aqui: "Ejecutado en la instancia pequeña: en una corrida entregó un horario válido de costo 18 y en otra no terminó en 40 s. Sin prueba de óptimo." },
  { n: "Gurobi", t: "Solver MIP comercial", ej: true, lic: "Propietario. La licencia restringida admite 2.000 variables; la académica excluye uso operativo.", mod: "Binarias de sesión, día, bloque y sala con restricciones lineales.", cert: "Cota, incumbente y brecha. Óptimo probado en la instancia pequeña.", aqui: "Ejecutado en la instancia pequeña. El problema real superaría el límite de la licencia gratuita." },
  { n: "HiGHS directo", t: "Solver MIP libre", ej: false, lic: "MIT, sin límite de tamaño", mod: "La misma formulación lineal que Gurobi, mediante highspy.", cert: "Puede probar óptimo e informar brecha.", aqui: "Documentado. Se usó solo a través de MiniZinc." },
  { n: "SCIP", t: "MIP y programación por restricciones", ej: false, lic: "Apache-2.0 desde la versión 8.0.3", mod: "PySCIPOpt o MiniZinc.", cert: "Cotas y prueba de optimalidad cuando concluye.", aqui: "Documentado, no ejecutado." },
  { n: "Timefold Solver", t: "Planificación con búsqueda local", ej: false, lic: "Núcleo Apache-2.0", mod: "Entidades de planificación con puntaje duro y blando, en ecosistema JVM.", cert: "Metaheurísticas: mejores soluciones conocidas, sin prueba global.", aqui: "Documentado. Secundario para un prototipo en Python." },
  { n: "UniTime", t: "Sistema universitario completo", ej: false, lic: "Aplicación Apache-2.0, solver LGPL-3.0", mod: "Cursos, salas, docentes y demanda estudiantil como entidades del sistema.", cert: "Búsqueda local: no entrega certificado global.", aqui: "Documentado. Tiene sentido si el alcance crece a gestión institucional." },
];
$("#carrusel").innerHTML = MOTORES.map(m => `
  <article class="panel motor${m.dest ? " destacado" : ""}">
    <header>${marca(m.n)}<h3>${esc(m.n)}</h3><span class="chip ${m.ej ? "ok" : ""}">${m.ej ? "ejecutado" : "documentado"}</span></header>
    <span class="tipo">${esc(m.t)}</span>
    <dl>
      <div><dt>Licencia</dt><dd>${esc(m.lic)}</dd></div>
      <div><dt>Cómo se modela</dt><dd>${esc(m.mod)}</dd></div>
      <div><dt>Qué puede certificar</dt><dd>${esc(m.cert)}</dd></div>
      <div><dt>En este proyecto</dt><dd>${esc(m.aqui)}</dd></div>
    </dl>
    <a class="enlace-motor" href="${ENLACE[m.n]}" target="_blank" rel="noopener">Sitio oficial de ${esc(m.n.split(" + ")[0].split(" / ")[0])}</a>
  </article>`).join("");

(() => {
  const c = $("#carrusel"), paso = () => Math.min(c.clientWidth * .8, 700);
  $("#car-prev").addEventListener("click", () => c.scrollBy({ left: -paso(), behavior: "smooth" }));
  $("#car-next").addEventListener("click", () => c.scrollBy({ left: paso(), behavior: "smooth" }));
  const act = () => { const fin = c.scrollLeft + c.clientWidth >= c.scrollWidth - 8; $("#car-prev").disabled = c.scrollLeft < 8; $("#car-next").disabled = fin; c.classList.toggle("fin", fin); };
  c.addEventListener("scroll", act, { passive: true }); act();
})();

// ---------- gráfico de barras horizontal reutilizable
function barras(svg, filas, { max, formato = v => fmt(v), ancho = 920, etiquetaAncho = 190 } = {}) {
  svg.innerHTML = "";
  const alto = filas.length * 34 + 28;
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  const tope = max ?? Math.max(...filas.map(f => f.valor), 1) * 1.12;
  const x0 = etiquetaAncho, W = ancho - x0 - 70;
  for (let i = 0; i <= 4; i++) {
    const x = x0 + W * i / 4;
    svg.append(sv("line", { x1: x, x2: x, y1: 10, y2: alto - 18, class: "guia" }));
    svg.append(sv("text", { x, y: alto - 2, "text-anchor": "middle" }, fmt(tope * i / 4)));
  }
  filas.forEach((f, i) => {
    const y = 14 + i * 34;
    const t = sv("text", { x: x0 - 12, y: y + 14, "text-anchor": "end" }, f.etiqueta); svg.append(t);
    const w = Math.max(f.valor / tope * W, f.valor > 0 ? 2 : 0);
    const r = sv("rect", { x: x0, y, width: 0, height: 22, rx: 5, fill: f.color, class: "bar" });
    r.style.transition = "width .8s cubic-bezier(.16,1,.3,1)";
    r.addEventListener("mousemove", ev => mostrarTip(ev, f.tip || esc(f.etiqueta)));
    r.addEventListener("mouseleave", ocultarTip);
    svg.append(r);
    requestAnimationFrame(() => requestAnimationFrame(() => r.setAttribute("width", w)));
    svg.append(sv("text", { x: x0 + w + 8, y: y + 15, class: "etq-barra" }, f.rotulo ?? formato(f.valor)));
  });
}
const leyendaMotor = () => `<span><i style="background:var(--fet)"></i>FET</span><span><i style="background:var(--cp)"></i>CP-SAT</span>`;

// ---------- resultados con pestañas por escenario
(() => {
  const nClienteRef = R.meta.choques_cliente;
  const ref = H.cliente_ref;
  $("#res-lead").textContent = `El horario original del cliente tiene ${nClienteRef} choques. Todas las opciones que siguen cumplen las reglas duras: encontrar una válida no fue el problema, la diferencia está en su calidad.`;
  const grupos = [
    ["salas_cliente", "Salas del cliente", "Cada clase usa las salas que ya tenía. Casi no hay decisión de sala.", "costo"],
    ["sala_libre", "Sala libre", "Cualquier sala con capacidad suficiente. Se agregan laboratorios y disponibilidad inventada como reglas.", "costo"],
  ];
  let activo = grupos[0][0];
  const tabs = $("#tabs-res");
  const pintar = () => {
    tabs.innerHTML = grupos.map(([k, t]) => `<button class="tab" role="tab" aria-selected="${k === activo}" data-k="${k}">${t}</button>`).join("");
    tabs.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => { activo = b.dataset.k; pintar(); }));
    const g = grupos.find(x => x[0] === activo);
    $("#res-titulo").textContent = "Costo blando por horario (menor es mejor)";
    $("#res-sub").textContent = g[2] + " Costo = 3 por hueco de estudiantes + 2 por ventana docente + 1 por sesión que empieza en bloques F o G.";
    const filas = R.horarios.filter(h => h.grupo === activo).sort((a, b) => a.costo - b.costo);
    barras($("#chart-costos"), filas.map(h => ({ etiqueta: h.nombre, valor: h.costo, color: COLOR_MOTOR[h.motor], tip: `<b>${esc(h.nombre)}</b><br>costo ${fmt(h.costo)}<br>huecos ${h.huecos}, ventanas ${h.ventanas}, F-G ${h.fg}<br>${fmt(h.segundos, 1)} s${h.cota != null ? "<br>óptimo probado (cota " + fmt(h.cota) + ")" : ""}`, rotulo: fmt(h.costo) + (h.cota != null && h.cota === h.costo ? " (óptimo probado)" : "") })), { ancho: 960, etiquetaAncho: 200 });
    $("#ley-costos").innerHTML = leyendaMotor();
    const cols = [["Horario", "nombre"], ["Motor", "motor"], ["Válido", "valido"], ["Huecos", "huecos"], ["Ventanas", "ventanas"], ["F-G", "fg"], ["Costo", "costo"], ["Asientos libres", "desperdicio"], ["Seg", "segundos"]];
    const filasT = [...filas]; if (ref && activo === "salas_cliente") filasT.push(ref);
    $("#tabla-res").innerHTML = `<thead><tr>${cols.map(([t, k]) => `<th class="${["nombre", "motor"].includes(k) ? "" : "num"}">${t}</th>`).join("")}</tr></thead><tbody>` +
      filasT.map(h => `<tr class="${h.cota != null && h.cota === h.costo ? "mejor" : ""}"><td>${esc(h.nombre)}</td><td>${esc(h.grupo === "referencia" ? "Original" : h.motor)}</td>` +
        `<td class="num"><span class="chip ${h.valido ? "ok" : "mal"}">${h.valido ? "válido" : h.violaciones + " choques"}</span></td>` +
        `<td class="num">${h.huecos}</td><td class="num">${h.ventanas}</td><td class="num">${h.fg}</td><td class="num">${fmt(h.costo)}</td><td class="num">${h.desperdicio == null ? "-" : fmt(h.desperdicio)}</td><td class="num">${h.segundos == null ? "-" : fmt(h.segundos, 2)}</td></tr>`).join("") + "</tbody>";
  };
  pintar();
})();

// ---------- salas: desperdicio
(() => {
  const libres = R.horarios.filter(h => h.grupo === "sala_libre" && h.desperdicio != null);
  barras($("#chart-desp"), libres.map(h => ({ etiqueta: h.nombre, valor: h.desperdicio, color: COLOR_MOTOR[h.motor], tip: `<b>${esc(h.nombre)}</b><br>${fmt(h.desperdicio)} asientos libres<br>costo blando ${fmt(h.costo)}` })), { ancho: 760, etiquetaAncho: 220 });
  const sin = H.cpsat_libre_extras, con = H.cpsat_libre_extras_S10;
  if (sin && con) $("#big-desp").textContent = fmt(100 * (1 - con.desperdicio / sin.desperdicio)) + " %";
  $("#salas-texto").textContent = `Con las salas del cliente, ${R.meta.clases_una_sola_sala_modo_cliente} de ${R.meta.clases} clases tienen una única sala posible. El cupo de una clase compartida es la suma de los cupos de sus secciones y ocupa a la vez cada programa y semestre listado. Hay clases con cupo 0 en la planilla: es un dato faltante que conviene corregir en la fuente.`;
  $("#tabla-compartidas").innerHTML = `<thead><tr><th>Asignatura compartida</th><th>Programas</th><th class="num">Cupo</th><th class="num">Salas posibles</th></tr></thead><tbody>` +
    (() => { const u = new Map(); R.compartidas.forEach(c => { const k = [c.asignatura, c.programas, c.cupo, c.salas_candidatas].join("|"); const e = u.get(k); if (e) e.n++; else u.set(k, { ...c, n: 1 }); }); return [...u.values()]; })().map(c => `<tr><td>${esc(c.asignatura)}${c.n > 1 ? ` <span class="chip">${c.n} secciones</span>` : ""}</td><td>${esc(c.programas)}</td><td class="num">${fmt(c.cupo)}</td><td class="num">${fmt(c.salas_candidatas)}</td></tr>`).join("") + "</tbody>";
})();

// ---------- pareto + slider
(() => {
  const P = R.pareto; if (!P.length) return;
  const svg = $("#chart-pareto"), W = 760, Hh = 420, m = { l: 62, r: 24, t: 20, b: 52 };
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  const xs = P.map(p => p.pct_igual), ys = P.map(p => p.costo);
  const x = v => m.l + (v - 0) / 100 * (W - m.l - m.r);
  const ymax = Math.max(...ys) * 1.15; const y = v => Hh - m.b - v / ymax * (Hh - m.t - m.b);
  for (let v = 0; v <= 100; v += 20) { svg.append(sv("line", { x1: x(v), x2: x(v), y1: m.t, y2: Hh - m.b, class: "guia" })); svg.append(sv("text", { x: x(v), y: Hh - m.b + 20, "text-anchor": "middle" }, v + " %")); }
  for (let i = 0; i <= 4; i++) { const v = ymax * i / 4; svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "guia" })); svg.append(sv("text", { x: m.l - 10, y: y(v) + 4, "text-anchor": "end" }, fmt(v))); }
  svg.append(sv("text", { x: (W + m.l) / 2, y: Hh - 8, "text-anchor": "middle" }, "Sesiones iguales al horario original"));
  const t = sv("text", { x: 14, y: Hh / 2, transform: `rotate(-90 14 ${Hh / 2})`, "text-anchor": "middle" }, "Costo blando"); svg.append(t);
  const ord = [...P].sort((a, b) => a.pct_igual - b.pct_igual);
  svg.append(sv("polyline", { points: ord.map(p => `${x(p.pct_igual)},${y(p.costo)}`).join(" "), fill: "none", stroke: "var(--cp)", "stroke-width": 2.5, "stroke-linejoin": "round" }));
  const puntos = P.map(p => { const c = sv("circle", { cx: x(p.pct_igual), cy: y(p.costo), r: 7, fill: "var(--surface)", stroke: "var(--cp)", "stroke-width": 2.5 });
    c.addEventListener("mousemove", ev => mostrarTip(ev, `peso ${p.w5} por sesión movida<br>${fmt(p.pct_igual, 1)} % igual, costo ${fmt(p.costo)}<br>${p.movidas} sesiones movidas`)); c.addEventListener("mouseleave", ocultarTip); svg.append(c); return c; });
  const sel = sv("circle", { r: 11, fill: "none", stroke: "var(--accent)", "stroke-width": 2.5 }); svg.append(sel);
  const rng = $("#w5"); rng.max = P.length - 1; rng.value = Math.min(1, P.length - 1);
  const alt = { 1: "cpsat_C_calidad", 4: "cpsat_B_balance", 8: "cpsat_A_estable" };
  const act = () => {
    const p = P[+rng.value];
    $("#w5-val").textContent = p.w5;
    sel.setAttribute("cx", x(p.pct_igual)); sel.setAttribute("cy", y(p.costo));
    puntos.forEach((c, i) => c.setAttribute("fill", i === +rng.value ? "var(--accent)" : "var(--surface)"));
    $("#lectura-w5").innerHTML = `<div class="fila"><span>Parecido con el original</span><b>${fmt(p.pct_igual, 1)} %</b></div><div class="fila"><span>Sesiones movidas</span><b>${p.movidas}</b></div><div class="fila"><span>Costo blando</span><b>${fmt(p.costo)}</b></div><div class="fila"><span>Estado del solver</span><b>${p.estado === "OPTIMAL" ? "óptimo probado" : esc(p.estado)}</b></div><p class="muted" style="font-size:13px">El horario descargable es una de las soluciones óptimas para ese peso; con igual objetivo, el costo de huecos y ventanas puede variar levemente entre soluciones.</p>`;
    const h = H[alt[p.w5]];
    $("#alt-links").innerHTML = h ? `<a class="descarga" href="${h.xlsx}" download><span>${esc(h.nombre)}<small>Excel anonimizado</small></span><span class="chip ok">xlsx</span></a>` : `<p class="muted" style="font-size:14px;margin-top:6px">Con este peso no se publicó un horario descargable.</p>`;
  };
  rng.addEventListener("input", act); act();
})();

// ---------- explorador
(async () => {
  const fh = $("#f-horario"), fv = $("#f-vista"), fe = $("#f-entidad");
  const orden = ["salas_cliente", "sala_libre", "estabilidad", "referencia"], nombreG = { salas_cliente: "Salas del cliente", sala_libre: "Sala libre", estabilidad: "Estabilidad", referencia: "Referencia" };
  fh.innerHTML = orden.map(g => `<optgroup label="${nombreG[g]}">` + R.horarios.filter(h => h.grupo === g).map(h => `<option value="${h.id}">${esc(h.nombre)}</option>`).join("") + "</optgroup>").join("");
  fh.value = H.cpsat_B_balance ? "cpsat_B_balance" : R.horarios[0].id;
  let datos;
  const entidades = () => {
    const v = fv.value; $("#l-entidad").textContent = { semestre: "Semestre", sala: "Sala", docente: "Docente" }[v];
    const lista = v === "semestre" ? datos.grupos : v === "sala" ? datos.salas : datos.docentes;
    const prev = fe.value; fe.innerHTML = lista.map(x => `<option>${esc(x)}</option>`).join("");
    if (lista.includes(prev)) fe.value = prev; else if (v === "semestre" && lista.includes("ICCI-S6")) fe.value = "ICCI-S6";
  };
  const vista = () => {
    const h = H[fh.value], v = fv.value, e = fe.value;
    const ses = datos.sesiones.filter(s => v === "semestre" ? s.grupos.some(g => g === e || g.startsWith(e + "-")) : v === "sala" ? s.sala === e : (s.docentes || []).includes(e));
    $("#v-titulo").textContent = `${h.nombre}: ${e}`;
    $("#v-chips").innerHTML = `<span class="chip ${h.valido ? "ok" : "mal"}">${h.valido ? "válido, 0 choques" : h.violaciones + " choques"}</span><span class="chip">${ses.length} sesiones</span>`;
    $("#f-resumen").innerHTML = `<b>${esc(h.grupo === "referencia" ? "Original" : h.motor)}</b>: ${esc(h.descripcion)}<br><span class="mono">costo ${fmt(h.costo)}${h.segundos == null ? "" : ", " + fmt(h.segundos, 2) + " s"}</span>`;
    if (!ses.length) { $("#v-grid").innerHTML = `<div class="vacio" style="grid-column:1/-1">Sin sesiones para esta selección.</div>`; $("#v-grid").className = "grid-h"; $("#v-grid").style.gridTemplateColumns = "1fr"; }
    else pintarGrid($("#v-grid"), ses, { etiqueta: v === "docente" ? "asignatura" : "asignatura" });
    $("#v-descargas").innerHTML = [["xlsx", "Excel con 4 hojas"], ["csv", "Sesiones en CSV"]].map(([k, t]) => `<a class="descarga" href="${h[k]}" download><span>${esc(h.nombre)}<small>${t}</small></span><span class="chip ok">${k}</span></a>`).join("");
  };
  const cargarH = async () => {
    $("#v-grid").innerHTML = `<div class="esqueleto" style="grid-column:1/-1"></div>`;
    datos = await horario(fh.value); entidades(); vista();
  };
  fh.addEventListener("change", cargarH); fv.addEventListener("change", () => { entidades(); vista(); }); fe.addEventListener("change", vista);
  await cargarH();
})();

// ---------- vistas previas del cuaderno
(() => {
  const V = [
    ["costo_motores", "Costo por motor", "Costo comparable de cada horario válido: CP-SAT y HiGHS llegan a 0, FET queda en 131."],
    ["horario_semestre", "Un semestre", "El horario de un semestre, con sala y almuerzo marcado, generado por el motor de menor costo."],
    ["ocupacion_salas", "Ocupación de salas", "Qué sala se usa en cada día y bloque."],
    ["estabilidad", "Estabilidad", "Cuánto cambia el horario original según el peso por sesión movida."],
  ];
  let a = 0;
  const pintar = () => {
    $("#tabs-prev").innerHTML = V.map((v, i) => `<button class="tab" role="tab" aria-selected="${i === a}" data-i="${i}">${v[1]}</button>`).join("");
    $("#tabs-prev").querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => { a = +b.dataset.i; pintar(); }));
    $("#prev-img").src = `img/${V[a][0]}.png`; $("#prev-img").alt = V[a][2]; $("#prev-pie").textContent = V[a][2];
  };
  pintar();
})();

// ---------- conclusiones (a partir de los datos medidos)
(() => {
  const fet = R.horarios.filter(h => h.id.startsWith("fet_base_")), cp = H.cpsat_optimo, cpv = H.cpsat_factible, ref = H.cliente_ref;
  const minFet = fet.length ? Math.min(...fet.map(h => h.costo)) : null, maxFet = fet.length ? Math.max(...fet.map(h => h.costo)) : null;
  const ok = [
    `<b>Un horario válido se obtiene al instante.</b> FET y CP-SAT entregan horarios sin choques en una fracción de segundo; el original del cliente tenía ${R.meta.choques_cliente}.`,
    cp && minFet != null ? `<b>Que sea válido no dice qué tan bueno es.</b> Las opciones de FET cuestan entre ${fmt(minFet)} y ${fmt(maxFet)} puntos de costo blando; CP-SAT demostró que existe una con ${fmt(cp.costo)}.` : "",
    `<b>Solo un motor exacto prueba el óptimo.</b> CP-SAT y Gurobi cerraron la brecha en la instancia pequeña; FET no entrega una cota.`,
    `<b>Las reglas se pueden hacer cumplir.</b> Laboratorios y disponibilidad quedaron en cero violaciones al declararlas; FET las ignora salvo que se las inyecten.`,
  ].filter(Boolean);
  const no = [
    `<b>Los pesos del costo no están validados.</b> La entrevista con el encargado docente no entrega ningún peso numérico; los usados son hipótesis de trabajo.`,
    `<b>Hay datos inventados.</b> La disponibilidad de docentes por hora y la lista de salas de laboratorio son supuestos para la demostración.`,
    `<b>El mejor según el costo no es necesariamente el mejor para el cliente.</b> Un costo cero en huecos y ventanas indica que esas reglas no son lo bastante exigentes con estos datos.`,
    `<b>Falta tiempo real de operación.</b> Nada de esto sustituye la validación de un horario con quienes lo usan.`,
  ];
  $("#ok-lista").innerHTML = ok.map(t => `<li>${t}</li>`).join("");
  $("#no-lista").innerHTML = no.map(t => `<li>${t}</li>`).join("");
})();
