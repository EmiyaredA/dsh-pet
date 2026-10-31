import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const base=new URL('../pet-packs/kurisu/',import.meta.url);
const history=readFileSync(new URL('history.html',base),'utf8');
const semantic=readFileSync(new URL('quality/diagnostics/semantic-a105-trial-01/preview.html',base),'utf8');
function harness(html){
 class Element{constructor(){this.children=[];this.attributes={};this.listeners={};this.paused=true;this.currentTime=0;this.duration=10;this.videoWidth=640;this.videoHeight=360;this.src='';this.loads=0;this.textContent='';this.hidden=false;}
  append(...v){this.children.push(...v)}replaceChildren(...v){this.children=v}setAttribute(k,v){this.attributes[k]=String(v)}removeAttribute(k){delete this.attributes[k];if(k==='src')this.src=''}
  addEventListener(k,v){this.listeners[k]=v}pause(){this.paused=true}play(){this.paused=false;return Promise.resolve()}load(){this.loads++}}
 const elements=new Map(),requests=[];const document={querySelector(s){if(!elements.has(s))elements.set(s,new Element());return elements.get(s)},querySelectorAll(){return[]},createElement(){return new Element()}};
 let responders=async()=>({ok:false,json:async()=>({})});
 const context=vm.createContext({document,URL,console,setInterval(){throw Error('No timers in test')},fetch:async(url,opts)=>{requests.push({url,opts});return responders(url,opts);}});
 let script=html.match(/<script>([\s\S]*?)<\/script>/)[1];new vm.Script(script);
 script=script.replace('refresh();setInterval(refresh,15000);','').replace(/\nrefresh\(\);\s*$/,'');vm.runInContext(script,context);
 return{context,elements,requests,run:x=>vm.runInContext(x,context),respond:fn=>{responders=fn;}};
}
test('both pages parse, have one nonautoplay video, and clearly separate historical/diagnostic status',()=>{
 for(const html of [history,semantic]){assert.equal((html.match(/<video\b/g)||[]).length,1);assert(!html.match(/<video[^>]*\bautoplay\b/));assert(html.includes('preload="none"'));harness(html);}
 assert(history.includes('不代表通过'));assert(semantic.includes('尚未验收'));assert(semantic.includes('不计入 106'));
 const gallery=readFileSync(new URL('preview.html',base),'utf8');assert(gallery.includes('href="history.html"'));assert(gallery.includes('查看历史动画（含未通过版本）'));
});
test('history only accepts pack-local real media paths and preserves current hold/reason information',()=>{
 const h=harness(history);
 for(const path of ['/tmp/private.mp4','/Users/tonghao/Projects/dsh-pet/temp/bad.webm','../secret.mp4','https://evil.invalid/a.mp4','source/a.txt']){h.context.p=path;assert.equal(h.run('safePath(p)'),null);}
 h.context.fixture={actions:[{id:'a001',name:'待机',group:'待机',status:'exhausted',quality_hold:{reason:'source appendage'},attempts:[{source_file:'source/one.mp4',candidate_file:'/tmp/out.webm'}],withdrawn_approvals:[{archive_file:'source/withdrawn/one.webm',reason:'withdrawn proof'}],approval_suspensions:[{archive_file:'source/hold/one.webm',reason:'hold proof'}]}]};
 const rows=h.run('fromLibrary(fixture)');assert.equal(rows.length,3);assert.equal(rows[0].reason,'source appendage');assert.equal(rows[1].reason,'withdrawn proof');assert.equal(rows[2].reason,'hold proof');assert.equal(rows[0].current_status,'exhausted');
});
test('history existence check uses HEAD and loads no video before user choice',async()=>{
 const h=harness(history);h.respond(async url=>({ok:!url.includes('missing')}));
 h.context.fixture=[{id:'a001',version:'one',file:'source/existing.mp4'},{id:'a002',version:'two',file:'source/missing.mp4'}];
 const rows=await h.run('existing(fixture)');assert.equal(rows.length,1);assert(h.requests.every(r=>r.opts.method==='HEAD'));
 const video=h.elements.get('#history-video');assert.equal(video.src,'');assert.equal(video.loads,0);
 h.context.item={...rows[0],name:'existing',current_status:'quality_withdrawn',reason:'source defect'};h.run('choose(item)');assert.equal(video.src,'source/existing.mp4');assert.equal(video.paused,true);
});
test('semantic missing candidate remains unavailable and does not load a video',async()=>{
 const h=harness(semantic);h.respond(async(url,opts)=>({ok:opts.method==='HEAD'&&url.includes('source/library/a105/attempt-3/')}));
 await h.run('refresh()');assert.equal(h.elements.get('#raw').disabled,false);assert.equal(h.elements.get('#candidate').disabled,true);
 h.run("choose('candidate')");assert.equal(h.elements.get('#clip').src,'');assert.equal(h.elements.get('#clip').loads,0);
 assert(h.elements.get('#availability').textContent.includes('尚未准备好'));
});
test('semantic versions share one player and preserve time when explicitly switching',async()=>{
 const h=harness(semantic);h.respond(async(_url,opts)=>({ok:opts.method==='HEAD'}));await h.run('refresh()');
 h.run("choose('raw')");const video=h.elements.get('#clip');assert(video.src.includes('source/library/a105/attempt-3'));video.currentTime=4;video.paused=false;
 h.run("choose('candidate')");assert.equal(video.src,'a105-semantic-isnet-anime.webm');video.listeners.loadedmetadata();assert.equal(video.currentTime,4);assert.equal(video.paused,false);
 assert(h.elements.get('#report-status').textContent.includes('未验收'));assert.equal(h.elements.size>0,true);
});

test('semantic intersection is a distinct optional version and retains the baseline in the same one video',async()=>{
 const h=harness(semantic);h.respond(async(_url,opts)=>({ok:opts.method==='HEAD'}));await h.run('refresh()');
 assert.equal(h.elements.get('#intersection').disabled,false);h.run("choose('intersection')");
 const video=h.elements.get('#clip');assert.equal(video.src,'a105-semantic-green-intersection.webm');
 assert(h.elements.get('#current-label').textContent.includes('诊断未验收'));
 h.run("choose('candidate')");assert.equal(video.src,'a105-semantic-isnet-anime.webm');
});

test('history retains old specification names and does not count old clip as new planned action',()=>{
 const h=harness(history);h.context.fixture={actions:[{id:'a034',name:'报错拍键盘（半身）',group:'研究与玩耍',status:'planned',spec_revision_id:'programmer-v2',spec_revision_history:[{old_spec_revision_id:'old',previous_action_metadata:{name:'用移液器取样'}}],attempts:[{source_file:'source/old.mp4',source_sha256:'a'.repeat(64),spec_revision_id:'old',spec_action_name:'用移液器取样'},{source_file:'source/new.mp4',spec_revision_id:'programmer-v2',spec_action_name:'报错拍键盘（半身）'}]}]};
 const rows=h.run('fromLibrary(fixture)');assert.equal(rows[0].name,'用移液器取样');assert.equal(rows[0].current_name,'报错拍键盘（半身）');assert.equal(rows[0].superseded,true);assert.match(rows[0].version,/旧规格/);assert.match(rows[0].reason,/不计当前/);assert.equal(rows[1].superseded,false);
});
