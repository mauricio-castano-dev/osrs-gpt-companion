/* Unit tests for pure rendering logic, using a synthetic DOM and no browser. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.dataset = {}; this.hidden = false; this.ownText = ''; this.className = ''; this.classList = {toggle: () => {}}; }
  remove() { this.removed = true; }
  focus() { this.focused = true; }
  addEventListener(type, handler) { (this.listeners ||= {})[type] = handler; }
  get textContent() { return this.ownText + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  set innerHTML(_) { throw new Error('Unsafe HTML assignment'); }
  append(...children) { for (let child of children) { if (typeof child === 'string') child = Object.assign(new Element('#text'),{ownText:child}); child.parentElement = this; this.children.push(child); } }
  replaceChildren(...children) { this.children = []; this.ownText = ''; this.append(...children); }
  setAttribute(key,value) { this.attributes[key] = value; }
}
function setup() {
  const elements = new Map();
  const byId = id => { if (!elements.has(id)) elements.set(id,new Element('div')); return elements.get(id); };
  const document = {
    getElementById: byId,
    querySelector: selector => selector.startsWith('meta') ? {content:'test-token'} : selector === '.thinking' ? elements.get('thinking') || null : null,
    querySelectorAll: () => [],
    createElement: tag => new Element(tag),
    createTextNode: text => Object.assign(new Element('#text'),{ownText:String(text)}),
  };
  const source = fs.readFileSync(path.join(__dirname,'..','ui','app.js'),'utf8');
  const timers = new Map(), cleared = [];
  let nextTimer = 0;
  const context = vm.createContext({document, Intl, Date, Number, console, encodeURIComponent,
    setTimeout: (fn,delay) => { const id = ++nextTimer; timers.set(id,{fn,delay}); return id; },
    clearTimeout: id => timers.delete(id),
    setInterval: (fn,delay) => { const id = ++nextTimer; timers.set(id,{fn,delay}); return id; },
    clearInterval: id => { cleared.push(id); timers.delete(id); },
  });
  vm.runInContext(source.split("$('chat-form').addEventListener")[0],context);
  return {context, byId, timers, cleared};
}
function descendants(element, tag) { return element.children.flatMap(child => [...(child.tagName === tag ? [child] : []),...descendants(child,tag)]); }

test('Markdown groups bullet and numbered lines and ignores blank paragraphs',()=>{
  const {context} = setup(), parent = new Element('div');
  context.markdown(parent,'# Heading\n\n- **First**\n* Second\n1. Third\n2. Fourth\n\n\nParagraph');
  assert.deepEqual(parent.children.map(child=>child.tagName),['H4','UL','P']);
  assert.equal(descendants(parent,'LI').length,4);
  assert.equal(descendants(parent,'STRONG')[0].textContent,'First');
  assert.equal(descendants(parent,'P').length,1);
});
test('Markdown code fences preserve literal text and headings stay readable',()=>{
  const {context} = setup(), parent = new Element('div');
  context.markdown(parent,'## Two\n### Three\n```html\n<script>fake()</script>\n- code line\n```\nAfter');
  assert.equal(descendants(parent,'H4').length,2);
  assert.equal(descendants(parent,'PRE')[0].textContent,'<script>fake()</script>\n- code line\n');
  assert.equal(descendants(parent,'SCRIPT').length,0);
  assert.equal(descendants(parent,'LI').length,0);
});
test('Untrusted Markdown stays text and javascript links are never created',()=>{
  const {context} = setup(), parent = new Element('div');
  context.markdown(parent,'<img src=x onerror=fake()>\n- [bad](javascript:fake)\n- [Wiki](https://oldschool.runescape.wiki/)');
  assert.equal(descendants(parent,'IMG').length,0);
  assert.equal(descendants(parent,'A').length,1);
  assert.equal(descendants(parent,'A')[0].href,'https://oldschool.runescape.wiki/');
  assert.match(parent.textContent,/<img/);
});
test('Gear, GE, Slayer, quests, combat tiers and KC use their exported fields',()=>{
  const {context,byId} = setup();
  context.renderGear({ok:true,slayer:{masterName:'Example Master',points:150,streak:30,amount:25,creatureId:1},killCounts:{'example boss':7,'_omitted':50}},
    {ok:true,equipment:{HEAD:{name:'Example helmet',itemId:1},EMPTY:{}},grandExchange:[{name:'Onion seed',state:'BUYING',quantitySold:4800,totalQuantity:10000,price:2},{name:'Unused',state:'EMPTY'}]},
    {ok:true,finished_count:40,in_progress_count:2,not_started_count:10,combatAchievements:{tiers:{EASY:{completed:3,total:10}}}});
  assert.match(byId('equipment').textContent,/HEADExample helmet/);
  assert.match(byId('ge-offers').textContent,/Onion seedBUYING.*4\.800\/10\.000 @ 2 GP/);
  assert.doesNotMatch(byId('ge-offers').textContent,/Unused/);
  assert.match(byId('slayer').textContent,/Example Master.*150 puntos.*30/);
  assert.match(byId('slayer').textContent,/25 restantes/);
  assert.match(byId('quest-progress').textContent,/40 completadas.*2 en curso.*10 pendientes/);
  assert.match(byId('combat-progress').textContent,/EASY3 \/ 10/);
  assert.equal(byId('kill-counts').textContent,'example boss7');
});
test('Gear hides stale values, handles missing data and never interprets HTML',()=>{
  const {context,byId} = setup();
  context.renderGear({ok:true,killCounts:{}},{ok:true,equipment:{HEAD:{name:'<script>unsafe</script>'}}},{ok:true});
  assert.equal(descendants(byId('equipment'),'SCRIPT').length,0);
  context.renderGear({ok:false,slayer:{masterName:'STALE'}},{ok:false,equipment:{HEAD:{name:'STALE'}}},{ok:false});
  assert.doesNotMatch(byId('equipment').textContent,/STALE/);
  assert.doesNotMatch(byId('slayer').textContent,/STALE/);
  assert.match(byId('ge-offers').textContent,/no disponibles/);
});
test('Live thinking label reflects completed tool calls only while busy',()=>{
  const {context,byId} = setup(), waiting = byId('thinking');
  context.updateThinking({busy:true,active_tools:[{name:'query_player_stats'},{name:'check_ge_price'}]});
  assert.equal(waiting.textContent,'Consultando: query_player_stats, check_ge_price…');
  context.updateThinking({busy:true,active_tools:[]});
  assert.match(waiting.textContent,/preparando/i);
  context.updateThinking({busy:false,active_tools:[{name:'old'}]});
  assert.doesNotMatch(waiting.textContent,/old/);
});
test('Third tab toggles visibility and keeps ARIA state synchronized',()=>{
  const {context,byId} = setup();
  context.tab('gear');
  assert.equal(byId('gear-content').hidden,false);
  assert.equal(byId('state-content').hidden,true);
  assert.equal(byId('memory-content').hidden,true);
  assert.equal(byId('tab-gear').attributes['aria-selected'],'true');
  assert.equal(byId('tab-gear').attributes.tabindex,'0');
  assert.equal(byId('tab-memory').attributes.tabindex,'-1');
});

test('Bank results show totals, quantities, limits and treat item names as text',()=>{
  const {context,byId} = setup();
  context.renderBank({ok:true,bank:{total_matches:35,bank_total_items:802,truncated:true,items:[{name:'<img src=x onerror=fake()>',quantity:5000}]},inventory:[{name:'Fire rune',quantity:12}]});
  assert.match(byId('bank-results').textContent,/35 coincidencias de 802 objetos/);
  assert.match(byId('bank-results').textContent,/5\.000/);
  assert.match(byId('bank-results').textContent,/primeras 30/);
  assert.match(byId('bank-results').textContent,/InventarioFire rune12/);
  assert.equal(descendants(byId('bank-results'),'IMG').length,0);
  context.renderBank({ok:false});
  assert.match(byId('bank-results').textContent,/no disponible/);
  assert.doesNotMatch(byId('bank-results').textContent,/Fire rune/);
});

test('Bank input debounces, encodes queries and ignores out-of-order responses',async()=>{
  const {context,byId,timers} = setup();
  const pending = [], calls = [];
  context.api = query => { calls.push(query); return new Promise(resolve => pending.push(resolve)); };
  byId('bank-search').value = 'rune & ore';
  context.queueBankSearch();
  assert.equal(timers.size,1);
  const first = [...timers.values()][0];
  assert.equal(first.delay,180);
  const firstRequest = first.fn();
  assert.equal(calls[0],'/api/bank?q=rune%20%26%20ore');
  byId('bank-search').value = 'coins';
  context.queueBankSearch();
  const secondRequest = [...timers.values()][0].fn();
  pending[1]({ok:true,bank:{total_matches:1,bank_total_items:802,items:[{name:'Coins',quantity:1}]}});
  await secondRequest;
  pending[0]({ok:true,bank:{items:[{name:'STALE',quantity:1}]}});
  await firstRequest;
  assert.match(byId('bank-results').textContent,/Coins/);
  assert.doesNotMatch(byId('bank-results').textContent,/STALE/);
  byId('bank-search').value = '';
  context.queueBankSearch();
  assert.equal(timers.size,0);
  assert.match(byId('bank-results').textContent,/Escribe para buscar/);
  assert.equal(calls.length,2);
});

test('Model selector loads safe options, persists change and restores selection on error',async()=>{
  const {context,byId} = setup();
  const calls = [];
  context.api = async (path,body) => { calls.push([path,body]); return path === '/api/models' ? {current:'first',models:[{slug:'first',display_name:'<script>fake()</script>'},{slug:'second'}]} : {model:'second'}; };
  await context.loadModels();
  const select = byId('model-select');
  assert.equal(select.hidden,false);
  assert.equal(select.value,'first');
  assert.equal(select.children.length,2);
  assert.equal(descendants(select,'SCRIPT').length,0);
  select.value = 'second';
  await context.changeModel();
  assert.equal(calls[1][0],'/api/model');
  assert.equal(calls[1][1].model,'second');
  assert.match(byId('model-label').textContent,/second/);
  context.api = async () => { throw new Error('Offline'); };
  select.value = 'first';
  await context.changeModel();
  assert.equal(select.value,'second');
  assert.equal(select.disabled,false);
  await context.loadModels();
  assert.equal(select.hidden,true);
});

test('Offline catalog stays hidden without displaying an intrusive error',async()=>{
  const {context,byId} = setup();
  byId('model-select').hidden = true;
  context.api = async () => { throw new Error('Offline'); };
  await context.loadModels();
  assert.equal(byId('model-select').hidden,true);
  assert.equal(byId('error').textContent,'');
});

test('Fast polling runs every 600 ms and always clears on success or failure',async()=>{
  for (const fail of [false,true]) {
    const {context,byId,timers,cleared} = setup();
    let finish;
    context.api = () => new Promise((resolve,reject) => { finish = () => fail ? reject(new Error('Offline')) : resolve({reply:'Done'}); });
    context.bubble = () => {};
    context.refreshStatus = async () => {};
    context.refreshMemories = async () => {};
    const request = context.submit('Hello');
    assert.equal(timers.size,1);
    assert.equal([...timers.values()][0].delay,600);
    assert.equal(byId('model-select').disabled,true);
    finish();
    await request;
    assert.equal(timers.size,0);
    assert.equal(cleared.length,1);
    assert.equal(byId('model-select').disabled,false);
    assert.equal(byId('send').disabled,false);
  }
});

test('Diary summary counts exported boolean tiers, treats regions as text and clears stale state',()=>{
  const {context,byId} = setup();
  context.renderGear({ok:true},{ok:true},{ok:true,achievementDiaries:{
    ARDOUGNE:{tiers:{easy:true,medium:true,hard:true,elite:true}},
    '<img src=x onerror=fake()>':{tiers:{easy:true,medium:true,hard:true,elite:false}},
  }});
  const summary = byId('diary-progress');
  assert.match(summary.textContent,/7 \/ 8 tiers completados en 2 regiones/);
  assert.match(summary.textContent,/ARDOUGNE4\/4/);
  assert.match(summary.textContent,/3\/4/);
  assert.equal(descendants(summary,'IMG').length,0);
  context.renderGear({ok:false},{ok:false},{ok:false,achievementDiaries:{STALE:{tiers:{easy:true}}}});
  assert.equal(summary.textContent,'Diarios no disponibles.');
  context.renderGear({ok:true},{ok:true},{ok:true});
  assert.match(summary.textContent,/No hay diarios/);
});

test('Progress explorer renders quest, diary and combat details with limits and safe text',()=>{
  const {context,byId} = setup();
  context.renderProgressResults({ok:true,total_matches:50,truncated:true,
    quests:[{displayName:'<script>quest()</script>',name:'Fallback',state:'IN_PROGRESS'}],
    achievementDiaries:{'<img src=x>':{tiers:{easy:true,hard:false},total_matches:31,truncated:true,
      tasks:[{tier:'easy',name:'<script>task()</script>',completed:true},{tier:'hard',name:'Pending diary',completed:false}]}},
    combatAchievements:{total_matches:30,truncated:true,tasks:[{name:'<img src=x onerror=fake()>',tier:'HARD',monster:'<script>boss()</script>',completed:false}]}});
  const results = byId('progress-results');
  assert.match(results.textContent,/50 coincidencias/);
  assert.match(results.textContent,/primeras 40/);
  assert.match(results.textContent,/IN_PROGRESS/);
  assert.match(results.textContent,/\[easy\].*Completado/);
  assert.match(results.textContent,/Pending diaryPendiente/);
  assert.match(results.textContent,/primeras 30/);
  assert.match(results.textContent,/HARD.*boss.*Pendiente/);
  assert.match(results.textContent,/primeras 25/);
  assert.doesNotMatch(results.textContent,/Sin coincidencias/);
  assert.equal(descendants(results,'SCRIPT').length,0);
  assert.equal(descendants(results,'IMG').length,0);
});

test('Progress handles unavailable, empty and summary-only combat results',()=>{
  const {context,byId} = setup();
  context.renderProgressResults({ok:true,quests:[{name:'Fallback quest',state:'FINISHED'}],total_matches:1});
  assert.match(byId('progress-results').textContent,/Fallback questFINISHED/);
  for (const result of [undefined,{ok:false,quests:[{name:'STALE'}]}]) {
    context.renderProgressResults(result);
    assert.equal(byId('progress-results').textContent,'Progreso no disponible.');
  }
  context.renderProgressResults({ok:true,quests:[],achievementDiaries:{},combatAchievements:{tasks:[],total_matches:0},total_matches:0});
  assert.match(byId('progress-results').textContent,/Sin coincidencias para ese filtro/);
  context.renderProgressResults({ok:true,combatAchievements:{available:true,tiers:{}}});
  assert.match(byId('progress-results').textContent,/Escribe un nombre, jefe o tier/);
});

test('Progress search debounces 180 ms, encodes all fields and discards out-of-order responses',async()=>{
  const {context,byId,timers} = setup();
  const pending = [], calls = [];
  context.api = path => { calls.push(path); return new Promise(resolve => pending.push(resolve)); };
  byId('progress-search').value = '  Dragon & ore  ';
  byId('progress-category').value = 'combat_achievements';
  byId('progress-status').value = 'incomplete';
  context.queueProgressSearch();
  const first = [...timers.values()][0];
  assert.equal(first.delay,180);
  assert.equal(calls.length,0);
  const old = first.fn();
  assert.equal(calls[0],'/api/progress?q=Dragon%20%26%20ore&category=combat_achievements&status=incomplete');
  byId('progress-search').value = 'New';
  context.queueProgressSearch();
  const latest = [...timers.values()][0].fn();
  pending[1]({ok:true,quests:[{name:'NEW',state:'FINISHED'}],total_matches:1});
  await latest;
  pending[0]({ok:true,quests:[{name:'STALE',state:'FINISHED'}],total_matches:1});
  await old;
  assert.match(byId('progress-results').textContent,/NEW/);
  assert.doesNotMatch(byId('progress-results').textContent,/STALE/);
});

test('Empty default progress filters cancel timers and invalidate pending requests without fetching',async()=>{
  const {context,byId,timers} = setup();
  let resolve, calls = 0;
  context.api = () => { calls++; return new Promise(done => { resolve = done; }); };
  byId('progress-search').value = 'Quest';
  byId('progress-category').value = 'all'; byId('progress-status').value = 'all';
  context.queueProgressSearch();
  const pending = [...timers.values()][0].fn();
  byId('progress-search').value = '  ';
  context.queueProgressSearch();
  assert.equal(timers.size,0);
  resolve({ok:true,quests:[{name:'STALE'}]});
  await pending;
  assert.match(byId('progress-results').textContent,/Escribe o elige un filtro/);
  assert.doesNotMatch(byId('progress-results').textContent,/STALE/);
  assert.equal(calls,1);
  context.queueProgressSearch(true);
  assert.equal(calls,1);
});

test('Progress selectors search immediately without text and errors stay local',async()=>{
  const {context,byId,timers} = setup();
  const calls = [];
  byId('progress-search').value = '';
  byId('progress-category').value = 'diaries'; byId('progress-status').value = 'completed';
  context.api = async path => { calls.push(path); return {ok:true,achievementDiaries:{EXAMPLE:{tiers:{easy:true}}}}; };
  await context.queueProgressSearch(true);
  assert.equal(timers.size,0);
  assert.equal(calls[0],'/api/progress?q=&category=diaries&status=completed');
  assert.match(byId('progress-results').textContent,/EXAMPLEeasyCompletado/);
  context.api = async () => { throw new Error('Offline'); };
  await context.queueProgressSearch(true);
  assert.equal(byId('progress-results').textContent,'No se pudo consultar el progreso local.');
  assert.equal(byId('error').textContent,'');
});

test('Mixed progress results omit empty category headings and retain quest status classes',()=>{
  const {context,byId} = setup();
  context.renderProgressResults({ok:true,quests:[],total_matches:0,achievementDiaries:{},
    combatAchievements:{tasks:[{name:'Example boss challenge',tier:'EASY',completed:true}],total_matches:1}});
  assert.doesNotMatch(byId('progress-results').textContent,/Misiones · 0/);
  assert.match(byId('progress-results').textContent,/Combat Achievements · 1/);
  context.renderProgressResults({ok:true,total_matches:3,quests:[{name:'Quest A',state:'FINISHED'},
    {name:'Quest B',state:'IN_PROGRESS'},{name:'Quest C',state:'NOT_STARTED'}],achievementDiaries:{},combatAchievements:{tasks:[],total_matches:0}});
  assert.doesNotMatch(byId('progress-results').textContent,/Combat Achievements/);
  const classes = descendants(byId('progress-results'),'DIV').map(el => el.className);
  for (const name of ['state-finished','state-in-progress','state-not-started']) assert.ok(classes.some(value => value.includes(name)));
  context.renderProgressResults({ok:true,quests:[],total_matches:0,achievementDiaries:{},combatAchievements:{tasks:[]}});
  assert.match(byId('progress-results').textContent,/Misiones · 0/);
  assert.match(byId('progress-results').textContent,/Sin coincidencias/);
});

test('Skill levels 99 and above are highlighted and all 24 skills have local SVG sprites',()=>{
  const {context,byId} = setup();
  context.renderSkills({ATTACK:{level:99},Strength:98,SAILING:{level:100},RUNECRAFTING:{level:50},'<img src=x>':1});
  const cells = byId('skills').children;
  assert.equal(cells[0].attributes['data-skill'],'attack');
  assert.match(cells[0].className,/skill-max/);
  assert.doesNotMatch(cells[1].className,/skill-max/);
  assert.equal(cells[2].attributes['data-skill'],'sailing');
  assert.match(cells[2].className,/skill-max/);
  assert.equal(cells[3].attributes['data-skill'],'runecraft');
  assert.equal(descendants(byId('skills'),'IMG').length,0);
  const css = fs.readFileSync(path.join(__dirname,'..','ui','app.css'),'utf8');
  for (const name of ['attack','strength','defence','ranged','prayer','magic','runecraft','construction','hitpoints','agility','herblore','thieving','crafting','fletching','slayer','hunter','mining','smithing','fishing','cooking','firemaking','woodcutting','farming','sailing']) {
    assert.ok(css.includes('.skill[data-skill="'+name+'"]::before'),name);
  }
  assert.match(css,/data:image\/svg\+xml/);
  assert.match(css,/image-rendering:pixelated/);
  context.renderSkills({});
  assert.match(byId('skills').textContent,/No hay habilidades/);
});

test('Each quick filter immediately sends its category and status while preserving the query',async()=>{
  const {context,byId,timers} = setup();
  const calls = [];
  byId('progress-search').value = 'Quest';
  context.api = async url => { calls.push(url); return {ok:true}; };
  for (const [category,status] of [['quests','in_progress'],['quests','incomplete'],['quests','completed'],['diaries','incomplete']]) {
    const button = new Element('button'); button.dataset = {progressCat:category,progressStatus:status};
    await context.quickProgressFilter(button);
    assert.equal(calls.at(-1),'/api/progress?q=Quest&category='+category+'&status='+status);
    assert.equal(byId('progress-category').value,category);
    assert.equal(byId('progress-status').value,status);
  }
  assert.equal(timers.size,0);
});

test('Status snapshots enable a clearly partial local fallback and fresh invalid state disables it',async()=>{
  const {context,byId} = setup();
  const snapshot = {ok:true,lastUpdated:'2026-11-10T00:00:00Z',truncated:true,quests:[
    {name:'Example quest',state:'IN_PROGRESS'},{name:'Other quest',state:'FINISHED'}],achievementDiaries:{},combatAchievements:{available:false}};
  context.api = async () => ({quests:snapshot,stats:{ok:true,skills:{}},items:{ok:true},model:'test'});
  await context.refreshStatus();
  const before = JSON.stringify(snapshot);
  byId('progress-search').value = 'Example'; byId('progress-category').value = 'quests'; byId('progress-status').value = 'in_progress';
  let calls = 0;
  context.api = async () => { calls++; throw new Error('Offline'); };
  await context.queueProgressSearch(true);
  assert.equal(calls,1);
  assert.match(byId('progress-results').textContent,/Respaldo del navegador/);
  assert.match(byId('progress-results').textContent,/Resultados parciales/);
  assert.match(byId('progress-results').textContent,/Example questIN_PROGRESS/);
  assert.doesNotMatch(byId('progress-results').textContent,/Other quest/);
  assert.equal(JSON.stringify(snapshot),before);
  context.api = async () => ({quests:{ok:false},stats:{ok:false},items:{ok:false}});
  await context.refreshStatus();
  context.api = async () => { throw new Error('Offline'); };
  await context.queueProgressSearch(true);
  assert.equal(byId('progress-results').textContent,'No se pudo consultar el progreso local.');
});

test('Cached diary and combat detail filtering remains safe and does not mutate its snapshot',async()=>{
  const {context,byId} = setup();
  const snapshot = {ok:true,quests:[],achievementDiaries:{EXAMPLE:{tiers:{easy:true,hard:false},tasks:[
    {name:'<img src=x>',tier:'hard',completed:false},{name:'Done task',tier:'easy',completed:true}]}},
    combatAchievements:{available:true,tasks:[{name:'<script>task()</script>',monster:'Example boss',tier:'EASY',completed:false},{name:'Done',monster:'Example boss',completed:true}]}};
  context.api = async () => ({quests:snapshot,stats:{ok:true},items:{ok:true}});
  await context.refreshStatus();
  const diary = context.cachedProgress('example','diaries','incomplete');
  assert.equal(diary.achievementDiaries.EXAMPLE.tasks.length,1);
  context.renderProgressResults(diary);
  assert.equal(descendants(byId('progress-results'),'IMG').length,0);
  const combat = context.cachedProgress('example boss','combat_achievements','incomplete');
  assert.equal(combat.combatAchievements.tasks.length,1);
  context.renderProgressResults(combat);
  assert.equal(descendants(byId('progress-results'),'SCRIPT').length,0);
  assert.equal(snapshot.combatAchievements.tasks.length,2);
  assert.equal(context.cachedProgress('','diaries','in_progress').achievementDiaries.EXAMPLE,undefined);
});

test('Late progress failures cannot overwrite newer results with cached fallback',async()=>{
  const {context,byId} = setup();
  context.api = async () => ({quests:{ok:true,quests:[{name:'STALE',state:'FINISHED'}]},stats:{ok:true},items:{ok:true}});
  await context.refreshStatus();
  let reject;
  context.api = () => new Promise((_,fail) => { reject = fail; });
  byId('progress-search').value = 'stale'; byId('progress-category').value = 'quests'; byId('progress-status').value = 'all';
  const old = context.queueProgressSearch(true);
  context.api = async () => ({ok:true,quests:[{name:'NEW',state:'FINISHED'}],total_matches:1});
  byId('progress-search').value = 'new';
  await context.queueProgressSearch(true);
  reject(new Error('Old request failed'));
  await old;
  assert.match(byId('progress-results').textContent,/NEW/);
  assert.doesNotMatch(byId('progress-results').textContent,/STALE|Respaldo/);
});

test('Equipment uses decorative span sprites and keeps exported slot and name text',()=>{
  const {context,byId} = setup();
  context.renderGear({ok:true},{ok:true,equipment:{HEAD:{name:'Example helmet'},WEAPON:{name:'<img src=x>'}}},{ok:true});
  const icons = descendants(byId('equipment'),'SPAN').filter(el => el.className.startsWith('game-icon'));
  assert.equal(icons.length,2);
  assert.equal(icons[0].attributes['aria-hidden'],'true');
  assert.match(icons[0].className,/icon-head/);
  assert.match(icons[1].className,/icon-attack/);
  assert.match(byId('equipment').textContent,/HEADExample helmet/);
  assert.equal(descendants(byId('equipment'),'IMG').length,0);
});

test('RuneScribe uses functional copy and keeps removed promotional slogans out of HTML and JS',()=>{
  const html = fs.readFileSync(path.join(__dirname,'..','ui','index.html'),'utf8');
  const js = fs.readFileSync(path.join(__dirname,'..','ui','app.js'),'utf8');
  for (const slogan of ['TU AVENTURA. TU COMPAÑERO.','OLD SCHOOL, NUEVAS POSIBILIDADES',
    'ADVENTURE ASSISTANT','Tu compañero de aventuras','TU PRÓXIMA MISIÓN EMPIEZA AQUÍ',
    'Un compañero. Mil aventuras.','LOCAL COMPANION']) {
    assert.ok(!html.includes(slogan),slogan);
    assert.ok(!js.includes(slogan),slogan);
  }
  assert.match(html,/<title>RuneScribe · OSRS HUD &amp; Wiki<\/title>/);
  assert.match(html,/<h1>Rune<span>Scribe<\/span><\/h1>/);
  assert.match(html,/Consultas &amp; Oráculo/);
  assert.match(html,/Notas y objetivos/);
  assert.match(html,/data-question="¿Tengo cultivos listos para recoger\?"/);
  const {context,byId} = setup();
  context.bubble('Example answer','assistant');
  assert.equal(byId('conversation').children[0].children[0].textContent,'RuneScribe');
  const waiting = byId('thinking');
  context.updateThinking({busy:true,active_tools:[]});
  assert.equal(waiting.textContent,'Preparando respuesta…');
});

test('Countdown formats seconds, minutes and hours and turns expired patches ready each second',()=>{
  const {context,byId} = setup();
  let now = Date.parse('2030-01-01T00:00:00Z');
  context.Date = class extends Date { static now() { return now; } };
  const stamp = seconds => new Date(now + seconds * 1000).toISOString();
  assert.equal(context.countdown(stamp(30),'GROWING'),'Listo en 30 s');
  assert.equal(context.countdown(stamp(61),'GROWING'),'Listo en 1 min 1 s');
  assert.equal(context.countdown(stamp(3660),'GROWING'),'Listo en 1 h 1 min');
  assert.equal(context.countdown(stamp(100),'READY'),'Listo para recoger');
  assert.equal(context.countdown('bad-date','GROWING'),'');
  assert.equal(context.countdown(stamp(-1),'DEAD'),'');
  const row = context.activity('<img src=x>','Example patch','GROWING',stamp(1),2,5);
  assert.match(row.textContent,/Etapa 2\/5/);
  assert.match(row.className,/growing/);
  const badge = row.children.at(-1);
  context.document.querySelectorAll = selector => selector === '[data-ready-at]' ? [badge] : [];
  now += 1500;
  context.refreshAges();
  assert.equal(badge.textContent,'Listo para recoger');
  assert.equal(row.className,'activity ready');
  assert.equal(descendants(row,'IMG').length,0);
  const dead = context.activity('Dead patch','Example','DEAD',stamp(-10),1,5);
  assert.equal(dead.className,'activity dead');
  assert.equal(dead.children.length,2);
  assert.equal(context.activity('Patch','Example','GROWING','invalid').children.length,2);
});

test('Dailies show only unlocked entries, safe names, counts and claimed state',()=>{
  const {context,byId} = setup();
  context.renderDailies({herbBoxes:{unlocked:true,claimed:false,claimedCount:0,max:15},
    sand:{unlocked:true,claimed:true,claimedCount:84,max:84},locked:{unlocked:false,claimed:false},
    '<script>fake()</script>':{unlocked:true,claimed:false},unstructured:1});
  const rows = byId('dailies').children;
  assert.equal(rows.length,3);
  assert.match(rows[0].textContent,/Cajas de hierbasPendiente hoy · 0 \/ 15/);
  assert.match(rows[0].className,/ready/);
  assert.match(rows[1].textContent,/ArenaReclamado · 84 \/ 84/);
  assert.match(rows[1].className,/growing/);
  assert.equal(descendants(byId('dailies'),'SCRIPT').length,0);
  context.renderDailies(null);
  assert.equal(byId('dailies').textContent,'No hay dailies desbloqueadas registradas.');
});

test('Manual notes POST directly, keep filter, clear saved input and retain drafts on failure',async()=>{
  const {context,byId} = setup();
  byId('memory-topic').value = 'Meta'; byId('memory-text').value = '<img src=x>Quest Cape';
  byId('memory-search').value = 'quest & cape';
  const calls = [];
  context.api = async (path,body) => { calls.push([path,body]); return body ? {saved:true,id:1} : {memories:[]}; };
  await context.createMemory('Meta','<img src=x>Quest Cape');
  assert.equal(calls[0][0],'/api/memories');
  assert.equal(calls[0][1].contenido,'<img src=x>Quest Cape');
  assert.equal(calls[1][0],'/api/memories?q=quest%20%26%20cape');
  assert.equal(byId('memory-topic').value,'');
  assert.equal(byId('memory-text').value,'');
  assert.equal(byId('memory-feedback').textContent,'Nota guardada.');
  assert.equal(byId('memory-save').disabled,false);
  byId('memory-topic').value = 'Draft'; byId('memory-text').value = 'Keep this';
  context.api = async () => { throw new Error('Busy'); };
  await context.createMemory('Draft','Keep this');
  assert.equal(byId('memory-text').value,'Keep this');
  assert.equal(byId('memory-save').disabled,false);
  assert.equal(byId('error').textContent,'Busy');
});

test('Memory search debounces, invalidates in-flight results immediately and renders text safely',async()=>{
  const {context,byId,timers} = setup();
  const pending = [], calls = [];
  context.api = path => { calls.push(path); return new Promise(resolve => pending.push(resolve)); };
  byId('memory-search').value = 'old';
  const old = context.refreshMemories();
  byId('memory-search').value = 'new & query';
  context.queueMemorySearch();
  assert.equal([...timers.values()][0].delay,180);
  pending[0]({memories:[{id:1,tema:'STALE',contenido:'stale'}]});
  await old;
  assert.doesNotMatch(byId('memories').textContent,/STALE/);
  const latest = [...timers.values()][0].fn();
  assert.equal(calls[1],'/api/memories?q=new%20%26%20query');
  pending[1]({memories:[{id:2,tema:'<img src=x>',contenido:'<script>fake()</script>'}]});
  await latest;
  assert.equal(descendants(byId('memories'),'IMG').length,0);
  assert.equal(descendants(byId('memories'),'SCRIPT').length,0);
  assert.match(byId('memories').textContent,/fake/);
});

test('Direct GE results show prices, limits, missing fields and safe item names',()=>{
  const {context,byId} = setup();
  context.renderOracleResults('ge',{matches:[{name:'<img src=x>',high:1200,low:1000,limit:70,highalch:800},{name:'No price',high:null,low:null}]});
  const text = byId('oracle-results').textContent;
  assert.match(text,/Compra inst\.: 1\.200 GP · Venta inst\.: 1\.000 GP/);
  assert.match(text,/Límite 4h: 70 · High Alch: 800 GP/);
  assert.match(text,/Compra inst\.: — GP/);
  assert.equal(descendants(byId('oracle-results'),'IMG').length,0);
  context.renderOracleResults('ge',{matches:[]});
  assert.equal(byId('oracle-results').textContent,'Sin coincidencias en Grand Exchange.');
});

test('Direct Wiki renders extracts as text and links only to the exact HTTPS Wiki prefix',()=>{
  const {context,byId} = setup();
  context.renderOracleResults('wiki',{extract:'<script>fake()</script>',truncated:true,results:[
    {title:'<img src=x>',url:'https://oldschool.runescape.wiki/w/Example'},
    {title:'bad',url:'javascript:fake()'},{title:'bad',url:'https://oldschool.runescape.wiki.evil.example/'},
    {title:'bad',url:'https://oldschool.runescape.wiki@evil.example/'},{title:'bad',url:'//oldschool.runescape.wiki/w/Example'}]});
  const links = descendants(byId('oracle-results'),'A');
  assert.equal(links.length,1);
  assert.equal(links[0].target,'_blank');
  assert.equal(links[0].rel,'noopener noreferrer');
  assert.equal(descendants(byId('oracle-results'),'IMG').length,0);
  assert.equal(descendants(byId('oracle-results'),'SCRIPT').length,0);
  assert.match(byId('oracle-results').textContent,/Extracto abreviado/);
  context.renderOracleResults('wiki',{results:[]});
  assert.equal(byId('oracle-results').textContent,'Sin resultados en OSRS Wiki.');
});

test('Oracle sends encoded direct queries, skips empty text and prevents late responses overwriting new filters',async()=>{
  const {context,byId} = setup();
  const pending = [], calls = [];
  context.api = path => { calls.push(path); return new Promise(resolve => pending.push(resolve)); };
  byId('oracle-search').value = ''; byId('oracle-mode').value = 'ge';
  await context.runOracleQuery();
  assert.equal(calls.length,0);
  byId('oracle-search').value = 'Example & item';
  const old = context.runOracleQuery();
  assert.equal(calls[0],'/api/ge?q=Example%20%26%20item');
  context.resetOracleQuery();
  byId('oracle-mode').value = 'wiki'; byId('oracle-search').value = 'Example boss';
  const latest = context.runOracleQuery();
  assert.equal(calls[1],'/api/wiki?q=Example%20boss');
  pending[1]({results:[{title:'NEW',url:'https://oldschool.runescape.wiki/w/Example'}]});
  await latest;
  pending[0]({matches:[{name:'STALE'}]});
  await old;
  assert.match(byId('oracle-results').textContent,/NEW/);
  assert.doesNotMatch(byId('oracle-results').textContent,/STALE/);
  assert.equal(byId('oracle-submit').disabled,false);
  context.api = async () => { throw new Error('Wiki unavailable'); };
  await context.runOracleQuery();
  assert.equal(byId('oracle-results').textContent,'Wiki unavailable');
  assert.equal(byId('oracle-submit').disabled,false);
});
