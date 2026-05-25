/* ═══ GRPS WEB — FRONTEND JS ═════════════════════════════════════════════════
   Full port of the PyQt5 desktop app to browser JS.
   Covers: Leaflet map, fleet management, route optimization (via Flask API),
           OSRM routing, results panel, legend, route simulation, PDF, Excel.
══════════════════════════════════════════════════════════════════════════════ */
// ─── BACKEND URL ──────────────────────────────────────────────────────────────
// In local-backend mode this is set by the <script> in index.html to the
// Cloudflare tunnel URL (e.g. https://xxxx.trycloudflare.com).
// Falls back to "" (same-origin) so the app still works when run locally.
const _B = (window.BACKEND_URL || "").replace(/\/$/, "");
/** Prepend backend URL to an API path. */
function apiUrl(path) { return _B + path; }

// Wrap fetch so every cross-origin API call automatically sends session cookies.
// Without credentials:'include', the browser never attaches the session cookie
// on Render-frontend → Cloudflare-tunnel-backend requests, causing login_required
// to fire and return an HTML redirect that breaks res.json().
;(function () {
  const _orig = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    opts = opts || {};
    if (typeof url === "string" && _B !== "" && url.startsWith(_B)) {
      opts = Object.assign({}, opts, { credentials: "include" });
    }
    return _orig(url, opts);
  };
})();


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
    excelColumns: 'Required: Customer, Address, Packages#1, Packages#2, Packages#3, Time — Optional: Lat, Lng (skips geocoding)',
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
    infeasibleWarning: '🚫 No feasible solution found — hard constraints (capacity, time windows) cannot all be satisfied. Try relaxing constraints or adding vehicles.',
    stopsLabel: n => `${n} stops`,
    splitDelivery: (part, total) => `Split delivery: part ${part} of ${total}`,
    minUnloading: min => `${min} min unloading`,
    volLoad: 'Volumetric load / capacity',
    weightLoad: eff => `Weight load / capacity (effective fuel: ${eff} L/100km)`,
    volSizeHint: 'Volumetric size per package type',
    weightHint: 'Weight per package type (kg) — used for vehicle weight capacity constraints and load-dependent fuel calculation',
    sizesLabel: (s1, s2, s3) => `Sizes: ${s1} · ${s2} · ${s3} m³`,
    weightsLabel: (w1, w2, w3) => `Weights: ${w1} · ${w2} · ${w3} kg`,
    titleSmallParcel: 'Typical small parcel: 3–8 kg',
    titleMediumBox: 'Typical medium box: 10–20 kg',
    titleLargeItem: 'Typical large item: 20–50 kg',
    titleWeightCap: 'Max payload weight in kg. Set 0 for unlimited.',
    titleFuelBase: 'Base fuel consumption when empty. Increases linearly with load.',
    fuelLoadNote: pct => `⛽ Fuel usage is load-dependent: +${pct}% per 1 000 kg payload`,
    fuelLoadExample: (pct, base) => `e.g. ${base} L/100km empty → ${(base*(1+pct/100)).toFixed(1)} L at 1 000 kg, ${(base*(1+3*pct/100)).toFixed(1)} L at 3 000 kg`,
    fuelLoadFactorLabel: '📦 Fuel +% per 1 000 kg',
    volUsedOf: (used, cap) => `${used} m³ used of ${cap} m³ total capacity`,
    wtUsedOf: (used, cap) => `${used} kg used of ${cap} kg total capacity`,
    unloadPopup: min => `Unload: ${min}min`,
    costParams: '💰 Cost Parameters',
    minLoadTitle: '📦 Minimum departure load',
    minLoadHint: 'Vehicles leaving the depot must carry at least this % of their capacity. Set 0 to disable.',
    minVolPct: 'Min vol load (%)',
    minWtPct: 'Min weight load (%)',
    minLoadBadge: (vp, wp) => `min ${vp}% vol${wp > 0 ? ` · ${wp}% wt` : ''}`,
    costParamsHint: 'Adjust to match your local fuel price and driver wage',
    costParamsNote: '⛽ Fuel also increases +3% per 1 000 kg payload',
    fuelPriceLabel: '⛽ Fuel price (RSD/L)',
    driverWageLabel: '👷 Driver wage (RSD/h)',
    advancedParams: '🔬 Advanced Parameters',
    advancedParamsHint: 'Fine-tune the routing engine and solver penalties. Leave defaults unless you know what you\'re doing.',
    advancedParamsNote: 'Changes take effect on the next optimization run.',
    spatialFilterTitle: '📡 Spatial Filtering',
    kNearestLabel: 'K-Nearest neighbours',
    sentinelFactorLabel: 'Sentinel factor',
    overlapPenaltyTitle: '🗺️ Route Overlap Penalty',
    overlapThresholdLabel: 'Overlap threshold (km)',
    overlapWeightLabel: 'Overlap penalty (RSD/shared km)',
    solverPenaltiesTitle: '⚖️ Solver Penalties',
    distRsdPerKmLabel: 'Distance cost (RSD/km)',
    twPenaltyRsdLabel: 'TW violation penalty (RSD/min)',
    alnsCoolingLabel: 'ALNS cooling rate',
    histBlendTitle: '🕑 Historical Traffic Blending',
    depTimeLabel: 'Planned departure time',
    histBlendWeightLabel: 'Blend weight (0 = live, 1 = historical)',
    routeHistory: '🗄️ Route History',
    routeHistoryHint: 'Routes saved automatically after each optimization run.',
    refreshHistory: '🔄 Refresh',
    routeDetail: 'Route Detail',
    loading: 'Loading…',
    close: 'Close',
    deleteRoute: '🗑 Delete',
    historyEmpty: 'No saved routes yet. Run an optimization to save routes automatically.',
    historyError: '⚠️ Could not load history.',
    historyNoDB: '⚠️ Database not connected — set DATABASE_URL on Render.',
    historyDeleteConfirm: 'Delete this route permanently?',
    historyDeleted: '✅ Route deleted.',
    historyDeleteError: '⚠️ Delete failed: ',
    historyColDate: 'Date',
    historyColVehicle: 'Vehicle',
    historyColAlgo: 'Algorithm',
    historyColDist: 'Distance',
    historyColCost: 'Total cost',
    historyColStops: 'Stops',
    historyColBy: 'Saved by',
    historyViewBtn: 'View',
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
    excelColumns: 'Obavezno: Customer, Address, Packages#1, Packages#2, Packages#3, Time — Opciono: Lat, Lng (preskače geokodiranje)',
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
    infeasibleWarning: '🚫 Nije pronađeno izvodljivo rešenje — tvrda ograničenja (kapacitet, vremenski okviri) ne mogu sva biti zadovoljena. Pokušajte da olabavite ograničenja ili dodate vozila.',
    stopsLabel: n => `${n} stanica`,
    splitDelivery: (part, total) => `Podeljena isporuka: deo ${part} od ${total}`,
    minUnloading: min => `${min} min istovar`,
    volLoad: 'Zapreminski teret / kapacitet',
    weightLoad: eff => `Težinski teret / kapacitet (efektivna potrošnja: ${eff} L/100km)`,
    volSizeHint: 'Zapremina po tipu paketa',
    weightHint: 'Težina po tipu paketa (kg) — koristi se za ograničenja nosivosti i potrošnju goriva',
    sizesLabel: (s1, s2, s3) => `Veličine: ${s1} · ${s2} · ${s3} m³`,
    weightsLabel: (w1, w2, w3) => `Težine: ${w1} · ${w2} · ${w3} kg`,
    titleSmallParcel: 'Tipičan mali paket: 3–8 kg',
    titleMediumBox: 'Tipična srednja kutija: 10–20 kg',
    titleLargeItem: 'Tipičan veliki predmet: 20–50 kg',
    titleWeightCap: 'Maks. nosivost u kg. Postavite 0 za neograničeno.',
    titleFuelBase: 'Osnovna potrošnja goriva praznog vozila. Raste linearno sa teretom.',
    fuelLoadNote: pct => `⛽ Potrošnja zavisi od tereta: +${pct}% na svakih 1 000 kg`,
    fuelLoadExample: (pct, base) => `npr. ${base} L/100km prazno → ${(base*(1+pct/100)).toFixed(1)} L na 1 000 kg, ${(base*(1+3*pct/100)).toFixed(1)} L na 3 000 kg`,
    fuelLoadFactorLabel: '📦 Gorivo +% na 1 000 kg',
    volUsedOf: (used, cap) => `${used} m³ iskorišćeno od ${cap} m³ ukupnog kapaciteta`,
    wtUsedOf: (used, cap) => `${used} kg iskorišćeno od ${cap} kg ukupnog kapaciteta`,
    unloadPopup: min => `Istovar: ${min}min`,
    costParams: '💰 Parametri troškova',
    minLoadTitle: '📦 Minimalni teret pri polasku',
    minLoadHint: 'Vozilo mora imati najmanje ovaj % popunjenosti pre polaska iz depoa. Postavite 0 za isključivanje.',
    minVolPct: 'Min vol teret (%)',
    minWtPct: 'Min težinski teret (%)',
    minLoadBadge: (vp, wp) => `min ${vp}% vol${wp > 0 ? ` · ${wp}% tež` : ''}`,
    costParamsHint: 'Prilagodite lokalnoj ceni goriva i plati vozača',
    costParamsNote: '⛽ Gorivo raste +3% na svakih 1 000 kg tereta',
    fuelPriceLabel: '⛽ Cena goriva (RSD/L)',
    driverWageLabel: '👷 Plata vozača (RSD/h)',
    advancedParams: '🔬 Napredni parametri',
    advancedParamsHint: 'Fino podesite mašinu za rutiranje i kazne solvera. Ostavite podrazumevane vrednosti ako niste sigurni.',
    advancedParamsNote: 'Promene stupaju na snagu pri sledećoj optimizaciji.',
    spatialFilterTitle: '📡 Prostorno filtriranje',
    kNearestLabel: 'K-najbližih suseda',
    sentinelFactorLabel: 'Sentinel faktor',
    overlapPenaltyTitle: '🗺️ Kazna preklapanja ruta',
    overlapThresholdLabel: 'Prag preklapanja (km)',
    overlapWeightLabel: 'Kazna za preklapanje (RSD/deljeni km)',
    solverPenaltiesTitle: '⚖️ Kazne solvera',
    distRsdPerKmLabel: 'Trošak rastojanja (RSD/km)',
    twPenaltyRsdLabel: 'Kazna kršenja vremenskog okvira (RSD/min)',
    alnsCoolingLabel: 'ALNS stopa hlađenja',
    histBlendTitle: '🕑 Mešanje istorijskih podataka o saobraćaju',
    depTimeLabel: 'Planirano vreme polaska',
    histBlendWeightLabel: 'Težina mešanja (0 = živo, 1 = istorijsko)',
    routeHistory: '🗄️ Istorija ruta',
    routeHistoryHint: 'Rute se čuvaju automatski nakon svake optimizacije.',
    refreshHistory: '🔄 Osveži',
    routeDetail: 'Detalji rute',
    loading: 'Učitavanje…',
    close: 'Zatvori',
    deleteRoute: '🗑 Obriši',
    historyEmpty: 'Nema sačuvanih ruta. Pokrenite optimizaciju da automatski sačuvate rute.',
    historyError: '⚠️ Greška pri učitavanju istorije.',
    historyNoDB: '⚠️ Baza nije povezana — podesite DATABASE_URL na Renderu.',
    historyDeleteConfirm: 'Trajno obrisati ovu rutu?',
    historyDeleted: '✅ Ruta obrisana.',
    historyDeleteError: '⚠️ Greška pri brisanju: ',
    historyColDate: 'Datum',
    historyColVehicle: 'Vozilo',
    historyColAlgo: 'Algoritam',
    historyColDist: 'Rastojanje',
    historyColCost: 'Ukupni troškovi',
    historyColStops: 'Stanice',
    historyColBy: 'Sačuvao',
    historyViewBtn: 'Pregled',
  }
};

