/* ═══ GRPS WEB — FRONTEND JS ═════════════════════════════════════════════════
   Full port of the PyQt5 desktop app to browser JS.
   Covers: Leaflet map, fleet management, route optimization (via Flask API),
           OSRM routing, results panel, legend, route simulation, PDF, Excel.
══════════════════════════════════════════════════════════════════════════════ */

// ─── I18N ─────────────────────────────────────────────────────────────────────
const TRANSLATIONS = {
  en: {
    routePlanner: 'Route Planner',
    signOut: 'Sign out',
    locations: '📍 Locations',
    addDepot: '+ Depot',
    addCustomer: '+ Customer',
    multiDepotHint: 'Multiple depots supported — optimizer picks best depot per vehicle',
    type1qty: 'Type 1 (qty)',
    type2qty: 'Type 2 (qty)',
    type3qty: 'Type 3 (qty)',
    volume: '📐 Volume',
    unloading: 'Unloading (min)',
    timeWindow: 'Time window',
    searchAddress: 'Search address…',
    go: 'Go',
    orClickMap: 'or click the map to place a pin',
    clearAll: 'Clear all',
    importExcel: 'Import Excel',
    fleet: '🚛 Fleet',
    packageTypes: '📦 Package Types',
    packageWeights: '⚖️ Package Weights',
    type1m3: 'Type 1 (m³)',
    type2m3: 'Type 2 (m³)',
    type3m3: 'Type 3 (m³)',
    type1kg: 'Type 1 (kg)',
    type2kg: 'Type 2 (kg)',
    type3kg: 'Type 3 (kg)',
    algorithm: '⚙️ Algorithm',
    method: 'Method',
    iterations: 'Iterations',
    temperature: 'Temperature',
    hardConstraints: '🔒 Hard Constraints',
    volumeCapacity: '📐 Volume capacity',
    weightCapacity: '⚖️ Weight capacity',
    constraintWarning: '⚠️ Disabling constraints may cause overloads',
    useTimeWindows: '⏱ Use time windows',
    unloadingHint: '⏱ Unloading time per customer is set individually (Excel or manual input)',
    optimiseFor: '🎯 Optimise for',
    fuelCost: '⛽ Fuel cost',
    driverWages: '👷 Driver wages',
    distance: '📏 Distance',
    vehiclesUsed: '🚛 Vehicles used',
    minimisingDefault: 'Minimising: fuel cost + driver wages',
    findRoutes: '🚀 Find Optimal Routes',
    results: '📊 Results',
    litresFuel: 'litres ⛽',
    time: 'time',
    m3load: 'm³ load',
    volFill: 'vol fill %',
    wtFill: 'wt fill %',
    vehicles: 'vehicles',
    fuelCostRSD: 'fuel cost (RSD)',
    wagesRSD: 'wages (RSD)',
    totalCostRSD: 'total cost (RSD)',
    osrmWarning: '⚠️ OSRM unavailable — distances are straight-line estimates',
    runOptimizationHint: 'Run optimization to see results',
    legend: '🗺 Legend',
    toggleAll: '👁 Toggle all',
    actions: 'Actions',
    simSpeed: 'Sim speed',
    slow: '🐢 Slow',
    normal: '🚗 Normal',
    fast: '🚀 Fast',
    turbo: '⚡ Turbo',
    simulateRoutes: '▶ Simulate Routes',
    downloadPDF: '📄 Download PDF',
    configureVehicle: 'Configure Vehicle',
    count: 'Count',
    capacityM3: 'Capacity (m³)',
    weightCap: 'Weight cap (kg)',
    fuel: 'Fuel (L/100km)',
    cancel: 'Cancel',
    apply: 'Apply',
    excelPreview: 'Excel Import Preview',
    geocodingHint: 'Customers will be geocoded after import. This may take a moment.',
    excelColumns: 'Expected columns: Customer, Address, Packages#1, Packages#2, Packages#3, Time',
    importAll: 'Import All',
    searching: '🔍 Searching…',
    found: '✅ Found',
    parsingExcel: '📊 Parsing Excel…',
    geocodingProgress: (i, n, name) => `🔍 Geocoding ${i+1}/${n}: ${name}…`,
    importedCustomers: n => `✅ Imported ${n} customers`,
    foundRows: n => `Found ${n} rows`,
    outOfSerbia: '⚠️ Please place locations within Serbia',
    mapNotLoaded: 'Map not loaded yet — please wait a moment and try again.',
    addDepotFirst: 'Please add at least one depot first.',
    addCustomerFirst: 'Please add at least one customer.',
    optimizationError: 'Optimization error: ',
    routesCalculated: '✅ Routes calculated',
    phase1: 'Phase 1: fetching road distance matrix…',
    phase1short: 'Phase 1: road matrix…',
    phase2: 'Phase 2: optimizing routes…',
    srcHere: '🟢 Live traffic (HERE) — routes & map display',
    srcOsrm: '🔵 Road distances (OSRM)',
    srcHaversine: '🟠 Straight-line estimate',
    optimisedFor: 'Optimised for: ',
    constraints: 'Constraints: ',
    selectAtLeastOne: '⚠️ Select at least one — defaulting to fuel + wages',
    minimising: 'Minimising: ',
    capDisabled: (off, plural) => `⚠️ ${off} cap${plural} disabled — overloads allowed`,
    totalType: (cnt, cap, wStr) => `Type total: ${cnt}m³${wStr}`,
    unlimitedWeight: ' · unlimited weight',
    fleetSummary: (vehs, plural, total) => `🚛 ${vehs} vehicle${plural} · Total capacity: ${total} m³`,
    noVehicles: 'No vehicles configured — click a card',
    configureDash: name => `Configure — ${name}`,
    captureMaps: '📸 Capturing maps…',
    captureVehicle: (i, n) => `📸 Vehicle ${i}/${n}…`,
    buildingPDF: '📄 Building PDF…',
    exportPDF: '📄 Export PDF',
    pdfError: 'PDF error: ',
    errorPrefix: 'Error: ',
    objLabels: { fuel:'⛽ Fuel cost', wages:'👷 Wages', distance:'📏 Distance', vehicles:'🚛 Vehicles' },
    owLabels: { fuel:'⛽ Fuel cost', wages:'👷 Wages', distance:'📏 Distance', vehicles:'🚛 Vehicles' },
    srcBadges: {
      here:      { label: '🟢 Live traffic (HERE) — routes & map display', color: '#22c55e' },
      osrm:      { label: '🔵 Road distances (OSRM)', color: '#3b82f6' },
      haversine: { label: '🟠 Straight-line estimate', color: '#f97316' },
    },
    language: 'Language',
    langEn: 'English',
    langSr: 'Srpski',
    clickToConfigure: 'Click to configure',
    fuelConsumption: 'Fuel consumption',
    unservedWarning: (n, names) => `⚠️ ${n} customer(s) NOT served: ${names}`,
    stopsLabel: n => `${n} stops`,
    splitDelivery: (part, total) => `Split delivery: part ${part} of ${total}`,
    minUnloading: min => `${min} min unloading`,
    volLoad: 'Volumetric load / capacity',
    weightLoad: eff => `Weight load / capacity (effective fuel: ${eff} L/100km)`,
  },
  sr: {
    routePlanner: 'Planer ruta',
    signOut: 'Odjavi se',
    locations: '📍 Lokacije',
    addDepot: '+ Depo',
    addCustomer: '+ Mušterija',
    multiDepotHint: 'Podržano više depoa — optimizator bira najbliži depo po vozilu',
    type1qty: 'Tip 1 (kom)',
    type2qty: 'Tip 2 (kom)',
    type3qty: 'Tip 3 (kom)',
    volume: '📐 Zapremina',
    unloading: 'Istovar (min)',
    timeWindow: 'Vremenski okvir',
    searchAddress: 'Pretraži adresu…',
    go: 'Idi',
    orClickMap: 'ili klikni na mapu da postaviš pin',
    clearAll: 'Obriši sve',
    importExcel: 'Uvezi Excel',
    fleet: '🚛 Vozni park',
    packageTypes: '📦 Tipovi paketa',
    packageWeights: '⚖️ Težine paketa',
    type1m3: 'Tip 1 (m³)',
    type2m3: 'Tip 2 (m³)',
    type3m3: 'Tip 3 (m³)',
    type1kg: 'Tip 1 (kg)',
    type2kg: 'Tip 2 (kg)',
    type3kg: 'Tip 3 (kg)',
    algorithm: '⚙️ Algoritam',
    method: 'Metod',
    iterations: 'Iteracije',
    temperature: 'Temperatura',
    hardConstraints: '🔒 Tvrda ograničenja',
    volumeCapacity: '📐 Kapacitet zapremine',
    weightCapacity: '⚖️ Kapacitet težine',
    constraintWarning: '⚠️ Isključivanje ograničenja može uzrokovati preopterećenja',
    useTimeWindows: '⏱ Koristi vremenske okvire',
    unloadingHint: '⏱ Vreme istovara po mušteriji se postavlja pojedinačno (Excel ili ručno)',
    optimiseFor: '🎯 Optimizuj za',
    fuelCost: '⛽ Troškovi goriva',
    driverWages: '👷 Plate vozača',
    distance: '📏 Rastojanje',
    vehiclesUsed: '🚛 Broj vozila',
    minimisingDefault: 'Minimizacija: troškovi goriva + plate',
    findRoutes: '🚀 Pronađi optimalne rute',
    results: '📊 Rezultati',
    litresFuel: 'litara ⛽',
    time: 'vreme',
    m3load: 'm³ teret',
    volFill: 'popunjenost vol %',
    wtFill: 'popunjenost tež %',
    vehicles: 'vozila',
    fuelCostRSD: 'troškovi goriva (RSD)',
    wagesRSD: 'plate (RSD)',
    totalCostRSD: 'ukupni troškovi (RSD)',
    osrmWarning: '⚠️ OSRM nedostupan — rastojanja su procenjena pravom linijom',
    runOptimizationHint: 'Pokrenite optimizaciju da vidite rezultate',
    legend: '🗺 Legenda',
    toggleAll: '👁 Prikaži/sakrij sve',
    actions: 'Akcije',
    simSpeed: 'Brzina simulacije',
    slow: '🐢 Sporo',
    normal: '🚗 Normalno',
    fast: '🚀 Brzo',
    turbo: '⚡ Turbo',
    simulateRoutes: '▶ Simuliraj rute',
    downloadPDF: '📄 Preuzmi PDF',
    configureVehicle: 'Podesi vozilo',
    count: 'Broj',
    capacityM3: 'Kapacitet (m³)',
    weightCap: 'Kapacitet težine (kg)',
    fuel: 'Gorivo (L/100km)',
    cancel: 'Otkaži',
    apply: 'Primeni',
    excelPreview: 'Pregled Excel uvoza',
    geocodingHint: 'Mušterije će biti geokodirane nakon uvoza. Ovo može potrajati.',
    excelColumns: 'Očekivane kolone: Customer, Address, Packages#1, Packages#2, Packages#3, Time',
    importAll: 'Uvezi sve',
    searching: '🔍 Pretraga…',
    found: '✅ Pronađeno',
    parsingExcel: '📊 Obrada Excel fajla…',
    geocodingProgress: (i, n, name) => `🔍 Geokodiranje ${i+1}/${n}: ${name}…`,
    importedCustomers: n => `✅ Uvezeno ${n} mušterija`,
    foundRows: n => `Pronađeno ${n} redova`,
    outOfSerbia: '⚠️ Molimo postavite lokacije unutar Srbije',
    mapNotLoaded: 'Mapa nije učitana — molimo sačekajte trenutak i pokušajte ponovo.',
    addDepotFirst: 'Molimo dodajte barem jedan depo.',
    addCustomerFirst: 'Molimo dodajte barem jednu mušteriju.',
    optimizationError: 'Greška optimizacije: ',
    routesCalculated: '✅ Rute izračunate',
    phase1: 'Faza 1: preuzimanje matrice putnih rastojanja…',
    phase1short: 'Faza 1: matrica puteva…',
    phase2: 'Faza 2: optimizacija ruta…',
    srcHere: '🟢 Saobraćaj uživo (HERE) — rute i prikaz mape',
    srcOsrm: '🔵 Putna rastojanja (OSRM)',
    srcHaversine: '🟠 Procena pravom linijom',
    optimisedFor: 'Optimizovano za: ',
    constraints: 'Ograničenja: ',
    selectAtLeastOne: '⚠️ Izaberite barem jedno — podrazumevano gorivo + plate',
    minimising: 'Minimizacija: ',
    capDisabled: (off, plural) => `⚠️ ${off} ogr${plural} isključeno — preopterećenja dozvoljena`,
    totalType: (cnt, cap, wStr) => `Ukupno tipa: ${cnt}m³${wStr}`,
    unlimitedWeight: ' · neograničena težina',
    fleetSummary: (vehs, plural, total) => `🚛 ${vehs} vozilo${plural} · Ukupni kapacitet: ${total} m³`,
    noVehicles: 'Nema podešenih vozila — kliknite na karticu',
    configureDash: name => `Podesi — ${name}`,
    captureMaps: '📸 Snimanje mapa…',
    captureVehicle: (i, n) => `📸 Vozilo ${i}/${n}…`,
    buildingPDF: '📄 Generisanje PDF-a…',
    exportPDF: '📄 Izvezi PDF',
    pdfError: 'Greška PDF-a: ',
    errorPrefix: 'Greška: ',
    objLabels: { fuel:'⛽ Troškovi goriva', wages:'👷 Plate', distance:'📏 Rastojanje', vehicles:'🚛 Vozila' },
    owLabels: { fuel:'⛽ Troškovi goriva', wages:'👷 Plate', distance:'📏 Rastojanje', vehicles:'🚛 Vozila' },
    srcBadges: {
      here:      { label: '🟢 Saobraćaj uživo (HERE) — rute i prikaz mape', color: '#22c55e' },
      osrm:      { label: '🔵 Putna rastojanja (OSRM)', color: '#3b82f6' },
      haversine: { label: '🟠 Procena pravom linijom', color: '#f97316' },
    },
    language: 'Jezik',
    langEn: 'English',
    langSr: 'Srpski',
    clickToConfigure: 'Kliknite za podešavanje',
    fuelConsumption: 'Potrošnja goriva',
    unservedWarning: (n, names) => `⚠️ ${n} mušterija nije opsluž.: ${names}`,
    stopsLabel: n => `${n} stanica`,
    splitDelivery: (part, total) => `Podeljena isporuka: deo ${part} od ${total}`,
    minUnloading: min => `${min} min istovar`,
    volLoad: 'Zapreminski teret / kapacitet',
    weightLoad: eff => `Težinski teret / kapacitet (efektivna potrošnja: ${eff} L/100km)`,
  }
};

