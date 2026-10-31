import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../pet-packs/kurisu/preview.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];

function harness(fixture={actions:[]}) {
 class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.attributes={};this.hidden=false;this.style={};this.src='';this.href='';this.paused=true;this.loads=0;this.textContent='';}
  append(...items){this.children.push(...items)}
  replaceChildren(...items){this.children=[...items]}
  setAttribute(key,value){this.attributes[key]=String(value)}
  removeAttribute(key){delete this.attributes[key];if(key==='src')this.src='';if(key==='href')this.href='';}
  play(){this.paused=false;return Promise.resolve()}
  pause(){this.paused=true}
  load(){this.loads++}
 }
 const elements=new Map(),created=[];let next=fixture;
 const document={querySelector(key){if(!elements.has(key))elements.set(key,new Element(key==='#pet'?'video':'div'));return elements.get(key)},
  querySelectorAll(){return[]},createElement(tag){created.push(tag);return new Element(tag)}};
 const requests=[];
 const context=vm.createContext({document,ResizeObserver:class{observe(){}},setInterval(){throw new Error('Test must not start timers')},
  fetch:async(url,options)=>{requests.push({url,options});return{ok:true,json:async()=>structuredClone(next)}},structuredClone,console});
 const isolated=script.replace('refresh();setInterval(refresh,15000);','');new vm.Script(isolated);vm.runInContext(isolated,context);
 return {context,elements,created,requests,setFixture(value){next=value},run(code){return vm.runInContext(code,context)},
  setData(value){context.fixture=structuredClone(value);vm.runInContext('data=fixture',context)}};
}

const approved={id:'a103',name:'整理实验记录',group:'工作状态',status:'approved',file:'pet/kurisu-animation/record.webm',sha256:'1'.repeat(64),poster:'previews/library/a103.png',attempts:[{},{}]};

test('gallery script parses and has a single lazy-selected video with no withdrawn bootstrap source',()=>{
 new vm.Script(script);
 assert.equal((html.match(/<video\b/g)||[]).length,1);
 const tag=html.match(/<video\b[^>]*>/)[0];assert.ok(!/\ssrc=/.test(tag));
 assert.ok(html.includes('id="download" hidden download'));
});

test('static notice is read-only and never claims a completed idle or a106 slot',()=>{
 const h=harness();const data={actions:[{id:'a001',group:'待机',status:'quality_withdrawn'}],
  preview_static_placeholder:{approved:true,label:'静态定稿占位 · 不计106条动画',file:'previews/static-preview/only.webm'}};
 const before=JSON.stringify(data);h.context.fixture=data;
 const text=h.run('liveDefaultNotice(fixture)');
 assert.match(text,/静态定稿/);assert.match(text,/不计入106/);assert.match(text,/不代表.*待机已完成/);
 assert.equal(JSON.stringify(data),before);
});

test('borrowed default notice names the actual action and does not declare missing idle complete',()=>{
 const h=harness();h.context.fixture={actions:[{id:'a002',name:'左右张望',group:'转向',status:'approved'}],preview_idle_override:{action_id:'a002'}};
 const text=h.run('liveDefaultNotice(fixture)');assert.match(text,/左右张望/);assert.match(text,/不计为缺失待机/);
 h.context.fixture.actions[0].status='quality_recheck_hold';
 assert.match(h.run('liveDefaultNotice(fixture)'),/尚未通过当前复核/);
});

test('review hold has its Chinese label, stays in review filter and cannot be played',()=>{
 const h=harness();h.setData({actions:[{id:'a002',name:'左右张望',group:'转向',status:'quality_recheck_hold',attempts:[]}],standing_authorization:{approved:true}});
 h.run("statusFilter='review';renderCards()");
 const cards=h.elements.get('#gallery').children;assert.equal(cards.length,1);assert.equal(cards[0].disabled,true);
 assert.match(cards[0].attributes['aria-label'],/复核暂挂/);
 cards[0].onclick();assert.equal(h.elements.get('#pet').src,'');
});