let currentLang = localStorage.getItem('grps_lang') || 'en';
function t(key) { return TRANSLATIONS[currentLang][key] ?? TRANSLATIONS['en'][key] ?? key; }

// ─── Current optimization job tracking ───────────────────────────────────────
let _currentJobId = null;

async function cancelCurrentJob() {
  if (!_currentJobId) return;
  const jobId = _currentJobId;
  console.log(`[GRPS] ✖ cancelling job ${jobId}`);
  try {
    const res  = await fetch(apiUrl(`/api/optimize/${jobId}/cancel`), { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      console.log(`[GRPS] cancel request accepted for job ${jobId}`);
      document.getElementById('cancel-job-btn').disabled = true;
      document.getElementById('cancel-job-btn').textContent = '⏳ Cancelling…';
      setProgress(0, '✖ Cancellation requested — waiting for solver to stop…');
    } else {
      console.warn(`[GRPS] cancel failed: ${data.error}`);
    }
  } catch (e) {
    console.warn(`[GRPS] cancel fetch error: ${e.message}`);
  }
}

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
  updatePkgSizes();
  updatePkgWeights();

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
  drivers: [],              // imported driver roster
  driverSelected: new Set(), // names of drivers checked as eligible
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

  // Redraw routes on zoom so shared-segment stripe width stays visually constant
  map.on('zoomend', () => {
    if (state.lastResult) {
      clearRoutes();
      drawRoutes(state.lastResult);
    }
  });

  renderFleetCards();
  updateFleetFooter();
  restorePanelStates();
  updateCostHint();

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

// Monotonic counter — guarantees unique IDs even after deletions + rapid re-adds
let _custSeq = 0;

function placeCustomer(lat, lng, name, pkg_counts, time_window, unloading_time) {
  if (typeof L === 'undefined') { alert(t('mapNotLoaded')); return; }
  const id = 'customer_' + (++_custSeq);
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
    .bindPopup(`<b>${cname}</b><br>📦 P1:${pkg_counts[0]} P2:${pkg_counts[1]} P3:${pkg_counts[2]}<br>📐 ${vol.toFixed(2)} m³ · ⚖️ ${calcWeight(pkg_counts).toFixed(1)} kg<br>⏱ ${time_window.start}–${time_window.end}<br>🔧 ${t('unloadPopup')(unload)}`);
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
      <span class="loc-name">👤 ${
        c.route_visit_num != null
          ? `<span style="color:${c.route_vehicle_color};font-weight:700">V${c.route_vehicle_num}:#${c.route_visit_num}</span>`
          : `C${c.customer_id}`
      }: ${esc(c.name)} [${calcVolume(c.pkg_counts).toFixed(2)}m³]</span>
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
    const res = await fetch(apiUrl('/api/geocode'), {
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
  if (el) el.textContent = t('sizesLabel')(s1.toFixed(3), s2.toFixed(3), s3.toFixed(3));
  updatePkgVolHint();
  updateFleetFooter();
}

function updatePkgWeights() {
  const w1 = parseFloat(document.getElementById('pkg-weight-1')?.value) || 5.0;
  const w2 = parseFloat(document.getElementById('pkg-weight-2')?.value) || 15.0;
  const w3 = parseFloat(document.getElementById('pkg-weight-3')?.value) || 30.0;
  state.pkg_weights_kg = [w1, w2, w3];
  const el = document.getElementById('pkg-weights-summary');
  if (el) el.textContent = t('weightsLabel')(w1.toFixed(1), w2.toFixed(1), w3.toFixed(1));
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
    const res = await fetch(apiUrl('/api/import_excel'), { method:'POST', body: fd });
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
  const hasCoords = rows.some(r => r.lat != null && r.lng != null);
  const coordCols = hasCoords ? '<th>Lat</th><th>Lng</th>' : '';
  let th = `<thead><tr><th>#</th><th>Customer</th><th>Address</th><th>Pkg#1</th><th>Pkg#2</th><th>Pkg#3</th><th>Vol (m³)</th><th>Unload (min)</th><th>Time</th>${coordCols}</tr></thead>`;
  let td = rows.map((r,i) => {
    const pc = r.pkg_counts || [r.packages||0, 0, 0];
    const vol = calcVolume(pc).toFixed(2);
    const coordCells = hasCoords
      ? `<td>${r.lat != null ? r.lat.toFixed(5) : '—'}</td><td>${r.lng != null ? r.lng.toFixed(5) : '—'}</td>`
      : '';
    const coordBadge = r.lat != null ? ' 📍' : '';
    return `<tr>
      <td>${i+1}</td><td>${esc(r.name)}${coordBadge}</td><td>${esc(r.address)}</td>
      <td>${pc[0]}</td><td>${pc[1]}</td><td>${pc[2]}</td><td>${vol}</td>
      <td>${r.unloading_time ?? 10}</td>
      <td>${r.time_window.start}–${r.time_window.end}</td>${coordCells}
    </tr>`;
  }).join('');
  document.getElementById('excel-table-wrap').innerHTML =
    `<table class="excel-preview-table">${th}<tbody>${td}</tbody></table>`;
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
    // If the row already has coordinates, skip the geocoding API call entirely
    if (r.lat != null && r.lng != null) {
      st.textContent = `📍 (${i+1}/${rows.length}) ${r.name}`;
      const pc = r.pkg_counts || [r.packages||1, 0, 0];
      placeCustomer(r.lat, r.lng, r.name, pc, r.time_window, r.unloading_time || 10);
      importedCount++;
      continue;
    }
    st.textContent = t('geocodingProgress')(i, rows.length, r.name);
    try {
      const res = await fetch(apiUrl('/api/geocode'), {
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
  let html = state.fleet.map((v,i) => {
    const minBadge = (v.min_vol_pct > 0 || v.min_wt_pct > 0)
      ? `<span class="fc-min-load" title="${t('minLoadTitle')}">▶${v.min_vol_pct}%${v.min_wt_pct > 0 ? '/'+v.min_wt_pct+'%' : ''}</span>`
      : '';
    return `
    <div class="fleet-card" onclick="openFleetModal(${i})" title="${t('clickToConfigure')}">
      <span class="fc-emoji">${v.emoji || emojis[i%emojis.length]}</span>
      <span class="fc-name">${esc(v.name)}</span>
      <span class="fc-count" style="color:${v.color}">×${v.count}</span>
      <span class="fc-cap">${v.capacity} m³</span>
      <span class="fc-fuel" title="${t('fuelConsumption')}">${v.fuel_consumption} L/100km</span>
      <span class="fc-weight" title="${t('weightCapacity')}">${v.weight_capacity > 0 ? v.weight_capacity + ' kg' : '∞ kg'}</span>
      ${minBadge}
    </div>`;
  }).join('');
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
  document.getElementById('modal-count').value        = v.count;
  document.getElementById('modal-cap').value          = v.capacity;
  document.getElementById('modal-weight-cap').value   = v.weight_capacity ?? 0;
  document.getElementById('modal-fuel').value         = v.fuel_consumption ?? 10;
  document.getElementById('modal-min-vol-pct').value  = v.min_vol_pct ?? 0;
  document.getElementById('modal-min-wt-pct').value   = v.min_wt_pct  ?? 0;
  updateModalHint();
  _refreshModalFuelNote(getCostParams().fuel_load_factor_pct);
  document.getElementById('fleet-modal').classList.remove('hidden');
}

function updateModalHint() {
  const cnt    = parseFloat(document.getElementById('modal-count').value)||0;
  const cap    = parseFloat(document.getElementById('modal-cap').value)||0;
  const wCap   = parseFloat(document.getElementById('modal-weight-cap')?.value)||0;
  const minVol = parseFloat(document.getElementById('modal-min-vol-pct')?.value)||0;
  const minWt  = parseFloat(document.getElementById('modal-min-wt-pct')?.value)||0;
  const wStr   = wCap > 0 ? ` · ${(cnt*wCap).toLocaleString()} kg total` : t('unlimitedWeight');
  let hint = t('totalType')((cnt*cap).toFixed(1), cap, wStr);
  if (minVol > 0 || minWt > 0) hint += `  ·  ${t('minLoadBadge')(minVol, minWt)}`;
  document.getElementById('modal-hint').textContent = hint;
}


function applyFleetModal() {
  const idx = state.editingFleetIdx;
  if (idx === null) return;
  state.fleet[idx].count            = parseInt(document.getElementById('modal-count').value)||0;
  state.fleet[idx].capacity         = parseFloat(document.getElementById('modal-cap').value)||5.0;
  state.fleet[idx].weight_capacity  = parseFloat(document.getElementById('modal-weight-cap').value)||0;
  state.fleet[idx].fuel_consumption = parseFloat(document.getElementById('modal-fuel').value)||10;
  state.fleet[idx].min_vol_pct      = parseFloat(document.getElementById('modal-min-vol-pct').value)||0;
  state.fleet[idx].min_wt_pct       = parseFloat(document.getElementById('modal-min-wt-pct').value)||0;
  closeFleetModal();
  renderFleetCards();
  updateFleetFooter();
}
function closeFleetModal() {
  document.getElementById('fleet-modal').classList.add('hidden');
  state.editingFleetIdx = null;
}

// ─── COLLAPSIBLE PANELS ───────────────────────────────────────────────────────
function togglePanel(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('collapsed');
  // persist state
  try {
    const states = JSON.parse(localStorage.getItem('grps_panels') || '{}');
    states[id] = el.classList.contains('collapsed');
    localStorage.setItem('grps_panels', JSON.stringify(states));
  } catch(e) {}
}

function restorePanelStates() {
  try {
    const states = JSON.parse(localStorage.getItem('grps_panels') || '{}');
    Object.entries(states).forEach(([id, collapsed]) => {
      const el = document.getElementById(id);
      if (el && collapsed) el.classList.add('collapsed');
    });
  } catch(e) {}
}

// ─── COST PARAMETERS ─────────────────────────────────────────────────────────
function getCostParams() {
  return {
    fuel_price_rsd_l:      parseFloat(document.getElementById('fuel-price-rsd')?.value)   || 200,
    driver_wage_rsd_h:     parseFloat(document.getElementById('driver-wage-rsd')?.value)   || 900,
    fuel_load_factor_pct:  parseFloat(document.getElementById('fuel-load-factor')?.value)  ?? 3,
  };
}

function updateCostHint() {
  const p = getCostParams();
  const el = document.getElementById('cost-hint');
  if (el) el.textContent = `${p.fuel_price_rsd_l} RSD/L · ${p.driver_wage_rsd_h} RSD/h · +${p.fuel_load_factor_pct}%/t`;
  // update the static note below the inputs
  const note = document.getElementById('cost-load-note');
  if (note) note.textContent = `⛽ ${t('fuelLoadFactorLabel')}: +${p.fuel_load_factor_pct}% per 1 000 kg`;
  // update the note inside the vehicle modal if it's open
  _refreshModalFuelNote(p.fuel_load_factor_pct);
}

function _refreshModalFuelNote(pct) {
  const noteEl    = document.getElementById('modal-fuel-load-note');
  const exampleEl = document.getElementById('modal-fuel-load-example');
  if (!noteEl || !exampleEl) return;
  const base = parseFloat(document.getElementById('modal-fuel')?.value) || 10;
  noteEl.textContent    = t('fuelLoadNote')(pct);
  exampleEl.textContent = t('fuelLoadExample')(pct, base);
}

// ─── ADVANCED PARAMETERS ─────────────────────────────────────────────────────
function getAdvancedParams() {
  return {
    k_nearest:            parseInt(document.getElementById('adv-k-nearest')?.value)        ?? 10,
    sentinel_factor:      parseFloat(document.getElementById('adv-sentinel-factor')?.value) ?? 2.5,
    overlap_threshold_km: parseFloat(document.getElementById('adv-overlap-threshold')?.value) ?? 3.0,
    overlap_weight_rsd:   parseFloat(document.getElementById('adv-overlap-weight')?.value)  ?? 500,
    dist_rsd_per_km:      parseFloat(document.getElementById('adv-dist-rsd-per-km')?.value) ?? 20,
    tw_penalty_rsd:       parseFloat(document.getElementById('adv-tw-penalty-rsd')?.value)  ?? 100,
    alns_cooling:         parseFloat(document.getElementById('adv-alns-cooling')?.value)    || 0.995,
    hist_blend_weight:    parseFloat(document.getElementById('adv-hist-blend-weight')?.value) || 0.5,
    departure_time:       document.getElementById('adv-dep-time')?.value || '',
  };
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
  const cancelBtn = document.getElementById('cancel-job-btn');
  const routingBanner = document.getElementById('routing-source-banner');
  if (routingBanner) routingBanner.style.display = 'none';
  btn.disabled = true;
  pw.classList.remove('hidden');
  if (cancelBtn) { cancelBtn.style.display = 'inline-block'; cancelBtn.disabled = false; cancelBtn.textContent = '✕ Cancel'; }
  setProgress(10, t('phase1'));

  const payload = {
    depots:    state.depots,
    customers: state.customers,
    fleet:     state.fleet,
    pkg_sizes:      state.pkg_sizes,
    pkg_weights_kg: state.pkg_weights_kg,
    obj_weights:    getObjWeights(),
    ...getCostParams(),
    algorithm: document.getElementById('algo-select').value,
    use_time_windows:    document.getElementById('use-tw').checked,
    use_volume_capacity: document.getElementById('use-vol-cap').checked,
    use_weight_capacity: document.getElementById('use-wt-cap').checked,
    max_iterations:   parseInt(document.getElementById('max-iter').value)||500,
    temperature:      parseFloat(document.getElementById('temperature').value)||150,
    advanced_params:  getAdvancedParams(),
    departure_time:   document.getElementById('adv-dep-time')?.value || '',
    ...getDriverPayloadExtras(),
  };

  console.log(`[GRPS] submitting optimize job — ${state.customers.length} customers, ${state.depots.length} depots`);

  try {
    // ── Step 1: submit job, get job_id immediately ──────────────────────────
    setProgress(5, t('phase1'));
    const submitRes = await fetch(apiUrl('/api/optimize'), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const submitData = await submitRes.json();
    if (!submitData.ok) {
      alert(t('optimizationError') + (submitData.error || 'Unknown'));
      btn.disabled = false;
      pw.classList.add('hidden');
      if (cancelBtn) cancelBtn.style.display = 'none';
      return;
    }
    const jobId = submitData.job_id;
    _currentJobId = jobId;
    console.log(`[GRPS] job submitted: ${jobId}`);

    // ── Step 2: poll /api/optimize/status/:job_id until done ───────────────
    // Progress bar ticks forward slowly; messaging flips at ~40 %
    let prog = 5;
    const ticker = setInterval(() => {
      prog = Math.min(prog + 2, 90);
      setProgress(prog, prog < 40 ? t('phase1short') : t('phase2'));
    }, 800);

    const POLL_INTERVAL_MS = 1500;
    const MAX_WAIT_MS      = 20 * 60 * 1000;   // 20 min hard client timeout
    const pollStart        = Date.now();

    const data = await new Promise((resolve, reject) => {
      const poll = async () => {
        if (Date.now() - pollStart > MAX_WAIT_MS) {
          reject(new Error('Optimization timed out after 20 minutes'));
          return;
        }
        try {
          const r = await fetch(apiUrl(`/api/optimize/status/${jobId}`));
          const d = await r.json();
          console.log(`[GRPS] poll job ${jobId.slice(0,8)}: status=${d.status}`);
          if (d.status === 'cancelled') {
            reject(new Error('Job was cancelled'));
            return;
          }
          if (!r.ok || d.status === 'error') {
            reject(new Error(d.error || 'Optimization failed on server'));
            return;
          }
          if (d.status === 'done') {
            resolve(d.result);
            return;
          }
          // still running — poll again
          setTimeout(poll, POLL_INTERVAL_MS);
        } catch (fetchErr) {
          reject(fetchErr);
        }
      };
      setTimeout(poll, POLL_INTERVAL_MS);
    });

    clearInterval(ticker);
    _currentJobId = null;

    if (!data.ok) {
      alert(t('optimizationError') + (data.error || 'Unknown'));
      btn.disabled = false;
      pw.classList.add('hidden');
      if (cancelBtn) cancelBtn.style.display = 'none';
      return;
    }

    console.log(`[GRPS] job ${jobId.slice(0,8)} done — `
      + `${data.vehicle_routes?.length} routes, dist=${data.total_distance} km, `
      + `cost=${data.total_cost_rsd} RSD, matrix=${data.matrix_source}`);

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

    // Infeasible solution: solver could not satisfy all hard constraints
    if (data.infeasible) {
      const st = document.getElementById('geocode-status');
      st.textContent = t('infeasibleWarning');
      st.style.color = '#e74c3c';
    }

    drawResults(data);
    drawRoutes(data);
    renderLegend(data);

    document.getElementById('simulate-btn').disabled = false;
    document.getElementById('pdf-btn').disabled = false;
  } catch(e) {
    _currentJobId = null;
    if (e.message === 'Job was cancelled') {
      setProgress(0, '✖ Job cancelled');
      console.log('[GRPS] job cancelled by user');
    } else {
      alert(t('errorPrefix') + e.message);
      console.error('[GRPS] optimization error:', e.message);
    }
  } finally {
    btn.disabled = false;
    if (cancelBtn) cancelBtn.style.display = 'none';
    setTimeout(() => pw.classList.add('hidden'), 2000);
  }
}

function setProgress(pct, msg) {
  document.getElementById('progress-bar-fill').style.width = pct + '%';
  document.getElementById('progress-label').textContent = msg;
}

// ─── DRAW ROUTES ──────────────────────────────────────────────────
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

  // Highlight unserved customers in red with a warning icon.
  // Count per-name so that if two customers share a name and only one stop is
  // served, the second is correctly flagged — not both marked served via Set.
  const _servedCount = {};
  (data.vehicle_routes || []).flatMap(vr => (vr.stops || []).map(s => s.name))
    .forEach(n => { _servedCount[n] = (_servedCount[n] || 0) + 1; });
  const _servedUsed = {};
  state.customers.forEach(c => {
    const available = _servedCount[c.name] || 0;
    const used      = _servedUsed[c.name]  || 0;
    const isServed  = used < available;
    _servedUsed[c.name] = used + (isServed ? 1 : 0);
    if (!isServed) {
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

  // ── Overlap detection & zoom-invariant alternating-color splitting ─────────
  // pixel-based dashArray shifts with zoom, so instead we split each shared
  // run geographically: slice the coordinate array into chunks of equal
  // geographic length (CHUNK_DEG), then assign each chunk to vehicles in
  // round-robin order. Each chunk is drawn as a short solid polyline in that
  // vehicle's color, stored in that vehicle's LayerGroup → toggle still works.
  // Because the slices are defined by coordinates, the 1/N split is exact at
  // every zoom level.
  //
  // Grid resolution: 1 cell ≈ 0.00025° ≈ 22–27 m at mid-European latitudes.
  const GRID_RES = 0.00025;
  function cellKey(lat, lng) {
    return `${Math.round(lat / GRID_RES)}_${Math.round(lng / GRID_RES)}`;
  }

  // Compute chunk size in degrees so stripes are always ~STRIPE_PX pixels wide
  // on screen, regardless of zoom level. We convert via Leaflet's CRS scale:
  //   metersPerPx = 156543.03 * cos(centerLat) / 2^zoom   (Web Mercator)
  //   degPerPx    = metersPerPx / 111320
  const STRIPE_PX = 20;  // target stripe width in screen pixels
  const zoom = map.getZoom();
  const centerLat = map.getCenter().lat;
  const metersPerPx = (156543.03392 * Math.cos(centerLat * Math.PI / 180)) / Math.pow(2, zoom);
  const degPerPx = metersPerPx / 111320;
  const CHUNK_DEG = STRIPE_PX * degPerPx;

  // Euclidean distance in degrees (fine for short segments)
  function segLen(a, b) {
    const dlat = b[0] - a[0], dlng = b[1] - a[1];
    return Math.sqrt(dlat * dlat + dlng * dlng);
  }

  // Interpolate between two [lat,lng] points at fraction t ∈ [0,1]
  function interp(a, b, t) {
    return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
  }

  // Slice a polyline (array of [lat,lng]) into equal-length geographic chunks.
  // Uses cumulative arc length so each chunk is exactly chunkLen degrees long.
  function slicePolylineClean(pts, chunkLen) {
    const chunks = [];
    let cur = [pts[0]];
    let budget = chunkLen;

    for (let i = 0; i + 1 < pts.length; i++) {
      const A = pts[i], B = pts[i + 1];
      let d = segLen(A, B);
      let t0 = 0; // fraction of AB already consumed

      while (t0 < 1) {
        const tNeeded = budget / d;          // fraction of AB needed to fill budget
        if (t0 + tNeeded >= 1 - 1e-10) {
          // Rest of AB fits within budget
          cur.push(B);
          budget -= d * (1 - t0);
          t0 = 1;
          if (budget < 1e-10) {             // chunk exactly full
            if (cur.length >= 2) chunks.push(cur);
            cur = [B];
            budget = chunkLen;
          }
        } else {
          // Cut AB at t0+tNeeded
          const cutPt = interp(A, B, t0 + tNeeded);
          cur.push(cutPt);
          if (cur.length >= 2) chunks.push(cur);
          cur = [cutPt];
          t0 += tNeeded;
          budget = chunkLen;
        }
      }
    }
    if (cur.length >= 2) chunks.push(cur);
    return chunks;
  }

  // Build grid: cellKey → Set of vehicle_ids
  const cellVehicles = {};
  (data.vehicle_routes || []).forEach(vr => {
    if (!vr.geometry || vr.geometry.length < 2) return;
    const pts = vr.geometry.map(([lng, lat]) => [lat, lng]);
    for (let i = 0; i < pts.length - 1; i++) {
      const midLat = (pts[i][0] + pts[i+1][0]) / 2;
      const midLng = (pts[i][1] + pts[i+1][1]) / 2;
      const k = cellKey(midLat, midLng);
      if (!cellVehicles[k]) cellVehicles[k] = new Set();
      cellVehicles[k].add(vr.vehicle_id);
    }
  });

  // sharedCells: cellKey → sorted vehicle_id[] (only cells with 2+ vehicles)
  const sharedCells = {};
  Object.entries(cellVehicles).forEach(([k, vids]) => {
    if (vids.size > 1) sharedCells[k] = [...vids].sort((a, b) => a - b);
  });

  // Color lookup
  const vehicleColor = {};
  (data.vehicle_routes || []).forEach(vr => { vehicleColor[vr.vehicle_id] = vr.color; });

  // Accumulate sub-layers per vehicle before building LayerGroups
  const vehicleSubLayers = {};
  (data.vehicle_routes || []).forEach(vr => { vehicleSubLayers[vr.vehicle_id] = []; });

  data.vehicle_routes.forEach(vr => {
    if (!vr.geometry || vr.geometry.length < 2) return;
    const pts = vr.geometry.map(([lng, lat]) => [lat, lng]);

    // Split route into runs by sharing-group signature
    const runs = [];
    let currentSig = undefined;
    let currentRun = null;

    for (let i = 0; i < pts.length - 1; i++) {
      const midLat = (pts[i][0] + pts[i+1][0]) / 2;
      const midLng = (pts[i][1] + pts[i+1][1]) / 2;
      const k = cellKey(midLat, midLng);
      const sharingVids = sharedCells[k] || null;
      const sig = sharingVids ? sharingVids.join(',') : '';

      if (sig !== currentSig) {
        if (currentRun) currentRun.push(pts[i]);
        currentRun = [pts[i]];
        currentSig = sig;
        runs.push({ sig, sharingVids, latlngs: currentRun });
      }
      currentRun.push(pts[i + 1]);
    }

    runs.forEach(run => {
      if (run.latlngs.length < 2) return;

      if (!run.sharingVids) {
        // Solid, non-shared segment
        vehicleSubLayers[vr.vehicle_id].push(
          L.polyline(run.latlngs, { color: vr.color, weight: 4, opacity: 0.85, smoothFactor: 1 })
        );
      } else {
        // Shared segment: slice into geographic chunks and assign round-robin.
        // Each vehicle gets every N-th chunk → exact 1/N split at all zoom levels.
        const n = run.sharingVids.length;
        const chunks = slicePolylineClean(run.latlngs, CHUNK_DEG);
        chunks.forEach((chunkPts, ci) => {
          const vid = run.sharingVids[ci % n];
          if (vehicleSubLayers[vid] === undefined) return;
          vehicleSubLayers[vid].push(
            L.polyline(chunkPts, {
              color:        vehicleColor[vid],
              weight:       5,
              opacity:      0.95,
              smoothFactor: 0,   // no smoothing — preserve exact cut points
            })
          );
        });
      }
    });
  });

  // Build LayerGroups and add to map
  data.vehicle_routes.forEach(vr => {
    if (!vr.geometry || vr.geometry.length < 2) return;
    const group = L.layerGroup(vehicleSubLayers[vr.vehicle_id]).addTo(map);
    state.routeLayers[vr.vehicle_id] = group;
    state.vehicleVisible[vr.vehicle_id] = true;

    // Update each customer marker: popup with schedule + dot colour = vehicle colour
    // Build per-name queue so duplicate-named customers are matched in order
    const _nameQueue = {};
    state.customers.forEach(c => {
      (_nameQueue[c.name] = _nameQueue[c.name] || []).push(c);
    });
    (vr.stops || []).forEach((stop, stopIdx) => {
      const custEntry = (_nameQueue[stop.name] || []).shift();
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
        // Update marker icon to show visit-order number in vehicle colour
        const visitNum = stopIdx + 1;
        state.markers[custEntry.id].setIcon(L.divIcon({
          className: '',
          html: `<div style="
            width:26px;height:26px;border-radius:50%;
            background:${vr.color};border:3px solid #fff;
            box-shadow:0 2px 6px rgba(0,0,0,.45);
            color:#fff;font-size:11px;font-weight:700;
            display:flex;align-items:center;justify-content:center;
            line-height:1;">${visitNum}</div>`,
          iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-16]
        }));
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
      volPctEl.title = t('volUsedOf')(totalVolUsed.toFixed(2), totalVolCap.toFixed(1));
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
      wtPctEl.title = t('wtUsedOf')(totalWtUsed.toFixed(0), totalWtCap.toLocaleString());
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
  // Clear any stale unserved-customers warning from a previous run
  const st = document.getElementById('geocode-status');
  if (st) { st.textContent = ''; st.style.color = ''; }
  state.lastResult = null;
}

// ─── LEGEND ──────────────────────────────────────────────────────────────────
function renderLegend(data) {
  const panel = document.getElementById('legend-panel');
  const rows  = document.getElementById('legend-rows');
  if (!data.vehicle_routes.length) { panel.classList.add('hidden'); return; }
  panel.classList.remove('hidden');

  const overlapHint = data.vehicle_routes.length > 1
    ? `<div style="margin-top:8px;padding:5px 6px;border-radius:5px;
                   background:rgba(128,128,128,0.08);font-size:10px;
                   color:var(--muted);display:flex;align-items:center;gap:6px">
         <svg width="32" height="10" style="flex-shrink:0">
           <rect x="0" y="2" width="14" height="6" fill="#3b82f6" rx="1"/>
           <rect x="16" y="2" width="14" height="6" fill="#f97316" rx="1"/>
         </svg>
         Striped = shared road segment
       </div>` : '';

  rows.innerHTML = data.vehicle_routes.map(vr => {
    const depotSub = vr.depot_name
      ? `<span style="display:block;font-size:9px;color:var(--muted)">🏠 ${esc(vr.depot_name)}</span>` : '';
    return `
    <div class="legend-row" id="leg-${vr.vehicle_id}" onclick="toggleRoute(${vr.vehicle_id})">
      <span class="legend-swatch" style="background:${vr.color}"></span>
      <span class="legend-label">${esc(vr.type)} #${vr.vehicle_id+1}${depotSub}</span>
      <span class="legend-eye">👁</span>
    </div>`;
  }).join('') + overlapHint;
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
  const totalVehicles = d.vehicle_routes.length;
  for (let i = 0; i < d.vehicle_routes.length; i++) {
    const vr = d.vehicle_routes[i];
    btn.textContent = t('captureVehicle')(i + 1, totalVehicles);
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
    const res  = await fetch(apiUrl('/api/pdf'), {
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

// ─── ROUTE HISTORY ───────────────────────────────────────────────────────────

let _historyCurrentId = null;

async function loadRouteHistory() {
  const listEl   = document.getElementById('history-list');
  const statusEl = document.getElementById('history-status');
  if (!listEl) return;

  listEl.innerHTML = '';
  statusEl.style.display = 'block';
  statusEl.textContent = t('loading');

  try {
    const res  = await fetch(apiUrl('/api/routes'));
    const data = await res.json();

    if (!data.ok) {
      statusEl.textContent = data.error?.includes('not configured')
        ? t('historyNoDB')
        : t('historyError') + ' ' + (data.error || '');
      return;
    }

    const routes = data.routes || [];
    statusEl.style.display = 'none';

    if (!routes.length) {
      listEl.innerHTML = `<div style="font-size:10px;color:var(--muted);text-align:center;padding:12px">${t('historyEmpty')}</div>`;
      return;
    }

    routes.forEach(r => {
      const card = document.createElement('div');
      card.style.cssText = 'background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:7px 9px;cursor:pointer;transition:border-color .15s;font-size:10px';
      card.onmouseenter = () => card.style.borderColor = 'var(--accent)';
      card.onmouseleave = () => card.style.borderColor = 'var(--border2)';

      const dateStr = (r.route_date || '').split('T')[0];
      const dist    = r.total_distance_km != null ? `${Number(r.total_distance_km).toFixed(1)} km` : '—';
      const cost    = r.total_cost_rsd    != null ? `${Math.round(r.total_cost_rsd).toLocaleString()} RSD` : '—';
      const stops   = r.num_stops ?? '—';
      const vtype   = r.vehicle_type || '—';
      const algo    = r.algorithm || '—';
      const by      = r.saved_by  || '—';

      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
          <span style="font-family:var(--font-syne,sans-serif);font-weight:700;font-size:11px;color:var(--fg)">#${r.route_id} · ${dateStr}</span>
          <span style="color:var(--accent);font-weight:600">${cost}</span>
        </div>
        <div style="color:var(--muted);display:flex;gap:8px;flex-wrap:wrap">
          <span>🚛 ${vtype}</span>
          <span>📏 ${dist}</span>
          <span>📍 ${stops} ${t('historyColStops').toLowerCase()}</span>
          <span>⚙️ ${algo}</span>
          <span>👤 ${by}</span>
        </div>`;
      card.onclick = () => openHistoryRoute(r.route_id);
      listEl.appendChild(card);
    });
  } catch (e) {
    statusEl.style.display = 'block';
    statusEl.textContent = t('historyError');
  }
}

async function openHistoryRoute(routeId) {
  _historyCurrentId = routeId;
  const modal   = document.getElementById('history-modal');
  const bodyEl  = document.getElementById('history-modal-body');
  const titleEl = document.getElementById('history-modal-title');

  titleEl.textContent = t('routeDetail') + ` #${routeId}`;
  bodyEl.innerHTML    = `<div class="placeholder-msg">${t('loading')}</div>`;
  modal.classList.remove('hidden');

  try {
    const res  = await fetch(apiUrl(`/api/routes/${routeId}`));
    const data = await res.json();
    if (!data.ok) { bodyEl.innerHTML = `<div style="color:var(--danger)">${data.error}</div>`; return; }
    const r = data.route;

    const fmtNum = (v, dec=1) => v != null ? Number(v).toFixed(dec) : '—';
    const fmtRSD = v => v != null ? Math.round(v).toLocaleString() + ' RSD' : '—';

    let stopsHtml = '';
    if (r.stops && r.stops.length) {
      stopsHtml = `
        <div style="margin-top:12px;font-size:10px;font-weight:700;color:var(--fg);margin-bottom:4px">${t('historyColStops')}</div>
        <table style="width:100%;border-collapse:collapse;font-size:9px">
          <thead>
            <tr style="background:var(--bg3);color:var(--muted)">
              <th style="padding:3px 5px;text-align:left">#</th>
              <th style="padding:3px 5px;text-align:left">Customer</th>
              <th style="padding:3px 5px;text-align:center">Arrival</th>
              <th style="padding:3px 5px;text-align:center">Depart</th>
              <th style="padding:3px 5px;text-align:center">Window</th>
              <th style="padding:3px 5px;text-align:right">Vol m³</th>
              <th style="padding:3px 5px;text-align:right">Wt kg</th>
            </tr>
          </thead>
          <tbody>
            ${r.stops.map((s, i) => {
              const viol = s.tw_violation_min > 0 ? ` <span style="color:var(--danger)">⚠️+${s.tw_violation_min}m</span>` : '';
              return `<tr style="border-top:1px solid var(--border2);${i%2===1?'background:var(--bg3)':''}">
                <td style="padding:3px 5px;color:var(--muted)">${s.stop_sequence}</td>
                <td style="padding:3px 5px;color:var(--fg)">${s.customer_name || '—'}</td>
                <td style="padding:3px 5px;text-align:center">${s.arrival_time || '—'}${viol}</td>
                <td style="padding:3px 5px;text-align:center">${s.departure_time || '—'}</td>
                <td style="padding:3px 5px;text-align:center;color:var(--muted)">${s.tw_start||'?'}–${s.tw_end||'?'}</td>
                <td style="padding:3px 5px;text-align:right">${fmtNum(s.volume_m3,3)}</td>
                <td style="padding:3px 5px;text-align:right">${fmtNum(s.weight_kg,1)}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`;
    }

    bodyEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:10px;margin-bottom:8px">
        ${[
          ['Date',        (r.route_date||'').split('T')[0]],
          ['Vehicle',     r.vehicle_type || '—'],
          ['Algorithm',   r.algorithm || '—'],
          ['Matrix',      r.matrix_source || '—'],
          ['Depot',       r.depot_name || '—'],
          ['Saved by',    r.saved_by || '—'],
          ['Distance',    fmtNum(r.total_distance_km) + ' km'],
          ['Fuel',        fmtNum(r.total_fuel_litres) + ' L'],
          ['Fuel cost',   fmtRSD(r.fuel_cost_rsd)],
          ['Wages',       fmtRSD(r.wage_cost_rsd)],
          ['Total cost',  fmtRSD(r.total_cost_rsd)],
          ['Working hrs', fmtNum(r.working_hours)],
          ['Departure',   r.departure_time || '—'],
          ['Return',      r.return_time    || '—'],
          ['Vol used',    fmtNum(r.volume_used_m3, 3) + ' m³'],
          ['Wt used',     fmtNum(r.weight_used_kg, 1) + ' kg'],
          ['Fuel price',  fmtNum(r.fuel_price_rsd_l, 0) + ' RSD/L'],
          ['Wage rate',   fmtNum(r.driver_wage_rsd_h, 0) + ' RSD/h'],
        ].map(([k, v]) => `
          <div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border2);padding:2px 0">
            <span style="color:var(--muted)">${k}</span>
            <span style="color:var(--fg);font-weight:600">${v}</span>
          </div>`).join('')}
      </div>
      ${stopsHtml}`;
  } catch (e) {
    bodyEl.innerHTML = `<div style="color:var(--danger)">${t('historyError')}</div>`;
  }
}

function closeHistoryModal() {
  document.getElementById('history-modal').classList.add('hidden');
  _historyCurrentId = null;
}

async function deleteHistoryRoute() {
  if (!_historyCurrentId) return;
  if (!confirm(t('historyDeleteConfirm'))) return;
  try {
    const res  = await fetch(apiUrl(`/api/routes/${_historyCurrentId}`), { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      closeHistoryModal();
      loadRouteHistory();
    } else {
      alert(t('historyDeleteError') + (data.error || ''));
    }
  } catch (e) {
    alert(t('historyDeleteError') + e.message);
  }
}

// ─── WORKSPACE MANAGEMENT ────────────────────────────────────────────────────

let _workspacePendingId = null;   // id of workspace selected for load/delete

function _getWorkspaceSnapshot() {
  // Collect all current UI state into a saveable object
  return {
    depots:    state.depots,
    customers: state.customers,
    fleet:     state.fleet,
    settings: {
      pkg_sizes:            state.pkg_sizes,
      pkg_weights_kg:       state.pkg_weights_kg,
      algorithm:            document.getElementById('algo-select')?.value || 'Model 1',
      max_iterations:       parseInt(document.getElementById('max-iter')?.value) || 500,
      temperature:          parseFloat(document.getElementById('temperature')?.value) || 150,
      use_time_windows:     document.getElementById('use-tw')?.checked || false,
      use_volume_capacity:  document.getElementById('use-vol-cap')?.checked ?? true,
      use_weight_capacity:  document.getElementById('use-wt-cap')?.checked ?? true,
      obj_weights:          getObjWeights(),
      ...getCostParams(),
      advanced_params:      getAdvancedParams(),
    },
    result: state.lastResult || null,
  };
}

function _applyWorkspaceSnapshot(ws) {
  // Restore depots
  state.depots = ws.depots || [];
  state.customers = ws.customers || [];
  state.fleet = ws.fleet || state.fleet;

  // Restore settings
  const s = ws.settings || {};
  if (s.pkg_sizes)      state.pkg_sizes      = s.pkg_sizes;
  if (s.pkg_weights_kg) state.pkg_weights_kg = s.pkg_weights_kg;

  // UI inputs
  if (s.algorithm)        document.getElementById('algo-select').value          = s.algorithm;
  if (s.max_iterations)   document.getElementById('max-iter').value             = s.max_iterations;
  if (s.temperature)      document.getElementById('temperature').value          = s.temperature;
  if (s.use_time_windows !== undefined) document.getElementById('use-tw').checked          = s.use_time_windows;
  if (s.use_volume_capacity !== undefined) document.getElementById('use-vol-cap').checked  = s.use_volume_capacity;
  if (s.use_weight_capacity !== undefined) document.getElementById('use-wt-cap').checked   = s.use_weight_capacity;
  if (s.fuel_price_rsd_l)    document.getElementById('fuel-price-rsd').value   = s.fuel_price_rsd_l;
  if (s.driver_wage_rsd_h)   document.getElementById('driver-wage-rsd').value  = s.driver_wage_rsd_h;
  if (s.fuel_load_factor_pct !== undefined) document.getElementById('fuel-load-factor').value = s.fuel_load_factor_pct;
  if (s.obj_weights) {
    document.getElementById('obj-fuel').checked     = !!s.obj_weights.fuel;
    document.getElementById('obj-wages').checked    = !!s.obj_weights.wages;
    document.getElementById('obj-distance').checked = !!s.obj_weights.distance;
    document.getElementById('obj-vehicles').checked = !!s.obj_weights.vehicles;
  }
  if (s.advanced_params) {
    const a = s.advanced_params;
    if (a.k_nearest !== undefined)            document.getElementById('adv-k-nearest').value          = a.k_nearest;
    if (a.sentinel_factor !== undefined)      document.getElementById('adv-sentinel-factor').value    = a.sentinel_factor;
    if (a.overlap_threshold_km !== undefined) document.getElementById('adv-overlap-threshold').value  = a.overlap_threshold_km;
    if (a.overlap_weight_rsd !== undefined)   document.getElementById('adv-overlap-weight').value     = a.overlap_weight_rsd;
    if (a.dist_rsd_per_km !== undefined)      document.getElementById('adv-dist-rsd-per-km').value    = a.dist_rsd_per_km;
    if (a.tw_penalty_rsd !== undefined)       document.getElementById('adv-tw-penalty-rsd').value     = a.tw_penalty_rsd;
    if (a.alns_cooling !== undefined)         document.getElementById('adv-alns-cooling').value       = a.alns_cooling;
    if (a.hist_blend_weight !== undefined)    document.getElementById('adv-hist-blend-weight').value  = a.hist_blend_weight;
    if (a.departure_time !== undefined)       document.getElementById('adv-dep-time').value           = a.departure_time;
  }
  if (s.pkg_sizes) {
    document.getElementById('pkg-size-1').value = s.pkg_sizes[0] || 0.10;
    document.getElementById('pkg-size-2').value = s.pkg_sizes[1] || 0.30;
    document.getElementById('pkg-size-3').value = s.pkg_sizes[2] || 0.60;
  }
  if (s.pkg_weights_kg) {
    document.getElementById('pkg-weight-1').value = s.pkg_weights_kg[0] || 5;
    document.getElementById('pkg-weight-2').value = s.pkg_weights_kg[1] || 15;
    document.getElementById('pkg-weight-3').value = s.pkg_weights_kg[2] || 30;
  }

  // Restore result
  state.lastResult = ws.result || null;

  // Re-render everything
  clearRoutes();
  redrawAllMarkers();
  renderLocationsList();
  renderFleetCards();
  updatePkgSizes();
  updatePkgWeights();
  updateCostHint();
  updateObjHint();
  updateConstraintHint();

  if (state.lastResult) {
    drawResults(state.lastResult);
    drawRoutes(state.lastResult);
    renderLegend(state.lastResult);
    document.getElementById('simulate-btn').disabled = false;
    document.getElementById('pdf-btn').disabled = false;
  } else {
    resetResults();
  }
}

function redrawAllMarkers() {
  // Clear existing markers and re-add from state
  Object.values(state.markers || {}).forEach(m => safeRemove(m));
  state.markers = {};

  state.depots.forEach((dep, i) => {
    const icon = L.divIcon({
      className: '',
      html: `<div style="
        width:24px;height:24px;border-radius:50%;
        background:${DEPOT_COLOR};border:3px solid #fff;
        box-shadow:0 2px 6px rgba(0,0,0,.5);
        display:flex;align-items:center;justify-content:center;
        font-size:12px;line-height:1;color:#fff;font-weight:700;">${i + 1}</div>`,
      iconSize:[24,24], iconAnchor:[12,12], popupAnchor:[0,-14]
    });
    const m = L.marker([dep.lat, dep.lng], { icon, draggable: true })
      .addTo(map)
      .bindPopup(`<b>${dep.name}</b><br>${dep.lat.toFixed(5)}, ${dep.lng.toFixed(5)}`);
    m.on('dragend', e => {
      const p = e.target.getLatLng();
      dep.lat = p.lat; dep.lng = p.lng;
      m.getPopup().setContent(`<b>${dep.name}</b><br>${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`);
    });
    m.on('contextmenu', () => removeDepot(dep.id));
    state.markers[dep.id] = m;
  });

  state.customers.forEach((c, i) => {
    const num = i + 1;
    const pkg = c.pkg_counts || [0, 0, 0];
    const vol = calcVolume(pkg);
    const unload = c.unloading_time || 10;
    const tw = c.time_window || { start: '09:00', end: '17:00' };
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
    const m = L.marker([c.lat, c.lng], { icon, draggable: true })
      .addTo(map)
      .bindPopup(
        `<b>${esc(c.name)}</b><br>` +
        `📦 P1:${pkg[0]} P2:${pkg[1]} P3:${pkg[2]}<br>` +
        `📐 ${vol.toFixed(2)} m³ · ⚖️ ${calcWeight(pkg).toFixed(1)} kg<br>` +
        `⏱ ${tw.start}–${tw.end}<br>` +
        `🔧 ${t('unloadPopup')(unload)}`
      );
    m.on('dragend', e => {
      const p = e.target.getLatLng();
      c.lat = p.lat; c.lng = p.lng;
    });
    m.on('contextmenu', () => removeCustomer(c.id));
    state.markers[c.id] = m;
  });

  if (state.depots.length > 0) {
    map.setView([state.depots[0].lat, state.depots[0].lng], 12);
  }
}

// ── Save modal ────────────────────────────────────────────────────────────────

let _overwriteWorkspaceId = null;

function openSaveWorkspaceModal(overwriteId, overwriteName) {
  _overwriteWorkspaceId = overwriteId || null;
  const snap = _getWorkspaceSnapshot();
  const nD = snap.depots.length;
  const nC = snap.customers.length;
  const nV = snap.fleet.reduce((s, v) => s + (v.count || 1), 0);
  const hasResult = !!snap.result;
  document.getElementById('workspace-save-summary').innerHTML =
    `${nD} depot${nD!==1?'s':''}, ${nC} customer${nC!==1?'s':''}, ` +
    `${nV} vehicle${nV!==1?'s':''}` +
    (hasResult ? ' <span style="color:var(--accent)">+ optimization result ✓</span>' : ' <span style="color:var(--muted)">(no result yet)</span>');
  document.getElementById('workspace-modal-title').textContent = overwriteId ? '✏️ Overwrite Workspace' : '💾 Save Workspace';
  if (overwriteName) document.getElementById('workspace-name-input').value = overwriteName;
  document.getElementById('workspace-save-error').style.display = 'none';
  document.getElementById('workspace-save-modal').classList.remove('hidden');
  setTimeout(() => document.getElementById('workspace-name-input').focus(), 50);
}

function closeWorkspaceSaveModal() {
  document.getElementById('workspace-save-modal').classList.add('hidden');
  document.getElementById('workspace-name-input').value = '';
  document.getElementById('workspace-desc-input').value = '';
  _overwriteWorkspaceId = null;
}

async function confirmSaveWorkspace() {
  const name = document.getElementById('workspace-name-input').value.trim();
  if (!name) {
    document.getElementById('workspace-save-error').textContent = 'Please enter a workspace name.';
    document.getElementById('workspace-save-error').style.display = 'block';
    return;
  }
  const desc = document.getElementById('workspace-desc-input').value.trim();
  const snap = _getWorkspaceSnapshot();
  const btn  = document.getElementById('workspace-save-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Saving…';

  try {
    const payload = { name, description: desc, ...snap };
    if (_overwriteWorkspaceId) payload.id = _overwriteWorkspaceId;
    const res  = await fetch(apiUrl('/api/workspaces'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      closeWorkspaceSaveModal();
      loadWorkspaceList();
      // Briefly flash the panel open
      const panel = document.getElementById('panel-workspaces');
      if (panel && panel.classList.contains('collapsed')) {
        panel.classList.remove('collapsed');
      }
    } else {
      document.getElementById('workspace-save-error').textContent = data.error || 'Save failed.';
      document.getElementById('workspace-save-error').style.display = 'block';
    }
  } catch (e) {
    document.getElementById('workspace-save-error').textContent = 'Network error: ' + e.message;
    document.getElementById('workspace-save-error').style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '💾 Save';
  }
}

// ── List ──────────────────────────────────────────────────────────────────────

async function loadWorkspaceList() {
  const listEl   = document.getElementById('workspace-list');
  const statusEl = document.getElementById('workspace-status');
  if (!listEl) return;
  statusEl.textContent = 'Loading…';
  statusEl.style.display = 'block';
  listEl.innerHTML = '';
  try {
    const res  = await fetch(apiUrl('/api/workspaces'));
    const data = await res.json();
    statusEl.style.display = 'none';
    if (!data.ok) {
      listEl.innerHTML = `<div style="font-size:11px;color:#e74c3c;padding:6px">${data.error || 'Failed to load'}</div>`;
      return;
    }
    if (!data.workspaces.length) {
      listEl.innerHTML = '<div style="font-size:11px;color:var(--muted);text-align:center;padding:8px">No workspaces saved yet.</div>';
      return;
    }
    listEl.innerHTML = data.workspaces.map(w => {
      const dt = new Date(w.updated_at).toLocaleString([], { dateStyle:'short', timeStyle:'short' });
      return `
        <div class="history-card" onclick="openWorkspaceLoadModal(${w.id})"
             style="cursor:pointer;padding:8px 10px;background:var(--bg3);border:1px solid var(--border2);border-radius:6px">
          <div style="font-weight:600;font-size:12px;color:var(--fg);margin-bottom:2px">${w.name}</div>
          ${w.description ? `<div style="font-size:10px;color:var(--muted);margin-bottom:3px">${w.description}</div>` : ''}
          <div style="font-size:10px;color:var(--muted)">
            ${w.n_depots} depot${w.n_depots!==1?'s':''} · ${w.n_customers} customer${w.n_customers!==1?'s':''}
            · by <b>${w.updated_by}</b> · ${dt}
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    statusEl.style.display = 'none';
    listEl.innerHTML = `<div style="font-size:11px;color:#e74c3c;padding:6px">Error: ${e.message}</div>`;
  }
}

// ── Load / Delete modal ───────────────────────────────────────────────────────

async function openWorkspaceLoadModal(id) {
  _workspacePendingId = id;
  document.getElementById('workspace-load-body').innerHTML = '<div style="color:var(--muted);font-size:12px">Loading…</div>';
  document.getElementById('workspace-load-modal').classList.remove('hidden');
  try {
    const res  = await fetch(apiUrl(`/api/workspaces/${id}`));
    const data = await res.json();
    if (!data.ok) {
      document.getElementById('workspace-load-body').innerHTML =
        `<div style="color:#e74c3c;font-size:12px">${data.error}</div>`;
      return;
    }
    document.getElementById('workspace-load-title').textContent = `📂 ${data.name}`;
    const dt   = new Date(data.updated_at).toLocaleString([], { dateStyle:'medium', timeStyle:'short' });
    const nV   = (data.fleet||[]).reduce((s,v) => s + (v.count||1), 0);
    const s    = data.settings || {};
    document.getElementById('workspace-load-body').innerHTML = `
      <div style="font-size:12px;line-height:1.9;color:var(--fg)">
        ${data.description ? `<div style="color:var(--muted);font-size:11px;margin-bottom:8px">${data.description}</div>` : ''}
        <div>📍 <b>${(data.depots||[]).length}</b> depot(s)</div>
        <div>🏠 <b>${(data.customers||[]).length}</b> customer(s)</div>
        <div>🚛 <b>${nV}</b> vehicle(s) in fleet</div>
        <div>⚙️ Algorithm: <b>${s.algorithm || '—'}</b></div>
        <div>📊 Result: <b>${data.result ? '✅ included' : '—'}</b></div>
        <div style="margin-top:6px;font-size:10px;color:var(--muted)">Last saved by <b>${data.updated_by}</b> on ${dt}</div>
      </div>
      <div style="margin-top:12px;padding:8px;background:rgba(231,76,60,.08);border:1px solid rgba(231,76,60,.2);border-radius:5px;font-size:11px;color:#e74c3c">
        ⚠️ Loading will replace your current workspace.
      </div>`;
    // Store data for use in confirmLoadWorkspace
    document.getElementById('workspace-load-btn')._wsData = data;
  } catch (e) {
    document.getElementById('workspace-load-body').innerHTML =
      `<div style="color:#e74c3c;font-size:12px">Error: ${e.message}</div>`;
  }
}

function closeWorkspaceLoadModal() {
  document.getElementById('workspace-load-modal').classList.add('hidden');
  _workspacePendingId = null;
}

function confirmLoadWorkspace() {
  const data = document.getElementById('workspace-load-btn')._wsData;
  if (!data) return;
  closeWorkspaceLoadModal();
  clearAll();
  _applyWorkspaceSnapshot(data);
}

async function confirmDeleteWorkspace() {
  if (!_workspacePendingId) return;
  if (!confirm('Delete this workspace? This cannot be undone.')) return;
  try {
    const res  = await fetch(apiUrl(`/api/workspaces/${_workspacePendingId}`), { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      closeWorkspaceLoadModal();
      loadWorkspaceList();
    } else {
      alert('Delete failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Delete failed: ' + e.message);
  }
}

async function exportWorkspace() {
  if (!_workspacePendingId) return;
  const wsId = _workspacePendingId;
  console.log(`[GRPS] exporting workspace ${wsId}`);
  const btn = document.getElementById('workspace-export-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Exporting…'; }
  try {
    const res = await fetch(apiUrl(`/api/workspaces/${wsId}/export`));
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      alert('Export failed: ' + (err.error || 'Unknown error'));
      return;
    }
    // Trigger browser download via a temporary anchor
    const blob     = await res.blob();
    const fname    = res.headers.get('content-disposition')?.match(/filename="?([^"]+)"?/)?.[1]
                     || `grps_workspace_${wsId}.json`;
    const url      = URL.createObjectURL(blob);
    const anchor   = document.createElement('a');
    anchor.href    = url;
    anchor.download = fname;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    console.log(`[GRPS] workspace ${wsId} exported as ${fname}`);
  } catch (e) {
    alert('Export error: ' + e.message);
    console.error('[GRPS] export error:', e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '📤 Export'; }
  }
}

// ── JSON Import ───────────────────────────────────────────────────────────────

function importWorkspaceJson(input) {
  const file = input.files[0];
  if (!file) return;
  // Reset so re-selecting the same file fires onchange again
  input.value = '';

  if (!file.name.endsWith('.json')) {
    alert('Please select a .json workspace file (exported from GRPS).');
    return;
  }

  const reader = new FileReader();
  reader.onload = function(e) {
    let ws;
    try {
      ws = JSON.parse(e.target.result);
    } catch (err) {
      alert('Invalid JSON file: ' + err.message);
      return;
    }

    // Basic sanity check — must look like a GRPS workspace
    if (!ws || (!ws.customers && !ws.depots && !ws.fleet)) {
      alert('This does not appear to be a valid GRPS workspace file.');
      return;
    }

    if (!confirm(
      `Import workspace "${ws.name || file.name}"?\n` +
      `${(ws.depots || []).length} depot(s), ${(ws.customers || []).length} customer(s).\n\n` +
      `This will replace your current workspace.`
    )) return;

    clearAll();
    _applyWorkspaceSnapshot(ws);
    console.log('[GRPS] workspace imported from', file.name);
  };
  reader.onerror = () => alert('Failed to read file: ' + reader.error);
  reader.readAsText(file);
}
// ─── DRIVERS WINDOW ──────────────────────────────────────────────────────────

// state.drivers — full list imported from Excel (initialized in state object)
// state.driverSelected — Set of driver names currently checked as eligible

/**
 * Import a driver roster Excel file.
 * Expected columns: Name & Surname | Availability (0/1) | Vehicle Preference
 */
async function importDriversExcel(input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const statusEl = document.getElementById('driver-import-status');
  statusEl.style.color = 'var(--muted)';
  statusEl.textContent = '⏳ Parsing driver roster…';
  input.value = '';

  try {
    const res = await fetch(apiUrl('/api/import_drivers'), { method: 'POST', body: fd });
    const data = await res.json();
    if (!data.ok) {
      statusEl.style.color = '#e74c3c';
      statusEl.textContent = '❌ ' + (data.error || 'Import failed');
      return;
    }
    state.drivers = data.drivers || [];
    state.driverSelected = new Set(
      state.drivers.filter(d => d.available).map(d => d.name)
    );

    if (data.errors && data.errors.length) {
      console.warn('[GRPS drivers] import warnings:', data.errors);
    }

    statusEl.style.color = 'var(--accent)';
    statusEl.textContent = `✅ Imported ${state.drivers.length} driver(s)`;

    renderDriverChecklist();
    updateDriverSummary();

    document.getElementById('driver-selector-wrap').style.display = '';
    document.getElementById('driver-summary').style.display = '';
    document.getElementById('driver-penalty-wrap').style.display = '';
  } catch (e) {
    statusEl.style.color = '#e74c3c';
    statusEl.textContent = '❌ ' + e.message;
  }
}

/** Render the checkboxes for each imported driver. */
function renderDriverChecklist() {
  const el = document.getElementById('driver-checklist');
  if (!el) return;

  const PREF_BADGE = {
    small:  { bg: '#3b82f6', label: 'small' },
    medium: { bg: '#f97316', label: 'medium' },
    large:  { bg: '#ef4444', label: 'large' },
  };

  el.innerHTML = state.drivers.map(d => {
    const checked = state.driverSelected.has(d.name);
    const availBadge = d.available
      ? '<span style="color:#22c55e;font-size:9px">✔ avail</span>'
      : '<span style="color:#e74c3c;font-size:9px">✖ unavail</span>';
    const prefColor = (PREF_BADGE[d.vehicle_pref] || {}).bg || 'transparent';
    const prefLabel = d.vehicle_pref
      ? `<span style="background:${prefColor};color:#fff;font-size:9px;padding:1px 5px;border-radius:3px;margin-left:4px">${d.vehicle_pref}</span>`
      : '<span style="color:var(--muted);font-size:9px;margin-left:4px">any</span>';
    return `
      <label style="display:flex;align-items:center;gap:6px;padding:4px 6px;
                    background:var(--bg3);border-radius:4px;cursor:pointer;
                    border:1px solid var(--border2);user-select:none">
        <input type="checkbox" ${checked ? 'checked' : ''} style="accent-color:var(--accent)"
               onchange="toggleDriverSelection('${esc(d.name)}', this.checked)">
        <span style="flex:1;font-size:11px;color:var(--fg)">${esc(d.name)}</span>
        ${availBadge}
        ${prefLabel}
      </label>`;
  }).join('');
}

function toggleDriverSelection(name, checked) {
  if (checked) state.driverSelected.add(name);
  else state.driverSelected.delete(name);
  updateDriverSummary();
}

function selectAllDrivers(all) {
  if (all) {
    state.drivers.forEach(d => state.driverSelected.add(d.name));
  } else {
    state.driverSelected.clear();
  }
  renderDriverChecklist();
  updateDriverSummary();
}

function updateDriverSummary() {
  const el = document.getElementById('driver-summary');
  if (!el) return;
  const total    = state.drivers.length;
  const eligible = state.driverSelected.size;
  const avail    = state.drivers.filter(d => d.available && state.driverSelected.has(d.name)).length;
  el.textContent = `${eligible}/${total} selected · ${avail} available · used as soft constraint`;
}

/**
 * Returns the list of eligible drivers to send to the optimizer.
 * Only drivers that are (a) checked in the UI are included.
 * Unavailable drivers are filtered by the backend; the UI pre-deselects them
 * but users can override.
 */
function getEligibleDrivers() {
  return state.drivers.filter(d => state.driverSelected.has(d.name));
}

// Driver data is injected into the optimize payload via getDriverPayloadExtras().
// The runOptimize function reads this before building its payload.
function getDriverPayloadExtras() {
  if (!state.drivers || state.drivers.length === 0) return {};
  return {
    eligible_drivers:       getEligibleDrivers(),
    driver_pref_penalty_rsd: parseFloat(
      document.getElementById('driver-pref-penalty')?.value || '5000'
    ),
  };
}