let currentLang = localStorage.getItem('grps_lang') || 'en';
function t(key) { return TRANSLATIONS[currentLang][key] ?? TRANSLATIONS['en'][key] ?? key; }

function setLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('grps_lang', lang);
  applyLanguage();
}

function applyLanguage() {
  // Update <html lang>
  document.documentElement.lang = currentLang;

  // Update all data-i18n elements in HTML
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const attr = el.getAttribute('data-i18n-attr');
    const val = t(key);
    if (attr) el.setAttribute(attr, val);
    else el.textContent = val;
  });

  // Update language toggle button state
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === currentLang);
  });

  // Re-render dynamic elements that build their own HTML
  renderFleetCards();
  updateFleetFooter();
  updateObjHint();
  updateConstraintHint();

  // Update results placeholder if visible
  const ph = document.getElementById('results-placeholder');
  if (ph && !ph.classList.contains('hidden')) ph.textContent = t('runOptimizationHint');

  // Update OSRM warning text
  const mw = document.getElementById('matrix-warning');
  if (mw) mw.innerHTML = t('osrmWarning');

  // Update address input placeholder
  const ai = document.getElementById('address-input');
  if (ai) ai.placeholder = t('searchAddress');

  // Re-draw results if we have them
  if (state && state.lastResult) {
    drawResults(state.lastResult);
  }
}

// ─── STATE ────────────────────────────────────────────────────────────────────
const state = {
  depots: [],       // multi-depot: array of {lat,lng,name,time_window}
  customers: [],
  mode: 'depot',
  markers: {},
  routeLayers: {},
  vehicleVisible: {},
  simMarkers: [],
  simTimers: [],
  lastResult: null,
  excelRows: null,
  fleet: [
    // weight_capacity in kg (0 = unlimited). Realistic max payloads:
    // Small Van ~800 kg, Medium Van ~1400 kg, Large Van ~2500 kg
    { name:'Small Van',    emoji:'🚐', capacity: 5.0,  weight_capacity:  800, count:1, color:'#3b82f6', fuel_consumption: 8.0  },
    { name:'Medium Van',   emoji:'🚐', capacity: 12.0, weight_capacity: 1400, count:1, color:'#f97316', fuel_consumption: 11.0 },
    { name:'Large Van',    emoji:'🚐', capacity: 20.0, weight_capacity: 2500, count:1, color:'#ef4444', fuel_consumption: 15.0 },
  ],
  // Package type weights in kg — Type 1: small parcel 5 kg, Type 2: medium box 15 kg, Type 3: large 30 kg
  pkg_weights_kg: [5.0, 15.0, 30.0],
  // Package type sizes in m³
  pkg_sizes: [0.10, 0.30, 0.60],
  editingFleetIdx: null,
};