test('standing authorization makes exhausted actions await repair instead of a permanent stop',()=>{
 const h=harness();h.context.fixture={actions:[],standing_authorization:{approved:true}};
 assert.equal(h.run("statusLabel('exhausted',fixture)"),'待返修');
 h.context.fixture.standing_authorization.revoked_at='later';
 assert.equal(h.run("statusLabel('exhausted',fixture)"),'单条次数已用尽');
});

test('repair accounting counts first replacement of reused origins without recounting legacy calls or diagnostics',()=>{
 const h=harness();h.context.fixture={actions:[{attempts:[],reused_origin_history:[{}]},
  {attempts:[{}],reused_origin_history:[{}]},{attempts:[{},{}],reused_origin_history:[{}]},
  {attempts:[{},{}],reused_origin_history:[]},{attempts:[{}]}],diagnostic_attempts:[{}]};
 assert.equal(h.run('repairCount(fixture)'),4);
});

test('approved gallery excludes static placeholder and held cards; cover images remain lazy',()=>{
 const h=harness();h.setData({actions:[approved,{id:'a002',name:'hold',group:'转向',status:'quality_recheck_hold',attempts:[]}],
  preview_static_placeholder:{approved:true,label:'静态定稿占位 · 不计106条动画',file:'previews/static-preview/only.webm'}});
 h.run('renderCards()');const cards=h.elements.get('#gallery').children;
 assert.equal(cards.length,1);assert.match(cards[0].attributes['aria-label'],/整理实验记录/);
 assert.equal(cards[0].children[0].children[0].loading,'lazy');assert.ok(!h.created.includes('video'));
});

test('refresh never loads or downloads placeholder as an approved animation and clears withdrawn playback',async()=>{
 const fixture={updated_at:'first',actions:[approved,{id:'a002',name:'hold',group:'转向',status:'quality_recheck_hold',attempts:[]}],
  limits:{total_calls:130,repair_calls:26},production_hold:{reason:'QA'},standing_authorization:{approved:true},
  preview_static_placeholder:{approved:true,label:'静态定稿占位 · 不计106条动画',file:'previews/static-preview/only.webm'}};
 const h=harness(fixture);await h.run('refresh()');
 assert.equal(h.elements.get('#live-default-notice').hidden,false);assert.match(h.elements.get('#live-default-notice').textContent,/静态/);
 assert.match(h.elements.get('#pet').src,/record\.webm/);assert.equal(h.elements.get('#download').href,approved.file);
 assert.ok(!h.elements.get('#pet').src.includes('static-preview'));assert.equal(h.elements.get('#progress').value,1);
 h.setFixture({...fixture,updated_at:'second',actions:fixture.actions.map(a=>({...a,status:'quality_recheck_hold'}))});
 await h.run('refresh()');assert.equal(h.elements.get('#pet').src,'');assert.equal(h.elements.get('#download').hidden,true);
 assert.equal(h.elements.get('#download').href,'');assert.equal(h.elements.get('#pause').disabled,true);
 assert.ok(h.requests.every(r=>r.url==='library.json'&&(!r.options.method||r.options.method==='GET')));
});

test('source coverage separates preserved historical raw from new specification work',()=>{
 const h=harness();h.context.fixture={actions:[{id:'a034',spec_revision_id:'programmer-v2',attempts:[{source_file:'old.mp4',spec_revision_id:'old'}]},{id:'a103',attempts:[{source_file:'record.mp4'}]}]};
 assert.equal(h.run('historicalSourceCoverage(fixture)'),2);assert.equal(h.run('sourceCoverage(fixture)'),1);assert.match(h.run('specRevisionNotice(fixture)'),/旧原片和调用历史保留/);h.context.fixture.actions[0].attempts.push({source_file:'new.mp4',spec_revision_id:'programmer-v2'});assert.equal(h.run('sourceCoverage(fixture)'),2);
});
