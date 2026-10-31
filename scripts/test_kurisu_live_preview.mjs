import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync,mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {liveConfiguration,partialConfiguration,previewSignature} from './kurisu_live_preview.mjs';
const require=createRequire(import.meta.url);
const {applyAnimations,menuLabels}=require('../dsh-pet/runtime/electron-helper/live-preview.js');

function withdrawnIdleFixture(t) {
 const packRoot=mkdtempSync(join(tmpdir(),'kurisu-explicit-default-'));t.after(()=>rmSync(packRoot,{recursive:true,force:true}));
 mkdirSync(join(packRoot,'pet/kurisu-animation'),{recursive:true});
 const accepted=(id,name,bytes)=>{
  const file='pet/kurisu-animation/'+name+'.webm';writeFileSync(join(packRoot,file),bytes);
  return {id,name,file,status:'approved',sha256:createHash('sha256').update(bytes).digest('hex')};
 };
 const first=accepted('a008','测试动作甲','synthetic-approved-media-A');
 const chosen=accepted('a006','测试动作乙','synthetic-approved-media-B');
 const library={actions:[{id:'a001',name:'原待机',status:'quality_withdrawn'},{id:'a003',name:'原拖拽',status:'quality_withdrawn'},first,chosen]};
 const full={pets:[{id:'formal-original',name:'正式名称',size:462,display:'both',fixedEnabled:true,position:{corner:'bottom-right',marginX:40,marginY:40}}],
  animations:{idle:['原待机'],drag:['原拖拽'],turn:[],clicks:[first.name,chosen.name],moves:{default:{leadSec:2,tailSec:2},actions:[]},
   categories:[{id:'测试分类',weight:40,actions:[first.name,chosen.name]}],events:{balance:['已撤回余额'],workStatus:['已撤回工作'],whisper:['已撤回碎碎念']}},
  animationWeights:{idle:100,turn:0,move:0}};
 return {packRoot,library,full,first,chosen};
}

function staticFixture(t) {
 const f=withdrawnIdleFixture(t);
 mkdirSync(join(f.packRoot,'references'));mkdirSync(join(f.packRoot,'previews/static-preview'),{recursive:true});
 const reference='synthetic-original-approved-RGBA',media='synthetic-independently-verified-static-WebM';
 writeFileSync(join(f.packRoot,'references/kurisu-front.png'),reference);
 writeFileSync(join(f.packRoot,'previews/static-preview/placeholder.webm'),media);
 const sourceSha=createHash('sha256').update(reference).digest('hex');
 f.library.canonical_reference_sha256=sourceSha;
 f.library.preview_static_placeholder={approved:true,file:'previews/static-preview/placeholder.webm',
  sha256:createHash('sha256').update(media).digest('hex'),source_reference_sha256:sourceSha,label:'静态定稿占位 · 不计106条动画'};
 return f;
}

test('only approved clips enter the live config, with immutable versions and user preferences preserved',()=>{
 const full=JSON.parse(readFileSync(new URL('../pet-packs/kurisu/kurisu-config.full.json',import.meta.url)));
 const library=JSON.parse(readFileSync(new URL('../pet-packs/kurisu/library.json',import.meta.url)));
 const previous={pets:[{id:'my-preview',name:'助手',size:360,display:'desktop',position:{corner:'bottom-left',marginX:70,marginY:40}}]};
 const result=liveConfiguration(full,library,previous);
 assert.equal(result.config.pets[0].id,'my-preview');assert.equal(result.config.pets[0].size,360);
 for(const a of result.available)assert.equal(a.status,'approved');
 const tree=menuLabels([{label:'动作',children:[{label:'待机呼吸__v_aaaaaaaaaaaa',anim:'待机呼吸__v_aaaaaaaaaaaa'}]}]);
 assert.equal(tree[0].children[0].label,'待机呼吸');assert.match(tree[0].children[0].anim,/__v_/);
 assert.equal(result.config.pets[0].whisperEnabled,false);
});