const VEHICLE_COLORS = ['#e74c3c','#3498db','#2ecc71','#f39c12',
                        '#9b59b6','#1abc9c','#e67e22','#e84342'];

// ─── MAP INIT ─────────────────────────────────────────────────────────────────
let map;
window.addEventListener('DOMContentLoaded', () => {
  map = L.map('map', {
    zoomControl: true,
    minZoom: 7, maxZoom: 18,
    maxBounds: [[41.85, 18.8], [46.2, 23.0]],
    maxBoundsViscosity: 0.85
  }).setView([44.0, 21.0], 8);

  const layers = {
    '🗺 Standard':  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        { attribution:'© OpenStreetMap', maxZoom:19, crossOrigin: true }),
    '⬜ Grey':  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        { attribution:'© CARTO', maxZoom:20, crossOrigin: true }),
    '🌑 Dark':   L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        { attribution:'© CARTO', maxZoom:20, crossOrigin: true }),
  };
  layers['🌑 Dark'].addTo(map);
  L.control.layers(layers, {}, { position:'topright' }).addTo(map);

  map.on('click', onMapClick);

  renderFleetCards();
  updateFleetFooter();

  document.getElementById('algo-select').addEventListener('change', function() {
    document.getElementById('alns-opts').style.display =
      this.value.startsWith('Model 1') ? '' : 'none';
  });

  // Apply saved language on load
  applyLanguage();
});

// Serbia bounding box
const SERBIA_BBOX = { minLat:41.85, maxLat:46.2, minLng:18.8, maxLng:23.0 };
function inSerbia(lat, lng) {
  return lat >= SERBIA_BBOX.minLat && lat <= SERBIA_BBOX.maxLat &&
         lng >= SERBIA_BBOX.minLng && lng <= SERBIA_BBOX.maxLng;
}

// ─── MAP CLICK ────────────────────────────────────────────────────────────────
function onMapClick(e) {
  const { lat, lng } = e.latlng;
  if (!inSerbia(lat, lng)) {
    const st = document.getElementById('geocode-status');
    st.textContent = t('outOfSerbia');
    setTimeout(() => { st.textContent = ''; }, 3000);
    return;
  }
  if (state.mode === 'depot') {
    placeDepot(lat, lng, 'Depot');
  } else {
    const pkg1 = parseInt(document.getElementById('pkg-count-1').value) || 0;
    const pkg2 = parseInt(document.getElementById('pkg-count-2').value) || 0;
    const pkg3 = parseInt(document.getElementById('pkg-count-3').value) || 0;
    const twS    = document.getElementById('tw-start').value || '09:00';
    const twE    = document.getElementById('tw-end').value   || '17:00';
    const unload = parseInt(document.getElementById('unloading-time').value) || 10;
    placeCustomer(lat, lng, null, [pkg1, pkg2, pkg3], { start: twS, end: twE }, unload);
  }
}

function setMode(mode, btn) {
  state.mode = mode;
  document.querySelectorAll('.mode-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const opts = document.getElementById('customer-opts');
  mode === 'customer' ? opts.classList.remove('hidden') : opts.classList.add('hidden');
}

// ─── PLACE MARKERS ────────────────────────────────────────────────────────────
function safeRemove(layer) {
  try { if (layer && map && map.hasLayer && map.hasLayer(layer)) map.removeLayer(layer); } catch(e) {}
}

// Depot colours: each depot gets a distinct warm colour
const DEPOT_COLOR = '#1a1a1a';  // all depots are black

function placeDepot(lat, lng, name) {
  if (typeof L === 'undefined') { alert(t('mapNotLoaded')); return; }
  const depotIdx = state.depots.length;
  const id = 'depot_' + depotIdx;
  const depotName = name || (depotIdx === 0 ? 'Depot' : `Depot ${depotIdx + 1}`);
  const depotObj = { id, idx: depotIdx, lat, lng, name: depotName,
                     time_window:{ start:'08:00', end:'18:00' }, packages:0 };
  state.depots.push(depotObj);

  const icon = L.divIcon({
    className: '',
    html: `<div style="
      width:24px;height:24px;border-radius:50%;
      background:${DEPOT_COLOR};border:3px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,.5);
      display:flex;align-items:center;justify-content:center;
      font-size:12px;line-height:1;color:#fff;font-weight:700;">${depotIdx + 1}</div>`,
    iconSize:[24,24], iconAnchor:[12,12], popupAnchor:[0,-14]
  });
  const marker = L.marker([lat, lng], { icon, draggable:true })
    .addTo(map)
    .bindPopup(`<b>${depotName}</b><br>${lat.toFixed(5)}, ${lng.toFixed(5)}`);
  marker.on('dragend', e => {
    const p = e.target.getLatLng();
    depotObj.lat = p.lat; depotObj.lng = p.lng;
    marker.getPopup().setContent(`<b>${depotName}</b><br>${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`);
  });
  marker.on('contextmenu', () => removeDepot(id));
  state.markers[id] = marker;
  renderLocationsList();
}

function placeCustomer(lat, lng, name, pkg_counts, time_window, unloading_time) {
  if (typeof L === 'undefined') { alert(t('mapNotLoaded')); return; }
  const id = 'customer_' + Date.now() + '_' + state.customers.length;
  const num = state.customers.length + 1;
  const cname = name || `Customer ${num}`;
  // Normalise pkg_counts to array of 3
  if (!Array.isArray(pkg_counts)) pkg_counts = [pkg_counts || 1, 0, 0];
  while (pkg_counts.length < 3) pkg_counts.push(0);
  const vol = calcVolume(pkg_counts);
  const unload = Math.max(1, parseInt(unloading_time) || 10);
  const cust = { id, lat, lng, name: cname, pkg_counts, time_window,
                 unloading_time: unload, customer_id: num };
  state.customers.push(cust);

  const icon = L.divIcon({
    className: '',
    html: `<div style="
      width:26px;height:26px;border-radius:50%;
      background:#3498db;border:3px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,.45);
      color:#fff;font-size:11px;font-weight:700;
      display:flex;align-items:center;justify-content:center;
      line-height:1;">${num}</div>`,
    iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-16]
  });
  const marker = L.marker([lat, lng], { icon, draggable:true })
    .addTo(map)
    .bindPopup(`<b>${cname}</b><br>📦 P1:${pkg_counts[0]} P2:${pkg_counts[1]} P3:${pkg_counts[2]}<br>📐 ${vol.toFixed(2)} m³ · ⚖️ ${calcWeight(pkg_counts).toFixed(1)} kg<br>⏱ ${time_window.start}–${time_window.end}<br>🔧 Unload: ${unload}min`);
  marker.on('dragend', e => {
    const p = e.target.getLatLng();
    cust.lat = p.lat; cust.lng = p.lng;
  });
  marker.on('contextmenu', () => removeCustomer(id));
  state.markers[id] = marker;
  renderLocationsList();
}

function removeDepot(id) {
  // If no id given, remove the last depot
  if (!id) {
    if (state.depots.length === 0) return;
    id = state.depots[state.depots.length - 1].id;
  }
  safeRemove(state.markers[id]);
  delete state.markers[id];
  state.depots = state.depots.filter(d => d.id !== id);
  // Re-number remaining depots
  state.depots.forEach((d, i) => { d.idx = i; });
  renderLocationsList();
}

function removeCustomer(id) {
  safeRemove(state.markers[id]);
  delete state.markers[id];
  state.customers = state.customers.filter(c => c.id !== id);
  renumberCustomers();
}

function clearAll() {
  Object.values(state.markers).forEach(m => safeRemove(m));
  state.markers = {};
  state.depots = [];
  state.customers = [];
  clearRoutes();
  renderLocationsList();
  resetResults();
}

