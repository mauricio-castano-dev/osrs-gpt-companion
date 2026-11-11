'use strict';
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf-token"]').content;
let busy = false;
let lastUpdated = null;
let statusOk = false;
let currentModel = null;
let bankSearchVersion = 0;
let bankSearchTimer;
let progressRequestSeq = 0;
let progressSearchTimer;
let lastQuestsSnapshot = null;
let lastStatsSnapshot = null;
let lastItemsSnapshot = null;
const diaryTiers = ['easy','medium','hard','elite'];
const number = (value) => typeof value === 'number' ? new Intl.NumberFormat('es-CO').format(value) : '—';
function relative(stamp) {
  const date = Date.parse(stamp || '');
  if (!Number.isFinite(date)) return 'sin fecha';
  const s = Math.max(0, Math.floor((Date.now() - date) / 1000));
  return s < 60 ? `hace ${s} s` : s < 3600 ? `hace ${Math.floor(s/60)} min` : s < 86400 ? `hace ${Math.floor(s/3600)} h` : `hace ${Math.floor(s/86400)} d`;
}
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : {'Content-Type':'application/json', 'X-CSRF-Token':token}, body: body === undefined ? undefined : JSON.stringify(body), cache:'no-store', credentials:'same-origin'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'No se pudo completar la petición.');
  return data;
}
function node(tag, text, cls) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (cls) item.className = cls;
  return item;
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function refreshAges() {
  $('live-freshness').textContent = 'Reporte: ' + (statusOk ? relative(lastUpdated) : 'sin datos actuales');
  document.querySelectorAll('[data-report]').forEach(el => { el.textContent = 'Reporte: ' + relative(el.dataset.report); });
}
function entries(value) { return Array.isArray(value) ? value : value && Array.isArray(value.entries) ? value.entries : []; }
function gameIcon(name) {
  const icon = node('span',undefined,'game-icon icon-' + name);
  icon.setAttribute('aria-hidden','true');
  return icon;
}
function renderSkills(skills) {
  $('skills').replaceChildren();
  Object.entries(skills || {}).forEach(([name,value]) => {
    const level = typeof value === 'object' && value !== null ? value.level : value;
    const normalized = name.toLowerCase().replace(/[^a-z]/g,'');
    const skill = {runecrafting:'runecraft',defense:'defence'}[normalized] || normalized;
    const cell = node('div',undefined,'skill' + (typeof level === 'number' && level >= 99 ? ' skill-max' : ''));
    cell.setAttribute('data-skill',skill);
    cell.append(node('span',name.replaceAll('_',' '),'skill-name'),node('span',level ?? '—','skill-value'));
    $('skills').append(cell);
  });
  if (!$('skills').children.length) $('skills').append(node('p','No hay habilidades disponibles.','muted'));
}
function activity(title, sub, state) {
  const cls = ['HARVESTABLE','READY','COMPLETE'].includes(state) ? 'ready' : state === 'DEAD' ? 'dead' : 'growing';
  const row = node('div', undefined, 'activity ' + cls);
  row.append(node('strong', title), node('small', sub));
  return row;
}
function renderGear(stats, items, quests) {
  $('equipment').replaceChildren(); $('ge-offers').replaceChildren();
  $('slayer').replaceChildren(); $('quest-progress').replaceChildren();
  $('diary-progress').replaceChildren();
  $('combat-progress').replaceChildren(); $('kill-counts').replaceChildren();
  Object.entries(items.ok ? items.equipment || {} : {}).forEach(([slot,item]) => {
    if (!item || typeof item !== 'object' || (!item.name && !(item.itemId > 0))) return;
    const row = node('div',undefined,'gear-row');
    const slots = {HEAD:'head',CAPE:'cape',AMULET:'neck',NECK:'neck',WEAPON:'attack',BODY:'body',SHIELD:'defence',LEGS:'legs',GLOVES:'hands',HANDS:'hands',BOOTS:'agility',FEET:'agility',RING:'ring',AMMO:'fletching'};
    row.append(gameIcon(slots[slot.toUpperCase()] || 'equipment'),node('small',slot.replaceAll('_',' ')),node('span',item.name || `Objeto #${item.itemId}`));
    $('equipment').append(row);
  });
  if (!$('equipment').children.length) $('equipment').append(node('p',items.ok ? 'No hay equipo registrado.' : 'Equipo no disponible.','muted'));
  const offers = items.ok && Array.isArray(items.grandExchange) ? items.grandExchange : [];
  offers.filter(offer => offer && offer.state !== 'EMPTY' && (offer.name || offer.itemId > 0)).forEach(offer => {
    const row = node('div',undefined,'ge-offer');
    row.append(node('strong',offer.name || `Objeto #${offer.itemId}`),
      node('small',`${offer.state || 'Sin estado'} · ${number(offer.quantitySold)}/${number(offer.totalQuantity)} @ ${number(offer.price)} GP`));
    $('ge-offers').append(row);
  });
  if (!$('ge-offers').children.length) $('ge-offers').append(node('p',items.ok ? 'No hay ofertas activas.' : 'Ofertas no disponibles.','muted'));
  const slayer = stats.ok ? stats.slayer || {} : {};
  if (Object.keys(slayer).length) {
    $('slayer').append(node('p',`${slayer.masterName || 'Maestro sin registrar'} · ${number(slayer.points)} puntos · Racha ${number(slayer.streak)}`,'progress-line'));
    if (slayer.amount > 0) $('slayer').append(node('p',`Tarea activa: ${slayer.creatureName || slayer.taskName || 'ID ' + (slayer.creatureId ?? '—')} · ${number(slayer.amount)} restantes`,'progress-line'));
  } else $('slayer').append(node('p','No hay datos de Slayer.','muted'));
  if (quests.ok) {
    $('quest-progress').append(node('strong','Misiones'),node('p',`${number(quests.finished_count)} completadas · ${number(quests.in_progress_count)} en curso · ${number(quests.not_started_count)} pendientes`));
    const tiers = quests.combatAchievements?.tiers || {};
    Object.entries(tiers).forEach(([tier,counts]) => {
      if (!counts || typeof counts !== 'object') return;
      const row = node('div',undefined,'tier-row');
      row.append(node('span',tier),node('strong',`${number(counts.completed)} / ${number(counts.total)}`));
      $('combat-progress').append(row);
    });
  } else $('quest-progress').append(node('p','Progreso de misiones no disponible.','muted'));
  if (!$('combat-progress').children.length) $('combat-progress').append(node('p','No hay datos de Combat Achievements.','muted'));
  renderDiarySummary(quests);
  Object.entries(stats.ok ? stats.killCounts || {} : {}).filter(([name,count]) => name !== '_omitted' && typeof count === 'number' && count > 0).sort((a,b) => b[1]-a[1]).forEach(([name,count]) => {
    const row = node('div',undefined,'tier-row');
    row.append(node('span',name),node('strong',number(count))); $('kill-counts').append(row);
  });
  if (!$('kill-counts').children.length) $('kill-counts').append(node('p','No hay KC registrados.','muted'));
}
function diaryTierEntries(diary) {
  return diaryTiers.filter(tier => typeof diary?.tiers?.[tier] === 'boolean').map(tier => [tier,diary.tiers[tier]]);
}
function renderDiarySummary(progress) {
  const container = $('diary-progress');
  container.replaceChildren();
  if (!progress?.ok) { container.append(node('p','Diarios no disponibles.','muted')); return; }
  const regions = Object.entries(progress.achievementDiaries || {});
  if (!regions.length) { container.append(node('p','No hay diarios registrados.','muted')); return; }
  let completed = 0, total = 0;
  const rows = regions.map(([region,diary]) => {
    const tiers = diaryTierEntries(diary);
    const done = tiers.filter(([,value]) => value).length;
    completed += done; total += tiers.length;
    const row = node('div',undefined,'tier-row');
    row.append(node('span',region),node('strong',tiers.length ? `${done}/${tiers.length}` : 'Sin tiers registrados'));
    return row;
  });
  container.append(node('p',`${number(completed)} / ${number(total)} tiers completados en ${number(regions.length)} regiones`,'progress-line'),...rows);
}
function renderProgressResults(result) {
  const container = $('progress-results');
  container.replaceChildren();
  if (!result?.ok) { container.append(node('p','Progreso no disponible.','muted')); return; }
  let matches = 0;
  if (result.cached) container.append(node('p','Respaldo del navegador · reporte ' + relative(result.lastUpdated) + '. Resultados parciales; vuelve a consultar cuando el servidor esté disponible.','cache-notice'));
  function row(parent, title, detail, state = '') {
    const classes = {completed:'state-finished',in_progress:'state-in-progress',incomplete:'state-not-started'};
    const entry = node('div',undefined,'progress-entry ' + (classes[state] || ''));
    entry.append(node('strong',title),node('small',detail));
    parent.append(entry);
  }
  const combat = result.combatAchievements;
  const otherMatches = Object.keys(result.achievementDiaries || {}).length || combat?.tasks?.length;
  if (Array.isArray(result.quests) && (result.quests.length || !otherMatches)) {
    container.append(node('h4',`Misiones · ${number(result.total_matches)} coincidencias`,'progress-title'));
    if (result.truncated) container.append(node('p','Se muestran las primeras 40 misiones. Afina la búsqueda.','muted'));
    result.quests.forEach(quest => { row(container,quest.displayName || quest.name,quest.state || 'Sin estado',questStatus(quest.state)); matches++; });
  }
  Object.entries(result.achievementDiaries || {}).forEach(([region,diary]) => {
    const card = node('section',undefined,'progress-card');
    card.append(node('h4',region,'progress-title'));
    const tiers = diaryTierEntries(diary);
    tiers.forEach(([tier,done]) => row(card,tier,done ? 'Completado' : 'Pendiente'));
    if (Array.isArray(diary.tasks)) {
      card.append(node('p',`${number(diary.total_matches)} tareas coincidentes`,'muted'));
      diary.tasks.forEach(task => row(card,`[${task.tier || 'Sin tier'}] ${task.name || 'Sin nombre'}`,task.completed === true ? 'Completado' : task.completed === false ? 'Pendiente' : 'Sin estado'));
      if (diary.truncated) card.append(node('p','Se muestran las primeras 30 tareas del diario.','muted'));
    }
    container.append(card); matches++;
  });
  if (Array.isArray(combat?.tasks) && combat.tasks.length) {
    container.append(node('h4',`Combat Achievements · ${number(combat.total_matches)} coincidencias`,'progress-title'));
    combat.tasks.forEach(task => {
      const state = task.completed === true ? 'Completado' : task.completed === false ? 'Pendiente' : 'Sin estado';
      row(container,task.name || 'Sin nombre',`${task.tier || 'Sin tier'} · ${task.monster || 'Sin jefe'} · ${state}`); matches++;
    });
    if (combat.truncated) container.append(node('p','Se muestran las primeras 25 tareas de combate.','muted'));
  } else if (combat?.available && !Array.isArray(combat.tasks) && !matches) {
    container.append(node('p','Escribe un nombre, jefe o tier para ver las tareas de combate.','muted'));
  }
  if (!matches) container.append(node('p','Sin coincidencias para ese filtro.','muted'));
}
function questStatus(value) {
  return {finished:'completed',completed:'completed',in_progress:'in_progress',not_started:'incomplete',incomplete:'incomplete'}[String(value).toLowerCase()] || 'unknown';
}
function cachedProgress(q, category, status) {
  if (!lastQuestsSnapshot?.ok) return null;
  const snapshot = lastQuestsSnapshot;
  const term = q.trim().toLowerCase();
  const includes = value => String(value ?? '').toLowerCase().includes(term);
  const taskStatus = task => status === 'all' || (status === 'completed' && task.completed === true) || (status === 'incomplete' && task.completed === false);
  const result = {ok:true,cached:true,partial:true,lastUpdated:snapshot.lastUpdated};
  if (category === 'all' || category === 'quests') {
    result.quests = (snapshot.quests || []).filter(quest => (!term || includes(quest.name) || includes(quest.displayName)) && (status === 'all' || questStatus(quest.state) === status));
    result.total_matches = result.quests.length;
    result.truncated = false;
  }
  if (category === 'all' || category === 'diaries') {
    result.achievementDiaries = Object.create(null);
    Object.entries(snapshot.achievementDiaries || {}).forEach(([region,diary]) => {
      const regionMatch = !!term && includes(region);
      const tasks = (diary.tasks || []).filter(task => (regionMatch || (!!term && includes(task.name))) && taskStatus(task));
      const tiers = diaryTierEntries(diary);
      const matchingTier = tiers.some(([,done]) => status === 'all' || (status === 'completed' && done) || (status === 'incomplete' && !done));
      if (term && !regionMatch && !tasks.length) return;
      if (status !== 'all' && !matchingTier && !tasks.length) return;
      result.achievementDiaries[region] = {tiers:{...(diary.tiers || {})},...(term ? {tasks,total_matches:tasks.length} : {})};
    });
  }
  if (category === 'all' || category === 'combat_achievements') {
    const combat = snapshot.combatAchievements || {};
    result.combatAchievements = {available:combat.available,tiers:combat.tiers};
    if (term) {
      const tasks = (combat.tasks || []).filter(task => ['id','name','tier','monster'].some(key => includes(task[key])) && taskStatus(task));
      result.combatAchievements.tasks = tasks;
      result.combatAchievements.total_matches = tasks.length;
    }
  }
  return result;
}
function quickProgressFilter(button) {
  $('progress-category').value = button.dataset.progressCat;
  $('progress-status').value = button.dataset.progressStatus;
  return queueProgressSearch(true);
}
function queueProgressSearch(immediate = false) {
  clearTimeout(progressSearchTimer);
  const seq = ++progressRequestSeq;
  const q = $('progress-search').value.trim();
  const category = $('progress-category').value;
  const status = $('progress-status').value;
  const empty = !q && category === 'all' && status === 'all';
  $('progress-results').replaceChildren(node('p',empty ? 'Escribe o elige un filtro para explorar misiones, diarios o logros de combate en RAM.' : 'Consultando progreso…','muted'));
  if (empty) return;
  const search = async () => {
    try {
      const result = await api(`/api/progress?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&status=${encodeURIComponent(status)}`);
      if (seq === progressRequestSeq) renderProgressResults(result);
    } catch (_) {
      if (seq !== progressRequestSeq) return;
      const fallback = cachedProgress(q,category,status);
      if (fallback) renderProgressResults(fallback);
      else $('progress-results').replaceChildren(node('p','No se pudo consultar el progreso local.','muted'));
    }
  };
  if (immediate === true) return search();
  progressSearchTimer = setTimeout(search,180);
}
function updateThinking(data) {
  const thinking = document.querySelector('.thinking');
  if (!thinking || !data.busy) return;
  const names = Array.isArray(data.active_tools) ? data.active_tools.map(tool => tool?.name).filter(name => typeof name === 'string') : [];
  thinking.textContent = names.length ? 'Consultando: ' + names.join(', ') + '…' : 'El compañero está preparando tu respuesta…';
}
function renderBank(data) {
  const results = $('bank-results');
  results.replaceChildren();
  if (!data.ok) { results.append(node('p','Instantánea no disponible. Comprueba Character Snapshot.','muted')); return; }
  const bank = data.bank || {};
  results.append(node('strong',`Banco: ${number(bank.total_matches)} coincidencias de ${number(bank.bank_total_items)} objetos`));
  function group(title, items) {
    results.append(node('small',title));
    if (!items.length) results.append(node('p','Sin coincidencias.','muted'));
    items.forEach(item => {
      const row = node('div',undefined,'gear-row');
      row.append(node('span',item.name || `Objeto #${item.itemId}`),node('strong',number(item.quantity)));
      results.append(row);
    });
  }
  group('Banco',Array.isArray(bank.items) ? bank.items : []);
  if (bank.truncated) results.append(node('p','Se muestran las primeras 30 coincidencias. Afina la búsqueda.','muted'));
  group('Inventario',Array.isArray(data.inventory) ? data.inventory : []);
}
function queueBankSearch() {
  clearTimeout(bankSearchTimer);
  const version = ++bankSearchVersion;
  const query = $('bank-search').value.trim();
  $('bank-results').replaceChildren(node('p',query ? 'Buscando…' : 'Escribe para buscar entre tus objetos del banco sin gastar tokens.','muted'));
  if (!query) return;
  bankSearchTimer = setTimeout(async () => {
    try {
      const data = await api('/api/bank?q=' + encodeURIComponent(query));
      if (version === bankSearchVersion) renderBank(data);
    } catch (_) {
      if (version === bankSearchVersion) $('bank-results').replaceChildren(node('p','No se pudo consultar el banco local.','muted'));
    }
  },180);
}
async function loadModels() {
  const select = $('model-select');
  try {
    const data = await api('/api/models');
    if (!Array.isArray(data.models) || !data.models.length) return;
    select.replaceChildren();
    data.models.forEach(model => { const option = node('option',model.display_name || model.slug); option.value = model.slug; select.append(option); });
    currentModel = data.current;
    select.value = currentModel;
    select.hidden = false;
  } catch (_) { select.hidden = true; }
}
async function changeModel() {
  const select = $('model-select');
  const previous = currentModel;
  select.disabled = true;
  try {
    const data = await api('/api/model',{model:select.value});
    currentModel = data.model;
    select.value = currentModel;
    $('model-label').textContent = 'Usando tu plan de ChatGPT · ' + currentModel;
    error('');
  } catch(e) { select.value = previous; error(e.message); }
  finally { select.disabled = busy; }
}
async function refreshStatus() {
  try {
    const data = await api('/api/status');
    const stats = data.stats || {}, items = data.items || {};
    lastQuestsSnapshot = data.quests || null;
    lastStatsSnapshot = stats;
    lastItemsSnapshot = items;
    statusOk = stats.ok === true && items.ok === true;
    lastUpdated = data.lastUpdated;
    $('connection').className = 'connection' + (statusOk ? ' ready' : '');
    $('connection').replaceChildren(node('i'), document.createTextNode(statusOk ? 'Instantánea disponible' : 'Esperando instantánea'));
    const player = statusOk ? stats.player || {} : {};
    $('player-name').textContent = player.username || 'Sin personaje disponible';
    $('player-meta').textContent = statusOk ? `Combate ${player.combatLevel ?? '—'} · Mundo ${player.world ?? '—'}` : 'Comprueba el archivo de Character Snapshot.';
    $('quest-points').textContent = number(stats.ok ? stats.questPoints : null);
    const currency = items.currency || {};
    $('gold').textContent = statusOk && currency.bank && currency.inventory ? number(currency.bank.gp_equivalent + currency.inventory.gp_equivalent) : '—';
    $('model-label').textContent = 'Usando tu plan de ChatGPT · ' + data.model;
    $('model-select').disabled = busy || data.busy;
    $('state-path').textContent = data.state_file;
    renderSkills(statusOk ? stats.skills : {});
    const timers = statusOk ? stats.timers || {} : {};
    $('farming').replaceChildren(); $('birdhouses').replaceChildren();
    entries(timers.farming).forEach(patch => {
      if (patch && typeof patch === 'object') $('farming').append(activity(patch.crop || patch.patch || 'Parche', `${patch.patch || patch.region || 'Farming'} · ${patch.state || 'Sin estado'}`, patch.state));
    });
    const count = timers.farming?.active_count;
    $('patch-count').textContent = typeof count === 'number' ? `${count} ACTIVOS` : '';
    entries(timers.birdhouses).forEach(house => {
      if (house && typeof house === 'object') $('birdhouses').append(activity('Birdhouse · ' + (house.house || 'Trampa'), `${house.space || 'Fossil Island'} · ${house.state || 'Sin estado'}`, house.state));
    });
    if (!$('farming').children.length && !$('birdhouses').children.length) $('farming').append(node('p','No hay actividades registradas.','muted'));
    renderGear(stats,items,data.quests || {});
    updateThinking(data);
    refreshAges();
  } catch (_) {
    statusOk = false;
    $('connection').className = 'connection';
    $('connection').textContent = 'Servidor local desconectado';
    refreshAges();
  }
}
async function refreshMemories() {
  try {
    const data = await api('/api/memories');
    $('memory-count').textContent = `(${data.memories.length})`;
    $('memories').replaceChildren();
    if (!data.memories.length) $('memories').append(node('p','Todavía no hay memorias. Cuéntale al compañero qué quieres recordar.','muted'));
    data.memories.forEach(memory => {
      const card = node('article',undefined,'memory'), content = node('div',undefined,'memory-body');
      content.append(node('strong',memory.tema),node('p',memory.contenido),node('small',`MEMORIA #${memory.id}`));
      const remove = node('button','✕','forget');
      remove.type = 'button'; remove.title = 'Olvidar esta memoria'; remove.setAttribute('aria-label', `Olvidar memoria ${memory.id}: ${memory.tema}`);
      remove.addEventListener('click', async () => { remove.disabled = true; try { await api('/api/memories/delete',{id:memory.id}); await refreshMemories(); } catch(e) { error(e.message); remove.disabled = false; } });
      card.append(content,remove); $('memories').append(card);
    });
  } catch(e) { error(e.message); }
}
function inline(parent, text) {
  // Construye nodos; ningun texto del jugador, memoria o modelo se interpreta como HTML.
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;
  let start = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(start,match.index)));
    if (match[2]) parent.append(node('strong',match[2]));
    else if (match[3]) parent.append(node('code',match[3]));
    else { const link = node('a',match[4]); link.href = match[5]; link.target = '_blank'; link.rel = 'noopener noreferrer'; parent.append(link); }
    start = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(start)));
}
function markdown(parent, text) {
  let code = null;
  let list = null;
  for (const line of text.split('\n')) {
    if (line.startsWith('```')) { list = null; code = code ? null : node('pre'); if (code) parent.append(code); continue; }
    if (code) { code.append(document.createTextNode(line+'\n')); continue; }
    if (!line.trim()) { list = null; continue; }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) { list = null; const title = node('h4'); inline(title,heading[1]); parent.append(title); continue; }
    const item = line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)$/);
    if (item) {
      if (!list) { list = node('ul'); parent.append(list); }
      const entry = node('li'); inline(entry,item[1]); list.append(entry); continue;
    }
    list = null;
    const paragraph = node('p'); inline(paragraph, line); parent.append(paragraph);
  }
}
function bubble(text, role, data) {
  $('welcome')?.remove();
  const card = node('article',undefined,'bubble '+role);
  const content = node('div',undefined,'bubble-content');
  if (role === 'assistant') markdown(content,text); else content.textContent = text;
  card.append(node('div',role === 'user' ? 'Tú' : 'Companion','bubble-label'),content);
  if (data) {
    const chips = node('div',undefined,'tool-chips');
    const icons = {query_player_stats:'⚔',query_player_bank:'🎒',query_quests_and_diaries:'🧭',check_ge_price:'💰',search_osrs_wiki:'📖',save_agent_memory:'🧠',recall_agent_memory:'🔮'};
    data.tools_used.forEach(tool => chips.append(node('span',`${icons[tool.name] || '✦'} ${tool.name}${tool.ok ? '' : ' · sin datos'}`,'tool-chip'+(tool.ok ? '' : ' failed'))));
    card.append(chips);
    const age = node('small','Reporte: '+data.freshness,'freshness'); age.dataset.report = data.lastUpdated || ''; card.append(age);
  }
  $('conversation').append(card); $('conversation').scrollTop = $('conversation').scrollHeight;
}
async function submit(message) {
  if (busy || !message.trim()) return;
  busy = true; error(''); $('send').disabled = true; $('clear').disabled = true;
  $('model-select').disabled = true;
  if (message !== '/limpiar') bubble(message,'user');
  const waiting = node('div','El compañero está preparando tu respuesta…','thinking'); $('conversation').append(waiting);
  const fastPoll = setInterval(refreshStatus,600);
  try {
    const data = await api('/api/chat',{message});
    if (message === '/limpiar') $('conversation').replaceChildren();
    bubble(data.reply,'assistant',data);
    await Promise.all([refreshStatus(),refreshMemories()]);
  } catch(e) { error(e.message); }
  finally { clearInterval(fastPoll); waiting.remove(); busy = false; $('send').disabled = false; $('clear').disabled = false; $('model-select').disabled = false; $('message').focus(); }
}
function tab(selected) {
  for (const name of ['state','gear','memory']) {
    $(name+'-content').hidden = name !== selected;
    $('tab-'+name).classList.toggle('selected',name === selected);
    $('tab-'+name).setAttribute('aria-selected',String(name === selected));
    $('tab-'+name).setAttribute('tabindex',name === selected ? '0' : '-1');
  }
  if (selected === 'memory') refreshMemories();
}
$('chat-form').addEventListener('submit',event => { event.preventDefault(); const text=$('message').value.trim(); if (!busy && text) { $('message').value=''; submit(text); } });
$('message').addEventListener('keydown',event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); } });
$('clear').addEventListener('click',()=>submit('/limpiar'));
$('bank-search').addEventListener('input',queueBankSearch);
$('progress-search').addEventListener('input',() => queueProgressSearch());
$('progress-category').addEventListener('change',() => queueProgressSearch(true));
$('progress-status').addEventListener('change',() => queueProgressSearch(true));
document.querySelectorAll('[data-progress-cat]').forEach(button => button.addEventListener('click',() => quickProgressFilter(button)));
$('model-select').addEventListener('change',changeModel);
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click',()=>{ $('message').value=button.dataset.question; $('message').focus(); }));
const tabs = ['state','gear','memory'];
tabs.forEach((name,index) => {
  $('tab-'+name).addEventListener('click',()=>tab(name));
  $('tab-'+name).addEventListener('keydown',event => {
    let target;
    if (event.key === 'ArrowRight') target = tabs[(index+1)%tabs.length];
    if (event.key === 'ArrowLeft') target = tabs[(index+tabs.length-1)%tabs.length];
    if (event.key === 'Home') target = tabs[0];
    if (event.key === 'End') target = tabs[tabs.length-1];
    if (target) { event.preventDefault(); tab(target); $('tab-'+target).focus(); }
  });
});
refreshStatus(); refreshMemories(); loadModels(); setInterval(refreshStatus,3000); setInterval(refreshAges,1000);