test('hot update keeps the actual position, facing and motion, and retires an old looping asset at its end',()=>{
 const animations={idle:['new'],turn:[],drag:[],clicks:[],moves:{actions:[]},categories:[],events:{balance:['new']}};
 const position={x:510,y:630},move={active:true};let ended=0;
 const sprite={pet:{id:'p'},pos:position,customPos:{rx:.4,ry:.7},facing:'right',moveRef:move,front:0,anim:'old',videoA:{loop:true},handleEnded(){ended++}};
 const pet={id:'p',animations,animationWeights:{idle:100,turn:0,move:0}};
 assert.equal(applyAnimations(sprite,pet),true);
 assert.equal(sprite.pos,position);assert.equal(sprite.moveRef,move);assert.equal(sprite.facing,'right');
 assert.deepEqual(sprite.customPos,{rx:.4,ry:.7});assert.equal(sprite.videoA.loop,false);
 sprite.videoA.onended();assert.equal(ended,1);
 sprite.videoA.loop=true;assert.equal(applyAnimations(sprite,pet),false);assert.equal(sprite.videoA.loop,false);
});

test('withdrawing the last balance clip removes it immediately without invalidating the live config',()=>{
 const full=JSON.parse(readFileSync(new URL('../pet-packs/kurisu/kurisu-config.full.json',import.meta.url)));
 const library=JSON.parse(readFileSync(new URL('../pet-packs/kurisu/library.json',import.meta.url)));
 for(const a of library.actions)if(a.group==='余额')a.status='quality_withdrawn';
 const result=liveConfiguration(full,library,{pets:[{balanceEnabled:true}]});
 assert.deepEqual(result.config.animations.events.balance,[result.config.animations.idle[0]]);
 assert.equal(result.config.pets[0].balanceEnabled,false);
 assert.ok(result.available.every(a=>a.group!=='余额'));
 assert.ok(!JSON.stringify(result.config).includes('预算充足'));
});

test('no approved idle never silently selects the first remaining approved action',t=>{
 const f=withdrawnIdleFixture(t);
 assert.throws(()=>liveConfiguration(f.full,f.library,{},f),/explicit preview_idle_override/);
 assert.throws(()=>partialConfiguration(f.full,f.library,{},f),/explicit preview_idle_override/);
});

test('explicit approved fallback keeps its own stable identity and supplies only necessary placeholders',t=>{
 const f=withdrawnIdleFixture(t);f.library.preview_idle_override={action_id:f.chosen.id,sha256:f.chosen.sha256,reason:'Isolated test declaration'};
 const fullBefore=structuredClone(f.full),libraryBefore=structuredClone(f.library);
 const previous={pets:[{id:'user-id',name:'用户名称',size:317.5,position:{corner:'top-left',marginX:124,marginY:87},facing:'right',display:'none',fixedEnabled:true,balanceEnabled:true,workStatusEnabled:true,whisperEnabled:true}]};
 const result=liveConfiguration(f.full,f.library,previous,f);const name=result.version(f.chosen.name);
 assert.deepEqual(result.config.animations.idle,[name]);assert.deepEqual(result.config.animations.drag,[name]);
 assert.deepEqual(result.config.animations.events.balance,[name]);
 assert.equal(result.temporaryDefault.action_id,f.chosen.id);assert.equal(result.temporaryDefault.name,f.chosen.name);
 assert.equal(result.temporaryDefault.counts_as_new_animation,false);assert.equal(result.available.length,2);
 assert.ok(result.available.every(a=>a.id!=='a001'));assert.ok(!JSON.stringify(result.config).includes('原待机'));
 for(const key of ['id','name','size','position','facing','display','fixedEnabled'])assert.deepEqual(result.config.pets[0][key],previous.pets[0][key]);
 for(const key of ['balanceEnabled','workStatusEnabled','whisperEnabled'])assert.equal(result.config.pets[0][key],false);
 assert.deepEqual(f.full,fullBefore);assert.deepEqual(f.library,libraryBefore);
});

test('explicit stable-ID shorthand is accepted but unknown or withdrawn IDs fail closed',t=>{
 const f=withdrawnIdleFixture(t);f.library.preview_idle_override=f.chosen.id;
 assert.equal(liveConfiguration(f.full,f.library,{},f).temporaryDefault.action_id,f.chosen.id);
 for(const value of ['a001','a999','',{},'测试动作乙']) {
  f.library.preview_idle_override=value;
  assert.throws(()=>liveConfiguration(f.full,f.library,{},f));
 }
});