// ─── LOCATIONS LIST ───────────────────────────────────────────────────────────
function renderLocationsList() {
  const el = document.getElementById('locations-list');
  let html = '';
  state.depots.forEach((dep, i) => {
    html += `<div class="loc-item">
      <span class="loc-dot" style="background:${DEPOT_COLOR}"></span>
      <span class="loc-name">🏠 ${esc(dep.name)}</span>
      <button class="loc-del" onclick="removeDepot('${dep.id}')">✕</button>
    </div>`;
  });
  state.customers.forEach(c => {
    html += `<div class="loc-item">
      <span class="loc-dot customer"></span>
      <span class="loc-name">👤 C${c.customer_id}: ${esc(c.name)} [${calcVolume(c.pkg_counts).toFixed(2)}m³]</span>
      <button class="loc-del" onclick="removeCustomer('${c.id}')">✕</button>
    </div>`;
  });
  if (!html) html = '<div style="font-size:10px;color:var(--muted);padding:4px 0">No locations added</div>';
  if (state.depots.length > 1) {
    html += `<div style="font-size:10px;color:var(--accent);padding:3px 0 0">✅ ${state.depots.length} depots — optimizer picks best depot per vehicle</div>`;
  }
  el.innerHTML = html;
}

// ─── GEOCODING ────────────────────────────────────────────────────────────────
async function geocodeAddress() {
  const addr = document.getElementById('address-input').value.trim();
  if (!addr) return;
  const st = document.getElementById('geocode-status');
  st.textContent = t('searching');
  try {
    const res = await fetch('/api/geocode', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ address: addr })
    });
    const data = await res.json();
    if (data.ok) {
      st.textContent = t('found');
      if (state.mode === 'depot') {
        placeDepot(data.lat, data.lng, addr.split(',')[0].trim());
      } else {
        const pkg1 = parseInt(document.getElementById('pkg-count-1').value) || 0;
        const pkg2 = parseInt(document.getElementById('pkg-count-2').value) || 0;
        const pkg3 = parseInt(document.getElementById('pkg-count-3').value) || 0;
        const twS    = document.getElementById('tw-start').value || '09:00';
        const twE    = document.getElementById('tw-end').value   || '17:00';
        const unload = parseInt(document.getElementById('unloading-time').value) || 10;
        placeCustomer(data.lat, data.lng, addr.split(',')[0].trim(), [pkg1, pkg2, pkg3], { start:twS, end:twE }, unload);
      }
      map.setView([data.lat, data.lng], 15);
      document.getElementById('address-input').value = '';
    } else {
      st.textContent = `❌ ${data.error}`;
    }
  } catch(e) {
    st.textContent = `❌ ${e.message}`;
  }
}
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.activeElement.id === 'address-input') geocodeAddress();
});

// ─── VOLUME HELPER ────────────────────────────────────────────────────────────
function calcVolume(pkg_counts) {
  if (!Array.isArray(pkg_counts)) return 0;
  return pkg_counts.reduce((s, cnt, k) => s + (cnt || 0) * (state.pkg_sizes[k] || 0), 0);
}

function updatePkgSizes() {
  const s1 = parseFloat(document.getElementById('pkg-size-1')?.value) || 0.10;
  const s2 = parseFloat(document.getElementById('pkg-size-2')?.value) || 0.30;
  const s3 = parseFloat(document.getElementById('pkg-size-3')?.value) || 0.60;
  state.pkg_sizes = [s1, s2, s3];
  const el = document.getElementById('pkg-sizes-summary');
  if (el) el.textContent = `Sizes: ${s1.toFixed(3)} · ${s2.toFixed(3)} · ${s3.toFixed(3)} m³`;
  updatePkgVolHint();
  updateFleetFooter();
}

function updatePkgWeights() {
  const w1 = parseFloat(document.getElementById('pkg-weight-1')?.value) || 5.0;
  const w2 = parseFloat(document.getElementById('pkg-weight-2')?.value) || 15.0;
  const w3 = parseFloat(document.getElementById('pkg-weight-3')?.value) || 30.0;
  state.pkg_weights_kg = [w1, w2, w3];
  const el = document.getElementById('pkg-weights-summary');
  if (el) el.textContent = `Weights: ${w1.toFixed(1)} · ${w2.toFixed(1)} · ${w3.toFixed(1)} kg`;
}

function calcWeight(pkg_counts) {
  if (!Array.isArray(pkg_counts)) return 0;
  return pkg_counts.reduce((s, cnt, k) => s + (cnt || 0) * (state.pkg_weights_kg[k] || 0), 0);
}

function updatePkgVolHint() {
  const p1 = parseInt(document.getElementById('pkg-count-1')?.value) || 0;
  const p2 = parseInt(document.getElementById('pkg-count-2')?.value) || 0;
  const p3 = parseInt(document.getElementById('pkg-count-3')?.value) || 0;
  const vol = calcVolume([p1, p2, p3]);
  const el = document.getElementById('pkg-vol-hint');
  if (el) el.textContent = `${vol.toFixed(3)} m³`;
}

// ─── EXCEL IMPORT ─────────────────────────────────────────────────────────────
async function importExcel(input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const st = document.getElementById('geocode-status');
  st.textContent = t('parsingExcel');
  try {
    const res = await fetch('/api/import_excel', { method:'POST', body: fd });
    const data = await res.json();
    input.value = '';
    if (!data.ok) { st.textContent = `❌ ${data.error}`; return; }
    st.textContent = t('foundRows')(data.rows.length);
    state.excelRows = data.rows;
    showExcelPreview(data.rows);
  } catch(e) {
    st.textContent = `❌ ${e.message}`;
  }
}

function showExcelPreview(rows) {
  let th = '<tr><th>#</th><th>Customer</th><th>Address</th><th>Pkg#1</th><th>Pkg#2</th><th>Pkg#3</th><th>Vol (m³)</th><th>Unload (min)</th><th>Time</th></tr>';
  let td = rows.map((r,i) => {
    const pc = r.pkg_counts || [r.packages||0, 0, 0];
    const vol = calcVolume(pc).toFixed(2);
    return `<tr>
      <td>${i+1}</td><td>${esc(r.name)}</td><td>${esc(r.address)}</td>
      <td>${pc[0]}</td><td>${pc[1]}</td><td>${pc[2]}</td><td>${vol}</td>
      <td>${r.unloading_time ?? 10}</td>
      <td>${r.time_window.start}–${r.time_window.end}</td>
    </tr>`;
  }).join('');
  document.getElementById('excel-table-wrap').innerHTML =
    `<table class="excel-preview-table"><thead>${th}</thead><tbody>${td}</tbody></table>`;
  document.getElementById('excel-modal').classList.remove('hidden');
}

function renumberCustomers() {
  state.customers.forEach((c, i) => {
    const num = i + 1;
    c.customer_id = num;
    const marker = state.markers[c.id];
    if (marker) {
      const icon = L.divIcon({
        className: '',
        html: `<div style="
          width:26px;height:26px;border-radius:50%;
          background:#3498db;border:3px solid #fff;
          box-shadow:0 2px 6px rgba(0,0,0,.45);
          color:#fff;font-size:11px;font-weight:700;
          display:flex;align-items:center;justify-content:center;
          line-height:1;">${num}</div>`,
        iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-16]
      });
      marker.setIcon(icon);
    }
  });
  renderLocationsList();
}

async function confirmExcelImport() {
  closeExcelModal();
  const rows = state.excelRows || [];
  const st = document.getElementById('geocode-status');
  let importedCount = 0;
  for (let i=0; i<rows.length; i++) {
    const r = rows[i];
    st.textContent = t('geocodingProgress')(i, rows.length, r.name);
    try {
      const res = await fetch('/api/geocode', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ address: r.address })
      });
      const data = await res.json();
      if (data.ok) {
        const pc = r.pkg_counts || [r.packages||1, 0, 0];
        placeCustomer(data.lat, data.lng, r.name, pc, r.time_window, r.unloading_time || 10);
        importedCount++;
      }
    } catch(e) {}
    await sleep(1100); // Nominatim rate limit
  }
  renumberCustomers();
  st.textContent = t('importedCustomers')(importedCount);
}
function closeExcelModal() { document.getElementById('excel-modal').classList.add('hidden'); }

// ─── FLEET MANAGEMENT ────────────────────────────────────────────────────────
function renderFleetCards() {
  const emojis = ['🚐','🚚','🚛','🏎','🚜','🚑'];
  let html = state.fleet.map((v,i) => `
    <div class="fleet-card" onclick="openFleetModal(${i})" title="${t('clickToConfigure')}">
      <span class="fc-emoji">${v.emoji || emojis[i%emojis.length]}</span>
      <span class="fc-name">${esc(v.name)}</span>
      <span class="fc-count" style="color:${v.color}">×${v.count}</span>
      <span class="fc-cap">${v.capacity} m³</span>
      <span class="fc-fuel" title="${t('fuelConsumption')}">${v.fuel_consumption} L/100km</span>
      <span class="fc-weight" title="${t('weightCapacity')}">${v.weight_capacity > 0 ? v.weight_capacity + ' kg' : '∞ kg'}</span>
    </div>`).join('');
  document.getElementById('fleet-cards').innerHTML = html;
}

