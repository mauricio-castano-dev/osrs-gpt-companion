/* Unit tests for pure rendering logic, using a synthetic DOM and no browser. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.hidden = false; this.ownText = ''; this.className = ''; this.classList = {toggle: () => {}}; }
  get textContent() { return this.ownText + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  set innerHTML(_) { throw new Error('Unsafe HTML assignment'); }
  append(...children) { for (const child of children) this.children.push(typeof child === 'string' ? Object.assign(new Element('#text'),{ownText:child}) : child); }
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
  const context = vm.createContext({document, Intl, Date, Number, console});
  vm.runInContext(source.split("$('chat-form').addEventListener")[0],context);
  return {context, byId};
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
  assert.match(waiting.textContent,/preparando/);
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