test('a stale declaration SHA or changed media bytes cannot become the temporary default',t=>{
 const f=withdrawnIdleFixture(t);f.library.preview_idle_override={action_id:f.chosen.id,sha256:'0'.repeat(64)};
 assert.throws(()=>liveConfiguration(f.full,f.library,{},f),/declaration SHA/);
 f.library.preview_idle_override={action_id:f.chosen.id,sha256:f.chosen.sha256};
 writeFileSync(join(f.packRoot,f.chosen.file),'altered-after-approval');
 assert.throws(()=>liveConfiguration(f.full,f.library,{},f),/media SHA mismatch/);
});

test('override changes invalidate the monitor signature even when approved media are unchanged',t=>{
 const f=withdrawnIdleFixture(t);const initial=previewSignature(f.library);
 f.library.preview_idle_override=f.chosen.id;const selected=previewSignature(f.library);
 assert.notEqual(selected,initial);
 f.library.preview_idle_override=f.first.id;assert.notEqual(previewSignature(f.library),selected);
});

test('partial configuration uses original media names and preserves multiple instances without changing the full draft',t=>{
 const f=withdrawnIdleFixture(t);f.library.preview_idle_override={action_id:f.chosen.id,sha256:f.chosen.sha256};
 const previous={pets:[{id:'p1',name:'甲',size:315,display:'none',position:{corner:'top-left',marginX:12,marginY:21},fixedEnabled:true,facing:'left'},
  {id:'p2',name:'乙',size:260,display:'desktop',position:{corner:'bottom-left',marginX:35,marginY:66},fixedEnabled:false,facing:'right'}]};
 const result=partialConfiguration(f.full,f.library,previous,f);
 assert.deepEqual(result.config.animations.idle,[f.chosen.name]);assert.deepEqual(result.config.animations.drag,[f.chosen.name]);
 assert.ok(!JSON.stringify(result.config).includes('__v_'));
 for(let i=0;i<2;i++)for(const key of ['id','name','size','display','position','fixedEnabled','facing'])assert.deepEqual(result.config.pets[i][key],previous.pets[i][key]);
 assert.equal(result.available.length,2);assert.equal(result.temporaryDefault.action_id,'a006');
});

test('hot replacement of a withdrawn idle preserves actual sprite position/facing and retires its old loop',t=>{
 const f=withdrawnIdleFixture(t);f.library.preview_idle_override=f.chosen.id;
 const result=liveConfiguration(f.full,f.library,{pets:[{id:'p',name:'existing',display:'none',fixedEnabled:true}]},f);
 const pos={x:456,y:123},customPos={rx:.4,ry:.7};let ended=0;
 const sprite={pet:{id:'p'},pos,customPos,facing:'left',front:0,anim:'原待机__v_aaaaaaaaaaaa',videoA:{loop:true},handleEnded(){ended++}};
 applyAnimations(sprite,{...result.config.pets[0],animations:result.config.animations,animationWeights:result.config.animationWeights});
 assert.equal(sprite.pos,pos);assert.equal(sprite.customPos,customPos);assert.equal(sprite.facing,'left');assert.equal(sprite.pet.fixedEnabled,true);assert.equal(sprite.pet.display,'none');
 assert.equal(sprite.videoA.loop,false);sprite.videoA.onended();assert.equal(ended,1);
});

test('explicit static preview is separate from approved actions and cannot impersonate a001',t=>{
 const f=staticFixture(t);const before=structuredClone(f.library);
 const previous={pets:[{id:'existing',name:'原名称',size:311,display:'none',position:{corner:'top-left',marginX:22,marginY:37},fixedEnabled:false,facing:'right',balanceEnabled:true,workStatusEnabled:true}]};
 const result=liveConfiguration(f.full,f.library,previous,f);
 assert.equal(result.available.length,2);assert.equal(result.approvedCount,2);assert.equal(result.previewOnlyAssets.length,1);
 assert.equal(result.temporaryDefault.action_id,null);assert.equal(result.temporaryDefault.static,true);
 assert.equal(result.temporaryDefault.counts_as_new_animation,false);assert.match(result.temporaryDefault.name,/静态.*不计106/);
 const placeholder=result.version(result.temporaryDefault.name);
 assert.deepEqual(result.config.animations.idle,[placeholder]);assert.deepEqual(result.config.animations.drag,[placeholder]);
 assert.deepEqual(result.config.animations.events.balance,[placeholder]);
 assert.deepEqual(result.config.animationWeights,{idle:100,turn:0,move:0});assert.ok(result.config.animations.categories.every(c=>c.weight===0));
 for(const key of ['id','name','size','position','display','fixedEnabled','facing'])assert.deepEqual(result.config.pets[0][key],previous.pets[0][key]);
 assert.equal(result.config.pets[0].balanceEnabled,false);assert.equal(result.config.pets[0].workStatusEnabled,false);
 assert.deepEqual(f.library,before);assert.ok(!JSON.stringify(result.config).includes('原待机'));
});