function updateFleetFooter() {
  const total = state.fleet.reduce((s,v) => s + v.count * v.capacity, 0);
  const vehs  = state.fleet.reduce((s,v) => s + v.count, 0);
  const el    = document.getElementById('fleet-footer');
  el.textContent = total > 0
    ? t('fleetSummary')(vehs, vehs!==1?'s':'', total.toFixed(1))
    : t('noVehicles');
}

function openFleetModal(idx) {
  state.editingFleetIdx = idx;
  const v = state.fleet[idx];
  document.getElementById('modal-title').textContent = t('configureDash')(v.name);
  document.getElementById('modal-count').value      = v.count;
  document.getElementById('modal-cap').value        = v.capacity;
  document.getElementById('modal-weight-cap').value = v.weight_capacity ?? 0;
  document.getElementById('modal-fuel').value       = v.fuel_consumption ?? 10;
  updateModalHint();
  document.getElementById('fleet-modal').classList.remove('hidden');
}

function updateModalHint() {
  const cnt  = parseFloat(document.getElementById('modal-count').value)||0;
  const cap  = parseFloat(document.getElementById('modal-cap').value)||0;
  const wCap = parseFloat(document.getElementById('modal-weight-cap')?.value)||0;
  const wStr = wCap > 0 ? ` · ${(cnt*wCap).toLocaleString()} kg total` : t('unlimitedWeight');
  document.getElementById('modal-hint').textContent =
    t('totalType')((cnt*cap).toFixed(1), cap, wStr);
}


function applyFleetModal() {
  const idx = state.editingFleetIdx;
  if (idx === null) return;
  state.fleet[idx].count            = parseInt(document.getElementById('modal-count').value)||0;
  state.fleet[idx].capacity         = parseFloat(document.getElementById('modal-cap').value)||5.0;
  state.fleet[idx].weight_capacity  = parseFloat(document.getElementById('modal-weight-cap').value)||0;
  state.fleet[idx].fuel_consumption = parseFloat(document.getElementById('modal-fuel').value)||10;
  closeFleetModal();
  renderFleetCards();
  updateFleetFooter();
}
function closeFleetModal() {
  document.getElementById('fleet-modal').classList.add('hidden');
  state.editingFleetIdx = null;
}

// ─── OBJECTIVE SELECTOR ──────────────────────────────────────────────────────
function getObjWeights() {
  return {
    fuel:     document.getElementById('obj-fuel')?.checked     ?? true,
    wages:    document.getElementById('obj-wages')?.checked    ?? true,
    distance: document.getElementById('obj-distance')?.checked ?? false,
    vehicles: document.getElementById('obj-vehicles')?.checked ?? false,
  };
}

function updateObjHint() {
  const ow = getObjWeights();
  const labels = t('objLabels');
  const active = Object.entries(ow)
    .filter(([, v]) => v)
    .map(([k]) => labels[k]);
  const hint = document.getElementById('obj-hint');
  if (!hint) return;
  if (active.length === 0) {
    hint.textContent = t('selectAtLeastOne');
    hint.style.color = '#e74c3c';
  } else {
    hint.textContent = t('minimising') + active.join(' + ');
    hint.style.color = 'var(--accent)';
  }
}

function updateConstraintHint() {
  const volOn = document.getElementById('use-vol-cap')?.checked ?? true;
  const wtOn  = document.getElementById('use-wt-cap')?.checked ?? true;
  const hint  = document.getElementById('constraint-hint');
  if (!hint) return;
  if (!volOn || !wtOn) {
    const off = [!volOn && '📐 volume', !wtOn && '⚖️ weight'].filter(Boolean).join(' & ');
    hint.textContent = t('capDisabled')(off, (!volOn && !wtOn) ? 's' : '');
    hint.style.color = '#e74c3c';
    hint.style.display = 'block';
  } else {
    hint.style.display = 'none';
  }
}

// ─── OPTIMIZATION ────────────────────────────────────────────────────────────
async function runOptimize() {
  if (state.depots.length === 0) { alert(t('addDepotFirst')); return; }
  if (state.customers.length < 1) { alert(t('addCustomerFirst')); return; }

  clearRoutes();
  resetResults();
  stopSimulation();

  const btn = document.getElementById('optimize-btn');
  const pw  = document.getElementById('progress-wrap');
  const routingBanner = document.getElementById('routing-source-banner');
  if (routingBanner) routingBanner.style.display = 'none';
  btn.disabled = true;
  pw.classList.remove('hidden');
  setProgress(10, t('phase1'));

  const payload = {
    depots:    state.depots,
    customers: state.customers,
    fleet:     state.fleet,
    pkg_sizes:      state.pkg_sizes,
    pkg_weights_kg: state.pkg_weights_kg,
    obj_weights:    getObjWeights(),
    algorithm: document.getElementById('algo-select').value,
    use_time_windows:    document.getElementById('use-tw').checked,
    use_volume_capacity: document.getElementById('use-vol-cap').checked,
    use_weight_capacity: document.getElementById('use-wt-cap').checked,
    max_iterations:   parseInt(document.getElementById('max-iter').value)||500,
    temperature:      parseFloat(document.getElementById('temperature').value)||150,
  };

  try {
    // Fake progress during server call
    let prog = 10;
    const ticker = setInterval(() => {
      prog = Math.min(prog + 3, 85);
      setProgress(prog, prog < 40 ? t('phase1short') : t('phase2'));
    }, 800);

    const res = await fetch('/api/optimize', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    clearInterval(ticker);
    const data = await res.json();

    if (!data.ok) {
      alert(t('optimizationError') + (data.error||'Unknown'));
      btn.disabled = false;
      pw.classList.add('hidden');
      return;
    }

    const srcBadges = t('srcBadges');
    const src     = data.matrix_source || 'osrm';
    const badge   = srcBadges[src] || srcBadges.osrm;
    const srcMsg  = data.matrix_msg ? ` · ${data.matrix_msg}` : '';
    setProgress(100, t('routesCalculated') + srcMsg);

    // Show routing source banner below the progress bar
    const routingBanner = document.getElementById('routing-source-banner');
    if (routingBanner) {
      routingBanner.textContent = badge.label;
      routingBanner.style.color = badge.color;
      routingBanner.style.display = 'block';
    }
    state.lastResult = data;
    document.getElementById('geocode-status').style.color = '';
    drawResults(data);
    drawRoutes(data);
    renderLegend(data);

    document.getElementById('simulate-btn').disabled = false;
    document.getElementById('pdf-btn').disabled = false;
  } catch(e) {
    alert(t('errorPrefix') + e.message);
  } finally {
    btn.disabled = false;
    setTimeout(() => pw.classList.add('hidden'), 2000);
  }
}

function setProgress(pct, msg) {
  document.getElementById('progress-bar-fill').style.width = pct + '%';
  document.getElementById('progress-label').textContent = msg;
}

// ─── DRAW ROUTES ON MAP ───────────────────────────────────────────────────────
function drawRoutes(data) {
  // Reset all customer markers back to default blue before colouring served ones
  state.customers.forEach(c => {
    const marker = state.markers[c.id];
    if (marker) {
      const icon = L.divIcon({
        className: '',
        html: `<div style="
          width:26px;height:26px;border-radius:50%;
          background:#3498db;border:3px solid #fff;
          box-shadow:0 2px 6px rgba(0,0,0,.45);
          color:#fff;font-size:11px;font-weight:700;
          display:flex;align-items:center;justify-content:center;
          line-height:1;">${c.customer_id}</div>`,
        iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-16]
      });
      marker.setIcon(icon);
    }
  });

  // Highlight unserved customers in red with a warning icon
  const servedNames = new Set(
    (data.vehicle_routes || []).flatMap(vr => (vr.stops || []).map(s => s.name))
  );
  state.customers.forEach(c => {
    if (!servedNames.has(c.name)) {
      const marker = state.markers[c.id];
      if (marker) {
        const icon = L.divIcon({
          className: '',
          html: `<div style="
            width:26px;height:26px;border-radius:50%;
            background:#e74c3c;border:3px solid #fff;
            box-shadow:0 2px 6px rgba(0,0,0,.45);
            color:#fff;font-size:13px;font-weight:700;
            display:flex;align-items:center;justify-content:center;
            line-height:1;">!</div>`,
          iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-16]
        });
        marker.setIcon(icon);
        marker.setPopupContent(`<b>${esc(c.name)}</b><br>⚠️ Not served — capacity or time window infeasible`);
      }
    }
  });

  // Show warning banner if any customers are unserved
  const unserved = data.unserved_customers || [];
  if (unserved.length > 0) {
    const st = document.getElementById('geocode-status');
    st.textContent = t('unservedWarning')(unserved.length, unserved.join(', '));
    st.style.color = '#e74c3c';
  }

  data.vehicle_routes.forEach(vr => {
    if (!vr.geometry || vr.geometry.length < 2) return;
    const latlngs = vr.geometry.map(([lng, lat]) => [lat, lng]);
    const layer = L.polyline(latlngs, {
      color: vr.color, weight: 4, opacity: 0.85, smoothFactor: 1
    }).addTo(map);
    state.routeLayers[vr.vehicle_id] = layer;
    state.vehicleVisible[vr.vehicle_id] = true;

    // Update each customer marker: popup with schedule + dot colour = vehicle colour
    (vr.stops || []).forEach(stop => {
      const custEntry = state.customers.find(c => c.name === stop.name);
      if (custEntry && state.markers[custEntry.id]) {
        const flag = stop.violation > 0 ? ` ⚠️ +${stop.violation}m late`
                   : stop.wait > 0      ? ` ⏳ wait ${stop.wait}m` : ' ✅';
        const pc = stop.pkg_counts || [stop.packages||0, 0, 0];
        state.markers[custEntry.id].setPopupContent(
          `<b>${esc(stop.name)}</b><br>` +
          `📦 P1:${pc[0]} P2:${pc[1]} P3:${pc[2]}<br>` +
          `📐 ${calcVolume(pc).toFixed(2)} m³<br>` +
          `🕐 Arrives: <b>${stop.arrival}</b><br>` +
          `🚪 Departs: ${stop.depart}<br>` +
          `⏱ Window: ${stop.tw_start}–${stop.tw_end}${flag}`
        );
        try {
          const el = state.markers[custEntry.id].getElement();
          if (el) { const dot = el.querySelector('div'); if (dot) dot.style.background = vr.color; }
        } catch(e) {}
      }
    });
  });
  // Fit map to routes + all depot markers
  try {
    const routeLayers = Object.values(state.routeLayers).filter(l => l);
    const depotLayers = state.depots.map(d => state.markers[d.id]).filter(m => m);
    const combined = [...routeLayers, ...depotLayers];
    if (combined.length > 0) {
      const group = L.featureGroup(combined);
      const bounds = group.getBounds();
      if (bounds && bounds.isValid()) map.fitBounds(bounds, { padding:[40,40] });
    }
  } catch(e) { console.warn('fitBounds:', e); }
}

