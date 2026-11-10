'use strict';
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="csrf-token"]').content;
let busy = false;
let lastUpdated = null;
let statusOk = false;
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
function activity(title, sub, state) {
  const cls = ['HARVESTABLE','READY','COMPLETE'].includes(state) ? 'ready' : state === 'DEAD' ? 'dead' : 'growing';
  const row = node('div', undefined, 'activity ' + cls);
  row.append(node('strong', title), node('small', sub));
  return row;
}
async function refreshStatus() {
  try {
    const data = await api('/api/status');
    const stats = data.stats || {}, items = data.items || {};
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
    $('state-path').textContent = data.state_file;
    $('skills').replaceChildren();
    Object.entries(statusOk ? stats.skills || {} : {}).forEach(([name,value]) => {
      const cell = node('div', undefined, 'skill');
      cell.append(node('span', name.replaceAll('_',' '), 'skill-name'), node('span', typeof value === 'object' && value !== null ? value.level ?? '—' : value, 'skill-value'));
      $('skills').append(cell);
    });
    if (!$('skills').children.length) $('skills').append(node('p','No hay habilidades disponibles.','muted'));
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
  for (const line of text.split('\n')) {
    if (line.startsWith('```')) { code = code ? null : node('pre'); if (code) parent.append(code); continue; }
    if (code) { code.append(document.createTextNode(line+'\n')); continue; }
    const paragraph = node('p'); inline(paragraph, line.replace(/^#{1,4}\s/,'')); parent.append(paragraph);
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
    const icons = {check_ge_price:'💰', search_osrs_wiki:'🔍', save_agent_memory:'◇',recall_agent_memory:'◇'};
    data.tools_used.forEach(tool => chips.append(node('span',`${icons[tool.name] || '✦'} ${tool.name}${tool.ok ? '' : ' · sin datos'}`,'tool-chip'+(tool.ok ? '' : ' failed'))));
    card.append(chips);
    const age = node('small','Reporte: '+data.freshness,'freshness'); age.dataset.report = data.lastUpdated || ''; card.append(age);
  }
  $('conversation').append(card); $('conversation').scrollTop = $('conversation').scrollHeight;
}
async function submit(message) {
  if (busy || !message.trim()) return;
  busy = true; error(''); $('send').disabled = true; $('clear').disabled = true;
  if (message !== '/limpiar') bubble(message,'user');
  const waiting = node('div','El compañero está preparando tu respuesta…','thinking'); $('conversation').append(waiting);
  try {
    const data = await api('/api/chat',{message});
    if (message === '/limpiar') $('conversation').replaceChildren();
    bubble(data.reply,'assistant',data);
    await Promise.all([refreshStatus(),refreshMemories()]);
  } catch(e) { error(e.message); }
  finally { waiting.remove(); busy = false; $('send').disabled = false; $('clear').disabled = false; $('message').focus(); }
}
$('chat-form').addEventListener('submit',event => { event.preventDefault(); const text=$('message').value.trim(); if (!busy && text) { $('message').value=''; submit(text); } });
$('message').addEventListener('keydown',event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); } });
$('clear').addEventListener('click',()=>submit('/limpiar'));
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click',()=>{ $('message').value=button.dataset.question; $('message').focus(); }));
function tab(memory) { $('memory-content').hidden=!memory; $('state-content').hidden=memory; $('tab-memory').classList.toggle('selected',memory); $('tab-state').classList.toggle('selected',!memory); $('tab-memory').setAttribute('aria-selected',String(memory)); $('tab-state').setAttribute('aria-selected',String(!memory)); if(memory) refreshMemories(); }
$('tab-state').addEventListener('click',()=>tab(false)); $('tab-memory').addEventListener('click',()=>tab(true));
refreshStatus(); refreshMemories(); setInterval(refreshStatus,3000); setInterval(refreshAges,1000);