test('a static preview can keep an otherwise empty live preview safe without inventing an approved action',t=>{
 const f=staticFixture(t);for(const a of f.library.actions)a.status='quality_withdrawn';
 const result=liveConfiguration(f.full,f.library,{},f);
 assert.equal(result.available.length,0);assert.equal(result.approvedCount,0);assert.equal(result.previewOnlyAssets.length,1);
 assert.equal(f.library.actions.filter(a=>a.status==='approved').length,0);
 assert.ok(result.config.animations.idle[0].startsWith('静态定稿占位_不计106'));
});

test('static preview is inactive whenever a real approved idle exists',t=>{
 const f=staticFixture(t);const idle=f.library.actions.find(a=>a.id==='a001');idle.status='approved';idle.sha256='f'.repeat(64);
 f.library.preview_static_placeholder={approved:false,file:'missing.webm'};
 const result=liveConfiguration(f.full,f.library,{},f);
 assert.equal(result.previewOnlyAssets.length,0);assert.equal(result.temporaryDefault,null);
 assert.ok(result.config.animations.idle[0].startsWith('原待机__v_'));
});

test('static preview requires explicit permission, an honest label, a pinned source and matching media SHA',t=>{
 const f=staticFixture(t),valid=structuredClone(f.library.preview_static_placeholder);
 for(const mutation of [{approved:false},{label:'正常待机'},{source_reference_sha256:'0'.repeat(64)},{sha256:'0'.repeat(64)},
  {file:f.chosen.file}]) {
  f.library.preview_static_placeholder={...valid,...mutation};
  assert.throws(()=>liveConfiguration(f.full,f.library,{},f));
 }
 f.library.preview_static_placeholder=valid;f.library.canonical_reference_sha256='0'.repeat(64);
 assert.throws(()=>liveConfiguration(f.full,f.library,{},f),/approved original front reference SHA/);
});

test('static previews cannot enter partial delivery configuration or ambiguously override another declaration',t=>{
 const f=staticFixture(t);
 assert.throws(()=>partialConfiguration(f.full,f.library,{},f),/preview-only/);
 f.library.preview_idle_override=f.chosen.id;
 assert.throws(()=>liveConfiguration(f.full,f.library,{},f),/only one temporary default/);
});

test('static declaration participates in hot-update signatures and replaces an old loop without resetting facing',t=>{
 const f=staticFixture(t);const declared=previewSignature(f.library);f.library.preview_static_placeholder.label+=' · 已核验';
 assert.notEqual(previewSignature(f.library),declared);
 const result=liveConfiguration(f.full,f.library,{pets:[{id:'p',name:'same',fixedEnabled:true,display:'none'}]},f);
 const pos={x:400,y:800},customPos={rx:.3,ry:.8};let ended=0;
 const sprite={pet:{id:'p'},pos,customPos,facing:'right',front:0,anim:'原待机__v_aaaaaaaaaaaa',videoA:{loop:true},handleEnded(){ended++}};
 applyAnimations(sprite,{...result.config.pets[0],animations:result.config.animations,animationWeights:result.config.animationWeights});
 assert.equal(sprite.pos,pos);assert.equal(sprite.customPos,customPos);assert.equal(sprite.facing,'right');assert.equal(sprite.videoA.loop,false);
 assert.equal(sprite.pet.fixedEnabled,true);assert.equal(sprite.pet.display,'none');sprite.videoA.onended();assert.equal(ended,1);
});