function clearRoutes() {
  Object.values(state.routeLayers).forEach(l => safeRemove(l));
  state.routeLayers = {};
  state.vehicleVisible = {};
}

// ─── RESULTS PANEL ───────────────────────────────────────────────────────────
function drawResults(data) {
  document.getElementById('results-placeholder').classList.add('hidden');
  document.getElementById('results-summary').classList.remove('hidden');

  document.getElementById('r-dist').textContent = data.total_distance.toFixed(1);
  document.getElementById('r-fuel').textContent = (data.total_fuel ?? 0).toFixed(1);
  document.getElementById('r-time').textContent =
    `${data.total_time_h}h${data.total_time_m}m`;
  document.getElementById('r-pkgs').textContent = (data.total_volume ?? data.total_packages ?? 0).toFixed(2) + ' m³';
  document.getElementById('r-vehs').textContent = data.vehicle_routes.length;

  // ── Fleet-wide capacity utilisation ──────────────────────────────────────
  const routes = data.vehicle_routes || [];
  const totalVolUsed = routes.reduce((s, vr) => s + (vr.volume_used  ?? 0), 0);
  const totalVolCap  = routes.reduce((s, vr) => s + (vr.volume_capacity ?? 0), 0);
  const totalWtUsed  = routes.reduce((s, vr) => s + (vr.weight_used  ?? 0), 0);
  const totalWtCap   = routes.reduce((s, vr) => s + (vr.weight_capacity ?? 0), 0);

  function pctColor(pct) {
    if (pct >= 90) return '#ef4444';   // red   — very full
    if (pct >= 70) return '#f97316';   // orange — high
    if (pct >= 40) return '#22c55e';   // green  — healthy
    return 'var(--muted)';             // grey   — low utilisation
  }

  const volPctEl = document.getElementById('r-vol-pct');
  if (volPctEl) {
    if (totalVolCap > 0) {
      const pct = Math.round(totalVolUsed / totalVolCap * 100);
      volPctEl.textContent = pct + '%';
      volPctEl.style.color = pctColor(pct);
      volPctEl.title = `${totalVolUsed.toFixed(2)} m³ used of ${totalVolCap.toFixed(1)} m³ total capacity`;
    } else {
      volPctEl.textContent = '—';
    }
  }

  const wtPctEl = document.getElementById('r-wt-pct');
  if (wtPctEl) {
    if (totalWtCap > 0) {
      const pct = Math.round(totalWtUsed / totalWtCap * 100);
      wtPctEl.textContent = pct + '%';
      wtPctEl.style.color = pctColor(pct);
      wtPctEl.title = `${totalWtUsed.toFixed(0)} kg used of ${totalWtCap.toLocaleString()} kg total capacity`;
    } else {
      wtPctEl.textContent = '—';
    }
  }
  document.getElementById('r-fuel-cost').textContent = (data.total_fuel_cost_rsd ?? 0).toLocaleString();
  document.getElementById('r-wage-cost').textContent = (data.total_wage_cost_rsd ?? 0).toLocaleString();
  document.getElementById('r-total-cost').textContent = (data.total_cost_rsd ?? 0).toLocaleString();

  // Show which objective was active during this run
  const owLabels = t('owLabels');
  const ow = data.obj_weights || { fuel: true, wages: true };
  const activeObj = Object.entries(ow).filter(([,v]) => v).map(([k]) => owLabels[k]).join(' + ');
  const objEl = document.getElementById('r-objective');
  if (objEl) objEl.textContent = activeObj ? t('optimisedFor') + activeObj : '';

  // Show active constraint info
  const constraintEl = document.getElementById('r-constraints');
  if (constraintEl) {
    const cList = [];
    if (data.use_volume_capacity !== false) cList.push('📐 Volume cap');
    else cList.push('<span style="color:var(--accent);text-decoration:line-through">📐 Volume cap</span>');
    if (data.use_weight_capacity !== false) cList.push('⚖️ Weight cap');
    else cList.push('<span style="color:var(--accent);text-decoration:line-through">⚖️ Weight cap</span>');
    constraintEl.innerHTML = t('constraints') + cList.join(' · ');
  }

  let html = '';
  data.vehicle_routes.forEach(vr => {
    const stopsHtml = (vr.stops||[]).map((s,i) => {
      const flag = s.violation > 0
        ? `<span class="stop-flag viol">⚠️+${s.violation}m</span>`
        : s.wait > 0
        ? `<span class="stop-flag">⏳${s.wait}m</span>`
        : '';
      const pc = s.pkg_counts || [s.packages||0, 0, 0];
      const pkgTip = `P1:${pc[0]} P2:${pc[1]} P3:${pc[2]}`;
      const splitBadge = s.split
        ? `<span style="background:#f97316;color:#fff;font-size:9px;padding:1px 4px;border-radius:3px;margin-left:2px" title="${t('splitDelivery')(s.split_part, s.split_total)}">✂️ ${s.split_part}/${s.split_total}</span>`
        : '';
      return `<div class="stop-row">
        <span class="stop-num">${i+1}.</span>
        <span class="stop-name" title="${esc(s.name)}">${esc(s.name.substring(0,18))}</span>${splitBadge}
        <span class="stop-time">${s.arrival}</span>
        <span class="stop-svc" title="${t('minUnloading')(s.service_time ?? 10)}">+${s.service_time ?? 10}m</span>
        <span style="color:var(--muted);font-size:10px">[${s.tw_start}–${s.tw_end}]</span>
        <span style="color:var(--accent);font-size:10px" title="${pkgTip}">📦${pkgTip}</span>
        ${flag}
      </div>`;
    }).join('');
    const depotRow = vr.depot_name
      ? `<div class="veh-depot-row">🏠 ${esc(vr.depot_name)}</div>` : '';
    const fuelBadge = vr.fuel_used != null
      ? `<span class="veh-fuel" title="${vr.fuel_consumption} L/100km">⛽ ${vr.fuel_used.toFixed(1)}L</span>`
      : '';
    const volUsed = vr.volume_used ?? vr.packages ?? 0;
    const volCap  = vr.volume_capacity ?? vr.capacity ?? 0;
    const volBadge = volUsed != null
      ? `<span class="veh-fuel" title="${t('volLoad')}">📐 ${parseFloat(volUsed).toFixed(2)}/${parseFloat(volCap).toFixed(1)}m³</span>`
      : '';
    const wUsed = vr.weight_used ?? 0;
    const wCap  = vr.weight_capacity ?? 0;
    const wCapStr = wCap > 0 ? `/${wCap}kg` : '/∞';
    const weightBadge = `<span class="veh-fuel" title="${t('weightLoad')(vr.effective_fuel_consumption ?? vr.fuel_consumption ?? '?')}">⚖️ ${wUsed.toFixed(0)}${wCapStr}</span>`;
    html += `<div class="veh-card" id="vcard-${vr.vehicle_id}">
      <div class="veh-card-header" onclick="toggleVehCard(${vr.vehicle_id})">
        <span class="veh-dot" style="background:${vr.color}"></span>
        <span class="veh-name">${esc(vr.type)} #${vr.vehicle_id+1}</span>
        <span class="veh-meta">${vr.num_customers} ${currentLang === 'sr' ? 'stan.' : 'stops'} · ${vr.distance.toFixed(1)}km ${fuelBadge} ${volBadge} ${weightBadge}</span>
        <span class="veh-meta" style="color:var(--muted);font-size:10px">⛽ ${(vr.fuel_cost_rsd??0).toLocaleString()} + 👷 ${(vr.wage_cost_rsd??0).toLocaleString()} = <b>${(vr.total_cost_rsd??0).toLocaleString()} RSD</b></span>
        <span class="veh-chevron">▼</span>
      </div>
      ${depotRow}
      <div class="veh-stops">${stopsHtml}</div>
    </div>`;
  });
  document.getElementById('vehicle-results').innerHTML = html;
}

