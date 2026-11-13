'use strict';
// Le navigateur ne lit jamais la carte NI : il reçoit les mesures du service Python.
const $ = id => document.getElementById(id);
const titles = {dashboard:['Tableau de bord','Une vue claire sur toutes les mesures de votre station.'],history:['Historique','Explorez les acquisitions, choisissez vos dates et exportez vos données.'],statistics:['Statistiques','Comprendre les tendances sur une période et une source précises.'],alarms:['Alarmes','Retrouvez les dépassements de seuils et leur durée observée.'],settings:['Paramètres','Configurez les voies, les étalonnages et les seuils de votre station.']};
const labels = {temperature:'Température',direction:'Girouette',wind:'Vent',rain:'Pluviomètre',rain_ml:'Pluie cumulée',humidity:'Humectation / humidité',light:'Luminosité',counter:'Compteur physique'};
const colors = {temperature:'#efb16e',wind:'#68d9cf',rain_ml:'#83adff',direction:'#c2d77c',humidity:'#b29bff',light:'#ead17f'};
let settings, activePage='dashboard', latest=null, recent=[], liveSource=null, socket, historyChart, roseChart, archiveGeneration=0;
const charts = {}, peakTimes = new Map();
const fmt = (value, digits=1) => value === null || value === undefined ? '—' : Number(value).toLocaleString('fr-FR',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const text = (id,value) => { $(id).textContent = value; };
const dateText = value => value ? new Date(value).toLocaleString('fr-FR') : '—';
const escapeHtml = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = seconds => `${Math.floor(seconds/3600)} h ${Math.floor(seconds%3600/60)} min ${Math.floor(seconds%60)} s`;

async function api(path, options={}) {
  const response = await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  if (!response.ok) {
    let detail;
    try { detail=(await response.json()).detail; } catch { detail=response.statusText; }
    if (Array.isArray(detail)) detail=detail.map(e=>`${e.loc.join(' → ')} : ${e.msg}`).join('\n');
    throw new Error(detail || `Erreur HTTP ${response.status}`);
  }
  return response.json();
}
function notify(message) { text('notice',message); $('notice').hidden=!message; }
function guarded(fn) { return async (...args) => { try { await fn(...args); } catch(error) { notify(error.message); } }; }

function makeChart(id, color, type='line') {
  if (!window.Chart) throw new Error('Chart.js manque. Vérifier frontend/vendor/chart.umd.min.js.');
  return new Chart($(id),{type,data:{labels:[],datasets:[]},options:{responsive:true,maintainAspectRatio:false,animation:false,
    interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{backgroundColor:'#0b1422',padding:12}},
    scales: type==='polarArea'?{r:{grid:{color:'#304055'},ticks:{backdropColor:'transparent',color:'#90a3bc'},pointLabels:{display:true,color:'#b8c9db'}}}:{x:{grid:{display:false},ticks:{color:'#7e94af',maxTicksLimit:6,maxRotation:0}},y:{grid:{color:'#26364b'},ticks:{color:'#7e94af',maxTicksLimit:5}}}}});
}
function lineDataset(label,values,color,extra={}) {
  return {label,data:values,borderColor:color,backgroundColor:color+'13',borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:.22,fill:true,spanGaps:false,...extra};
}
function updateChart(chart, rows, key, color, peaks=[]) {
  chart.data.labels = rows.map(r=>new Date(r.timestamp).toLocaleString('fr-FR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}));
  const values=rows.map(r=>key.startsWith('raw_') ? r.raw?.[key.slice(4)]?.value??null : r[key]??null);
  chart.data.datasets=[lineDataset(labels[key]||key,values,color)];
  if (key==='temperature'||key==='rain_ml') {
    for (const [bound,label] of [['low','Seuil bas'],['high','Seuil haut']]) {
      const threshold=rows.map(r=>r.limits?.[key]?.[bound]??null);
      if(threshold.some(v=>v!==null)) chart.data.datasets.push(lineDataset(label,threshold,'#ce8790',{borderDash:[5,5],borderWidth:1,fill:false}));
    }
  }
  if (key==='wind') {
    const marks=rows.map(r=>peakTimes.has(r.timestamp)?r.wind:null);
    for(const peak of peaks){
      if(!rows.length) break;
      let nearest=0;
      rows.forEach((r,i)=>{if(Math.abs(new Date(r.timestamp)-new Date(peak.timestamp))<Math.abs(new Date(rows[nearest].timestamp)-new Date(peak.timestamp)))nearest=i;});
      marks[nearest]=peak.value;
    }
    chart.data.datasets.push(lineDataset('Pic de fenêtre',marks,'#ffbd7a',{showLine:false,fill:false,pointRadius:5,pointStyle:'triangle'}));
  }
  if (key==='direction') { chart.options.scales.y.min=0; chart.options.scales.y.max=360; }
  else {delete chart.options.scales.y.min;delete chart.options.scales.y.max;}
  chart.update('none');
}
function renderLiveCharts() {
  for(const [key,chart] of Object.entries(charts)) updateChart(chart,recent,key,colors[key]);
}
function renderReading(name, value, unit, raw, quality) {
  const id=name==='rain'?'rain':name;
  if(value!==null&&value!==undefined) $('value-'+id).innerHTML=`${fmt(value)}<small>${escapeHtml(unit)}</small>`;
  else if(raw?.value!==null&&raw?.value!==undefined) $('value-'+id).innerHTML=`${fmt(raw.value,3)}<small>${escapeHtml(raw.unit)} brut</small>`;
  else text('value-'+id,'—');
  if($('quality-'+id)){text('quality-'+id,quality||'Indisponible');$('quality-'+id).classList.toggle('warning',!!quality&&!['Étalonné','Simulation fictive','Désactivé'].includes(quality));}
}
function renderSnapshot(snapshot) {
  const state=snapshot.status||{};
  const names={simulation:'Mode simulation',connected:'Matériel connecté',disconnected:'Matériel déconnecté',sensor_error:'Erreur de capteur',error:'Erreur du service',starting:'Démarrage'};
  text('system-status',names[state.state]||'Connexion en cours');
  $('system-status').classList.toggle('error',['disconnected','sensor_error','error'].includes(state.state));
  text('source-label',state.mode==='simulation'?'SIMULATION · DONNÉES ENTIÈREMENT FICTIVES':'ACQUISITION MATÉRIELLE · NATIONAL INSTRUMENTS');
  text('source-detail',state.message||'');
  const row=snapshot.measurement;
  if(!row){
    recent=[];peakTimes.clear();
    for(const name of ['temperature','wind','rain','humidity','light'])renderReading(name,null,'',null,'En attente du nouveau mode');
    text('value-direction','—');text('direction-cardinal','En attente');text('weather-summary','Initialisation de la nouvelle acquisition.');
    text('relative-humidity','—');text('comfort-score','—');$('comfort-fill').style.width='0%';$('compass-needle').style.opacity='0';
    renderLiveCharts();return;
  }
  latest=row;
  const identity=`${row.source}:${row.station}`;
  if(liveSource!==identity){recent=[];peakTimes.clear();liveSource=identity;}
  if(row.peak) peakTimes.set(row.peak.timestamp,row.peak.value);
  if(recent.at(-1)?.timestamp!==row.timestamp){recent.push(row);if(recent.length>300)recent.shift();}
  const first=recent[0]?.timestamp;
  for(const timestamp of peakTimes.keys()) if(timestamp<first)peakTimes.delete(timestamp);
  text('last-update',`Dernière acquisition · ${dateText(row.timestamp)}`);
  renderReading('temperature',row.temperature,'°C',row.raw.temperature,row.quality.temperature);
  renderReading('wind',row.wind,'km/h',row.raw.wind,row.quality.wind);
  renderReading('rain',row.rain_ml,'mL',row.raw.rain,row.quality.rain);
  renderReading('humidity',row.humidity,'%',row.raw.humidity,row.quality.humidity);
  renderReading('light',row.light,row.units.light,row.raw.light,row.quality.light);
  const temperatures=recent.map(r=>r.temperature).filter(v=>v!==null);
  text('detail-temperature',temperatures.length?`Courbe récente : ${fmt(Math.min(...temperatures))}° min · ${fmt(Math.max(...temperatures))}° max`:'Étalonnage nécessaire pour les °C');
  text('detail-wind',`Max sur ${settings?.peak_window_seconds||30} s : ${fmt(row.wind_window_max)} km/h`);
  text('detail-rain',`Compteur : ${fmt(row.rain_count,0)} imp. · ${fmt(row.rain_mm,2)} mm`);
  text('humidity-label',row.humidity_kind==='relative_humidity'?'Humidité relative':'Humectation de surface');
  text('humidity-chart-title',$('humidity-label').textContent);
  text('detail-humidity',row.humidity_kind==='relative_humidity'?'Humidité de l’air':'Capteur de surface, distinct de l’humidité de l’air');
  text('relative-humidity',`${fmt(row.relative_humidity)} %${row.source==='simulation'?' fictif':''}`);
  text('light-chart-unit',row.units.light);
  text('value-direction',row.direction!==null?`${fmt(row.direction,0)}°`:row.raw.direction?.value!=null?`${fmt(row.raw.direction.value,3)} V`:'—');
  text('direction-cardinal',row.cardinal||'Direction non étalonnée');
  text('quality-direction',row.quality.direction);
  $('compass-needle').style.opacity=row.direction!==null?'1':'0';
  $('compass-needle').style.transform=`rotate(${row.direction||0}deg)`;
  text('weather-summary',row.summary);
  text('comfort-score',row.comfort!==null?`${row.comfort}/100`:'Indisponible');
  $('comfort-fill').style.width=`${row.comfort||0}%`;
  text('station-header',String(row.station).padStart(2,'0'));
  text('station-number',String(row.station).padStart(2,'0'));
  const binary=row.station.toString(2).padStart(16,'0');
  text('station-binary',binary);
  $('station-leds').innerHTML=[...binary].map((bit,i)=>`<span class="led ${bit==='1'?'on':''}" title="Bit ${15-i} : ${bit}"></span>`).join('');
  $('station-leds').setAttribute('aria-label',`Numéro ${row.station}, binaire ${binary}`);
  text('physical-counter',fmt(row.counter,0));
  renderLiveCharts();
}
function connectSocket() {
  socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/measurements`);
  socket.onmessage=event=>{try{renderSnapshot(JSON.parse(event.data));}catch(error){notify(error.message);}};
  socket.onclose=()=>{text('system-status','Serveur déconnecté');$('system-status').classList.add('error');text('source-detail','Connexion perdue. Les valeurs affichées sont les dernières reçues. Reconnexion automatique…');setTimeout(connectSocket,2000);};
  socket.onerror=()=>socket.close();
}

function localInput(date) { const adjusted=new Date(date.getTime()-date.getTimezoneOffset()*60000);return adjusted.toISOString().slice(0,16); }
function setPeriod(days) {
  const end=new Date();$('date-end').value=localInput(end);$('date-start').value=localInput(new Date(end.getTime()-days*86400000));
  document.querySelectorAll('[data-days]').forEach(button=>button.classList.toggle('active',Number(button.dataset.days)===days));
}
function periodQuery() {
  if(!$('date-start').value||!$('date-end').value)throw new Error('Renseigner les deux dates.');
  const start=new Date($('date-start').value),end=new Date($('date-end').value);
  if(start>=end)throw new Error('Le début doit précéder la fin de la période.');
  return new URLSearchParams({start:start.toISOString(),end:end.toISOString(),source:$('archive-source').value,station:$('archive-station').value}).toString();
}
async function refreshArchives() {
  const query=periodQuery(),generation=++archiveGeneration;
  for(const id of ['history-report','stats-report']) $(id).href=`/api/report?${query}`;
  $('export-csv').href=`/api/export/csv?${query}`;
  if(activePage==='history'){
    const data=await api(`/api/measurements/history?${query}`);if(generation!==archiveGeneration)return;
    const key=$('history-sensor').value;
    text('history-info',`${data.count.toLocaleString('fr-FR')} mesures enregistrées · ${data.source==='simulation'?'SIMULATION FICTIVE':'Matériel NI'} · station ${data.station}`+(data.aggregated?` · courbe regroupée par ${fmt(data.bucket_seconds,0)} s (moyennes ; direction circulaire). Les valeurs brutes nécessitent une période plus courte.`:''));
    updateChart(historyChart,data.items,key,colors[key]||'#83adff',data.peaks);
  } else if(activePage==='statistics') {
    const data=await api(`/api/statistics?${query}`);if(generation!==archiveGeneration)return;
    const cards=[['Température moyenne',data.temperature_mean,'°C','temperature'],['Vent moyen',data.wind_mean,'km/h','wind'],['Pluie sur la période',data.rain_total_ml,'mL','rain'],['Temps hors limites',duration(data.temperature_alarm_seconds),'','humidity']];
    $('statistics-cards').innerHTML=cards.map(([label,value,unit,cls])=>`<article class="panel metric ${cls}"><div class="metric-top">${label}</div><div class="metric-value">${typeof value==='string'?escapeHtml(value):fmt(value)}<small>${unit}</small></div><div class="metric-detail">${data.source==='simulation'?'Simulation fictive':'Matériel NI'} · station ${data.station}</div></article>`).join('');
    const pairs=[['Mesures enregistrées',fmt(data.count,0)],['Température minimale',`${fmt(data.temperature_min)} °C`],['Température maximale',`${fmt(data.temperature_max)} °C`],['Vent maximal',`${fmt(data.wind_max)} km/h`],['Direction dominante',data.dominant_direction||'—'],['Épisodes d’alarme',fmt(data.alarms_count,0)]];
    $('statistics-summary').innerHTML=pairs.map(([label,value])=>`<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`).join('');
    roseChart.data.labels=Object.keys(data.wind_rose);roseChart.data.datasets=[{data:Object.values(data.wind_rose),backgroundColor:['#68d9cfaa','#83adffaa','#b29bffaa','#efb16eaa','#c2d77caa','#68d9cf88','#83adff88','#b29bff88'],borderWidth:1,borderColor:'#142437'}];roseChart.update();
  } else if(activePage==='alarms') {
    const data=await api(`/api/alarms?${query}`);if(generation!==archiveGeneration)return;
    $('alarms-body').innerHTML=data.items.length?data.items.map(alarm=>`<tr><td>${dateText(alarm.start)}<small>${alarm.end?dateText(alarm.end):'En cours'}</small></td><td>${escapeHtml(labels[alarm.sensor]||alarm.sensor)}</td><td>${alarm.type==='high'?'Au-dessus de':'En dessous de'} ${fmt(alarm.threshold)}</td><td>${fmt(alarm.value)}</td><td>${duration(alarm.duration)}</td><td><span class="alarm-state ${alarm.status==='active'?'':'closed'}">${({active:'Active',closed:'Terminée',interrupted:'Interrompue'})[alarm.status]}</span></td><td>${alarm.acknowledged?'Acquittée':`<button class="button secondary" data-ack="${alarm.id}">Acquitter</button>`}</td></tr>`).join(''):'<tr><td colspan="7">Aucune alarme pour cette période, cette source et cette station.</td></tr>';
  }
}
async function refreshLiveAlarms() {
  if(!settings)return;
  const query=new URLSearchParams({start:'2000-01-01T00:00:00Z',end:new Date().toISOString(),source:settings.mode,station:settings.station_number});
  // La route limite les périodes à dix ans ; les alarmes actives se trouvent sur la fenêtre récente.
  query.set('start',new Date(Date.now()-3650*86400000).toISOString());
  const {items}=await api(`/api/alarms?${query}`),active=items.filter(a=>a.status==='active');
  text('alarm-badge',active.length);
  $('live-alarms').innerHTML=active.length?active.map(a=>`<div class="alarm-line">● ${escapeHtml(labels[a.sensor]||a.sensor)} ${a.type==='high'?'au-dessus':'en dessous'} de ${fmt(a.threshold)}<small>${duration(a.duration)} · ${a.acknowledged?'acquittée':'à acquitter'}</small></div>`).join(''):'Aucune alarme en cours.';
}

const getPath=(object,path)=>path.split('.').reduce((obj,key)=>obj?.[key],object);
function setPath(object,path,value){const keys=path.split('.'),last=keys.pop();keys.reduce((obj,key)=>obj[key],object)[last]=value;}
function field(label,path,type='number',options=null) {
  const value=getPath(settings,path),attr=`data-path="${path}"`;
  if(type==='checkbox')return `<label class="checkbox-label">${label}<input type="checkbox" ${attr} ${value?'checked':''}></label>`;
  if(type==='select')return `<label>${label}<select ${attr}>${options.map(option=>{const [v,l]=Array.isArray(option)?option:[option,option];return `<option value="${v}" ${value===v?'selected':''}>${escapeHtml(l)}</option>`;}).join('')}</select></label>`;
  return `<label>${label}<input ${attr} type="${type}" ${type==='number'?'step="any"':''} value="${escapeHtml(value??'')}" placeholder="${value===null?'Non renseigné':''}"></label>`;
}
function renderSettings() {
  $('general-settings').innerHTML=field('Mode','mode','select',[['simulation','Simulation fictive'],['hardware','Matériel NI']])+field('Numéro logique (0–65535)','station_number')+field('Nom NI MAX','device','text')+field('Cycle acquisition (s)','interval_seconds')+field('Écriture des lots (s)','save_seconds')+field('Échantillonnage analogique (Hz)','sample_rate_hz')+field('Points par voie / fenêtre','sample_count')+field('Fenêtre de pic (s)','peak_window_seconds')+field('Seuil de pic (km/h)','peak_threshold_kmh')+field('Fuseau des saisons','timezone','text');
  let alarmFields=field('Seuils saisonniers activés','alarms.seasonal','checkbox');
  for(const [path,label] of [['temperature','Température fixe'],['seasons.hiver','Hiver'],['seasons.printemps','Printemps'],['seasons.ete','Été'],['seasons.automne','Automne'],['rain','Cumul pluie (mL)']])
    alarmFields+=field(`${label} · bas`,`alarms.${path}.low`)+field(`${label} · haut`,`alarms.${path}.high`);
  $('alarm-settings').innerHTML=alarmFields;
  const kinds={temperature:['voltage'],direction:['voltage'],wind:['counter','frequency'],rain:['digital','counter'],humidity:['frequency','voltage'],light:['voltage'],counter:['digital','counter']};
  const kindLabels={voltage:'Tension moyenne (V)',frequency:'Fréquence sur entrée analogique',counter:'Compteur matériel',digital:'Entrée numérique'};
  $('sensor-settings').innerHTML=Object.keys(settings.sensors).map(name=>{
    const path=`sensors.${name}`;
    let fields=field('Activé sur le matériel',`${path}.enabled`,'checkbox')+field('Étalonnage vérifié',`${path}.calibrated`,'checkbox')+field('Type de mesure',`${path}.kind`,'select',kinds[name].map(k=>[k,kindLabels[k]]))+field('Voie (ex. ai3, ctr0, port0/line7)',`${path}.channel`,'text');
    if(['wind','rain','counter'].includes(name))fields+=field('Borne compteur (ex. PFI0)',`${path}.terminal`,'text')+field('Front de comptage',`${path}.edge`,'select',['FALLING','RISING']);
    if(['temperature','direction','humidity','light','wind'].includes(name))fields+=field('Coefficient par V / Hz',`${path}.scale`)+field('Décalage',`${path}.offset`)+field('Unité physique',`${path}.unit`,'text');
    if(['temperature','direction','humidity','light','wind'].includes(name))fields+=field('Configuration du terminal',`${path}.terminal_config`,'select',['RSE','DIFF','NRSE','DEFAULT']);
    if(['temperature','direction','humidity','light'].includes(name))fields+=field('Tension minimum (V)',`${path}.min_voltage`)+field('Tension maximum (V)',`${path}.max_voltage`);
    if(name==='rain')fields+=field('mL par impulsion',`${path}.ml_per_pulse`)+field('Surface collecte (cm²)',`${path}.collector_cm2`)+field('Scrutation contact lent (ms)',`${path}.poll_ms`)+field('Anti-rebond (ms)',`${path}.debounce_ms`);
    if(name==='humidity')fields+=field('Grandeur réellement mesurée',`${path}.quantity`,'select',[['surface_wetness','Humectation de surface (TP2)'],['relative_humidity','Humidité relative (autre capteur)']]);
    return `<article class="panel"><div class="card-heading"><h3>${labels[name]}</h3><span class="tag">${name.toUpperCase()}</span></div><div class="form-grid">${fields}</div></article>`;
  }).join('');
  $('switch-mode').disabled=false;text('switch-mode',settings.mode==='simulation'?'Passer au matériel →':'Revenir à la simulation →');
}
async function saveSettings(next) {
  $('switch-mode').disabled=true;
  const submit=$('settings-form').querySelector('[type=submit]');submit.disabled=true;
  try {
    const data=await api('/api/settings',{method:'PUT',body:JSON.stringify(next)});settings=data.settings;
    recent=[];latest=null;liveSource=null;peakTimes.clear();renderSettings();
    $('archive-source').value=settings.mode;$('archive-station').value=settings.station_number;
    text('settings-result','Paramètres enregistrés. Acquisition redémarrée.');notify('');
    renderSnapshot(await api('/api/measurements/latest'));await refreshLiveAlarms();
  } finally {submit.disabled=false;$('switch-mode').disabled=false;}
}
function navigate() {
  const page=location.hash.slice(1);activePage=titles[page]?page:'dashboard';
  document.querySelectorAll('.page').forEach(section=>section.hidden=section.id!==`page-${activePage}`);
  document.querySelectorAll('[data-page]').forEach(link=>link.classList.toggle('active',link.dataset.page===activePage));
  text('page-title',titles[activePage][0]);text('page-subtitle',titles[activePage][1]);text('page-crumb',activePage==='dashboard'?'Vue d’ensemble':titles[activePage][0]);
  $('period-controls').hidden=!['history','statistics','alarms'].includes(activePage);
  window.scrollTo(0,0);
  if(!settings)return;
  if(['history','statistics','alarms'].includes(activePage))guarded(refreshArchives)();
  requestAnimationFrame(()=>{Object.values(charts).forEach(chart=>chart.resize());historyChart.resize();roseChart.resize();});
}
async function initialize() {
  Chart.defaults.font.family="'Segoe UI', system-ui, sans-serif";Chart.defaults.font.size=10;Chart.defaults.color='#8da2bb';
  for(const [key,color] of Object.entries(colors))charts[key]=makeChart(`chart-${key}`,color);
  historyChart=makeChart('history-chart','#efb16e');roseChart=makeChart('rose-chart','#68d9cf','polarArea');
  settings=await api('/api/settings');renderSettings();setPeriod(1);
  $('archive-source').value=settings.mode;$('archive-station').value=settings.station_number;
  const initial=await api('/api/measurements/recent');recent=initial.items;liveSource=`${settings.mode}:${settings.station_number}`;
  initial.items.forEach(row=>{if(row.peak)peakTimes.set(row.peak.timestamp,row.peak.value);});
  renderSnapshot(await api('/api/measurements/latest'));navigate();connectSocket();await refreshLiveAlarms();
  setInterval(guarded(refreshLiveAlarms),10000);
}
window.addEventListener('hashchange',navigate);
$('apply-period').addEventListener('click',guarded(refreshArchives));
$('history-sensor').addEventListener('change',guarded(refreshArchives));
$('refresh-alarms').addEventListener('click',guarded(refreshArchives));
document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',guarded(async()=>{setPeriod(Number(button.dataset.days));await refreshArchives();})));
$('alarms-body').addEventListener('click',guarded(async event=>{const button=event.target.closest('[data-ack]');if(button){await api(`/api/alarms/${button.dataset.ack}/acknowledge`,{method:'POST'});await refreshArchives();await refreshLiveAlarms();}}));
$('scan-ni').addEventListener('click',guarded(async()=>{text('ni-diagnostics','Recherche en cours…');text('ni-diagnostics',JSON.stringify(await api('/api/ni/devices'),null,2));}));
$('settings-form').addEventListener('submit',guarded(async event=>{
  event.preventDefault();const next=structuredClone(settings);
  document.querySelectorAll('[data-path]').forEach(input=>{const value=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):(input.value.trim()||null);setPath(next,input.dataset.path,value);});
  await saveSettings(next);
}));
$('switch-mode').addEventListener('click',guarded(async()=>{const next=structuredClone(settings);next.mode=settings.mode==='simulation'?'hardware':'simulation';await saveSettings(next);}));
setInterval(()=>text('clock',new Date().toLocaleString('fr-FR',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})),1000);
guarded(initialize)();