function toggleVehCard(vid) {
  document.getElementById('vcard-'+vid).classList.toggle('open');
}

function resetResults() {
  document.getElementById('results-placeholder').classList.remove('hidden');
  document.getElementById('results-placeholder').textContent = t('runOptimizationHint');
  document.getElementById('results-summary').classList.add('hidden');
  document.getElementById('vehicle-results').innerHTML = '';
  document.getElementById('legend-panel').classList.add('hidden');
  document.getElementById('legend-rows').innerHTML = '';
  document.getElementById('simulate-btn').disabled = true;
  document.getElementById('pdf-btn').disabled = true;
  ['r-vol-pct','r-wt-pct'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = '—'; el.style.color = ''; }
  });
  state.lastResult = null;
}

// ─── LEGEND ──────────────────────────────────────────────────────────────────
function renderLegend(data) {
  const panel = document.getElementById('legend-panel');
  const rows  = document.getElementById('legend-rows');
  if (!data.vehicle_routes.length) { panel.classList.add('hidden'); return; }
  panel.classList.remove('hidden');

  rows.innerHTML = data.vehicle_routes.map(vr => {
    const depotSub = vr.depot_name
      ? `<span style="display:block;font-size:9px;color:var(--muted)">🏠 ${esc(vr.depot_name)}</span>` : '';
    return `
    <div class="legend-row" id="leg-${vr.vehicle_id}" onclick="toggleRoute(${vr.vehicle_id})">
      <span class="legend-swatch" style="background:${vr.color}"></span>
      <span class="legend-label">${esc(vr.type)} #${vr.vehicle_id+1}${depotSub}</span>
      <span class="legend-eye">👁</span>
    </div>`;
  }).join('');
}

function toggleRoute(vid) {
  const visible = state.vehicleVisible[vid];
  const layer   = state.routeLayers[vid];
  const row     = document.getElementById('leg-'+vid);
  if (visible) {
    safeRemove(layer);
    row.classList.add('hidden-route');
    state.vehicleVisible[vid] = false;
  } else {
    if (layer && !map.hasLayer(layer)) layer.addTo(map);
    row.classList.remove('hidden-route');
    state.vehicleVisible[vid] = true;
  }
}

function toggleAllRoutes() {
  const allVis = Object.values(state.vehicleVisible).every(v => v);
  Object.keys(state.vehicleVisible).forEach(vid => {
    const layer = state.routeLayers[vid];
    if (allVis) {
      safeRemove(layer);
      state.vehicleVisible[vid] = false;
      const row = document.getElementById('leg-'+vid);
      if (row) row.classList.add('hidden-route');
    } else {
      if (layer && !map.hasLayer(layer)) layer.addTo(map);
      state.vehicleVisible[vid] = true;
      const row = document.getElementById('leg-'+vid);
      if (row) row.classList.remove('hidden-route');
    }
  });
}

// ─── SIMULATION ───────────────────────────────────────────────────────────────
function startSimulation() {
  if (!state.lastResult) return;
  stopSimulation();

  const data = state.lastResult;
  const speedFactor = parseInt(document.getElementById('sim-speed')?.value || '200');

  data.vehicle_routes.forEach((vr, vi) => {
    if (!vr.geometry || vr.geometry.length < 2) return;
    const coords = vr.geometry.map(([lng, lat]) => [lat, lng]);
    const color  = vr.color;

    // Create moving dot
    const el = document.createElement('div');
    el.className = 'sim-marker';
    el.style.background = color;
    const icon = L.divIcon({ html: el, className:'', iconSize:[16,16], iconAnchor:[8,8] });
    const marker = L.marker(coords[0], { icon, zIndexOffset: 1000 }).addTo(map);
    state.simMarkers.push(marker);

    let step = 0;
    function advance() {
      if (step >= coords.length) return;
      marker.setLatLng(coords[step]);
      step++;
      const t = setTimeout(advance, speedFactor + vi * 40);
      state.simTimers.push(t);
    }
    const t0 = setTimeout(advance, vi * 500);
    state.simTimers.push(t0);
  });
}

function stopSimulation() {
  state.simTimers.forEach(t => clearTimeout(t));
  state.simTimers = [];
  (state.simMarkers || []).forEach(m => safeRemove(m));
  state.simMarkers = [];
}

// ─── PDF ──────────────────────────────────────────────────────────────────────

/** Capture the current Leaflet map view into a base64 PNG string (or null). */
async function captureMapCanvas() {
  try {
    const mapEl   = document.getElementById('map');
    const mapRect = mapEl.getBoundingClientRect();
    const W = Math.round(mapRect.width);
    const H = Math.round(mapRect.height);
    const merged = document.createElement('canvas');
    merged.width  = W;
    merged.height = H;
    const ctx = merged.getContext('2d');

    // Draw tile canvases
    const canvases = mapEl.querySelectorAll('canvas');
    for (const c of canvases) {
      if (c.width > 0 && c.height > 0) {
        const r = c.getBoundingClientRect();
        ctx.drawImage(c, r.left - mapRect.left, r.top - mapRect.top, r.width, r.height);
      }
    }

    // Draw SVG overlays (markers, polylines)
    const svgEls = mapEl.querySelectorAll('svg');
    for (const svg of svgEls) {
      const r   = svg.getBoundingClientRect();
      const xml = new XMLSerializer().serializeToString(svg);
      const blob = new Blob([xml], {type: 'image/svg+xml'});
      const url  = URL.createObjectURL(blob);
      await new Promise((res) => {
        const img = new Image();
        img.onload = () => {
          ctx.drawImage(img, r.left - mapRect.left, r.top - mapRect.top, r.width, r.height);
          URL.revokeObjectURL(url);
          res();
        };
        img.onerror = () => { URL.revokeObjectURL(url); res(); };
        img.src = url;
      });
    }

    return merged.toDataURL('image/png').split(',')[1];
  } catch(e) {
    console.warn('Map capture failed (non-fatal):', e);
    return null;
  }
}

/**
 * Spin up a fully independent, offscreen Leaflet map for a single vehicle,
 * draw only its route + stop markers, capture it, then tear it down.
 * This never touches the main map at all.
 */
async function captureVehicleMap(vr) {
  if (!vr.geometry || vr.geometry.length < 2) return null;

  const W = 900, H = 500;

  // 1. Container stacked ON TOP of the page but hidden behind a high-z overlay
  //    Must be on-screen so the browser actually loads tiles.
  const overlay = document.createElement('div');
  overlay.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,0.01);z-index:9998;pointer-events:none;';
  document.body.appendChild(overlay);

  const container = document.createElement('div');
  container.style.cssText =
    `position:fixed;left:0;top:0;width:${W}px;height:${H}px;z-index:9999;pointer-events:none;opacity:0;`;
  document.body.appendChild(container);

  // 2. Fresh Leaflet map
  const vMap = L.map(container, { zoomControl:false, attributionControl:false, animate:false });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, crossOrigin: true,
  }).addTo(vMap);

  // 3. Route polyline
  const latlngs = vr.geometry.map(([lng, lat]) => [lat, lng]);
  L.polyline(latlngs, { color: vr.color, weight: 5, opacity: 0.9, smoothFactor: 1 }).addTo(vMap);

  // 4. Depot marker
  L.circleMarker(latlngs[0], {
    radius: 10, color: '#fff', weight: 3, fillColor: '#1a1a1a', fillOpacity: 1,
  }).addTo(vMap);

  // 5. Stop circle markers (SVG — always captured)
  (vr.stops || []).forEach((stop) => {
    if (stop.lat == null || stop.lng == null) return;
    L.circleMarker([stop.lat, stop.lng], {
      radius: 11, color: '#fff', weight: 2.5,
      fillColor: vr.color, fillOpacity: 1,
    }).addTo(vMap);
  });

  // 6. Fit to route bounds
  vMap.fitBounds(L.latLngBounds(latlngs), { padding: [40, 40], animate: false });

  // 7. Wait for tiles — use tileload event with a timeout fallback
  await new Promise(resolve => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    vMap.once('idle', finish);
    // fallback: wait 3s regardless
    setTimeout(finish, 3000);
  });
  // Extra frame settle
  await sleep(400);

  // 8. Composite canvas
  let b64 = null;
  try {
    const merged = document.createElement('canvas');
    merged.width  = W;
    merged.height = H;
    const ctx = merged.getContext('2d');
    const rect = container.getBoundingClientRect();

    // Tile canvases
    for (const c of container.querySelectorAll('canvas')) {
      if (c.width > 0 && c.height > 0) {
        const r = c.getBoundingClientRect();
        ctx.drawImage(c, r.left - rect.left, r.top - rect.top, r.width, r.height);
      }
    }

    // SVG overlays (polyline + circles)
    for (const svg of container.querySelectorAll('svg')) {
      const r   = svg.getBoundingClientRect();
      const xml = new XMLSerializer().serializeToString(svg);
      const blob = new Blob([xml], { type: 'image/svg+xml' });
      const url  = URL.createObjectURL(blob);
      await new Promise(res => {
        const img = new Image();
        img.onload  = () => { ctx.drawImage(img, r.left - rect.left, r.top - rect.top, r.width, r.height); URL.revokeObjectURL(url); res(); };
        img.onerror = () => { URL.revokeObjectURL(url); res(); };
        img.src = url;
      });
    }

    // Draw numbers on top of each stop circle
    ctx.font = 'bold 11px Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    (vr.stops || []).forEach((stop, idx) => {
      if (stop.lat == null || stop.lng == null) return;
      const pt = vMap.latLngToContainerPoint([stop.lat, stop.lng]);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(String(idx + 1), pt.x, pt.y);
    });

    b64 = merged.toDataURL('image/png').split(',')[1];
  } catch(e) {
    console.warn(`Vehicle ${vr.vehicle_id} map capture failed:`, e);
  }

  // 9. Teardown
  vMap.remove();
  document.body.removeChild(container);
  document.body.removeChild(overlay);

  return b64;
}

async function generatePDF() {
  if (!state.lastResult) return;
  const d = state.lastResult;

  const btn = document.getElementById('pdf-btn');
  btn.disabled = true;
  btn.textContent = t('captureMaps');

  // ── Capture full overview map ──────────────────────────────────────────────
  // First fit map to show all routes
  try {
    const allLayers = Object.values(state.routeLayers).filter(l => l);
    if (allLayers.length) {
      map.fitBounds(L.featureGroup(allLayers).getBounds(), { padding:[40,40], animate:false });
      await sleep(500);
    }
  } catch(e) {}
  const mapImageB64 = await captureMapCanvas();

  // ── Capture per-vehicle maps ───────────────────────────────────────────────
  const vehicleMaps = {};
  for (const vr of d.vehicle_routes) {
    btn.textContent = t('captureVehicle')(vr.vehicle_id + 1, d.vehicle_routes.length);
    vehicleMaps[vr.vehicle_id] = await captureVehicleMap(vr);
    await sleep(200);
  }

  // Restore full overview view after captures
  try {
    const allLayers = Object.values(state.routeLayers).filter(l => l);
    if (allLayers.length) {
      map.fitBounds(L.featureGroup(allLayers).getBounds(), { padding:[40,40], animate:false });
    }
  } catch(e) {}

  btn.textContent = t('buildingPDF');

  // Attach per-vehicle map images to each vehicle_route object
  const vehicleRoutesWithMaps = d.vehicle_routes.map(vr => ({
    ...vr,
    vehicle_map_image: vehicleMaps[vr.vehicle_id] || null,
  }));

  const payload = {
    algorithm:            d.algorithm,
    total_distance:       d.total_distance,
    total_fuel:           d.total_fuel,
    total_fuel_cost_rsd:  d.total_fuel_cost_rsd,
    total_wage_cost_rsd:  d.total_wage_cost_rsd,
    total_cost_rsd:       d.total_cost_rsd,
    fuel_price_rsd_l:     d.fuel_price_rsd_l,
    driver_wage_rsd_h:    d.driver_wage_rsd_h,
    total_time_h:         d.total_time_h,
    total_time_m:         d.total_time_m,
    total_customers:      state.customers.length,
    total_packages:       d.total_volume ?? d.total_packages,
    total_volume:         d.total_volume,
    pkg_sizes:            state.pkg_sizes,
    pkg_weights_kg:       state.pkg_weights_kg,
    obj_weights:          d.obj_weights,
    vehicles_used:        d.vehicle_routes.length,
    fleet:                state.fleet,
    vehicle_routes:       vehicleRoutesWithMaps,
    map_image:            mapImageB64,
  };

  try {
    const res  = await fetch('/api/pdf', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `route_report_${Date.now()}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) {
    alert(t('pdfError') + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = t('exportPDF');
  }
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── RESIZABLE PANELS ────────────────────────────────────────────────────────
(function initResize() {
  const MIN_SIDEBAR = 180;
  const MIN_MAP     = 200;

  function makeResizable(handleId, getSidebar, getEdge) {
    const handle = document.getElementById(handleId);
    if (!handle) return;

    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      handle.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      // Disable pointer events on map iframe/canvas during drag
      const mapEl = document.getElementById('map');
      if (mapEl) mapEl.style.pointerEvents = 'none';

      const onMove = ev => {
        const sidebar  = getSidebar();
        const layout   = document.querySelector('.layout');
        const layoutRect = layout.getBoundingClientRect();
        const newWidth = getEdge(ev.clientX, layoutRect);
        const clamped  = Math.max(MIN_SIDEBAR, newWidth);

        // Also ensure map doesn't shrink below minimum
        const mapArea   = document.getElementById('map-area');
        const leftSide  = document.getElementById('sidebar-left');
        const rightSide = document.getElementById('sidebar-right');
        const leftW     = parseInt(leftSide.style.width)  || leftSide.offsetWidth;
        const rightW    = parseInt(rightSide.style.width) || rightSide.offsetWidth;
        const handles   = 10; // 2 × 5px handles
        const available = layoutRect.width - handles;

        let mapW;
        if (sidebar === leftSide) {
          mapW = available - clamped - rightW;
        } else {
          mapW = available - leftW - clamped;
        }
        if (mapW < MIN_MAP) return;

        sidebar.style.width = clamped + 'px';
        // Invalidate Leaflet size after resize
        if (window.map) map.invalidateSize();
      };

      const onUp = () => {
        handle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        const mapEl = document.getElementById('map');
        if (mapEl) mapEl.style.pointerEvents = '';
        if (window.map) map.invalidateSize();
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  }

  makeResizable(
    'resize-left',
    () => document.getElementById('sidebar-left'),
    (clientX, rect) => clientX - rect.left
  );

  makeResizable(
    'resize-right',
    () => document.getElementById('sidebar-right'),
    (clientX, rect) => rect.right - clientX
  );
})();
