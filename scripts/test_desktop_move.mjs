import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function fixture({cx=110,width=1000}={}) {
 const scheduled=[];
 const ctx=vm.createContext({navigator:{platform:'test'},window:{},
  VIEW:{w:width,h:800},AREAS:[{x:0,y:0,width,height:800}],
  requestAnimationFrame:fn=>{scheduled.push(fn);return scheduled.length},cancelAnimationFrame:()=>{}});
 vm.runInContext(readFileSync(new URL('../dsh-pet/runtime/electron-helper/shared-core.js',import.meta.url),'utf8'),ctx);
 ctx.S=ctx.PetShared;
 vm.runInContext(readFileSync(new URL('../dsh-pet/runtime/electron-helper/sprite.js',import.meta.url),'utf8')+'\nglobalThis.SpriteClass=PetSprite;',ctx);
 const s=Object.create(ctx.SpriteClass.prototype);
 Object.assign(s,{moveRef:null,pendingMove:null,throwRef:null,size:462,halfW:100,halfH:130,
  sideAllow:40,confineToScreen:false,customPos:{rx:cx/width,ry:.5},moveToken:0,_facing:'left',anim:'idle',
  animations:{idle:['idle'],categories:[],moves:{default:{minDist:120,maxDist:120,margin:20,leadSec:2,tailSec:2},actions:[{name:'run'}]}}});
 s.markPoseDirty=()=>{};s.closeMenu=()=>{};s.switchTo=(name,once,id)=>{s.switched={name,once,id}};
 s.playOnce=name=>{s.fallback=name};s.reportPlayback=(id,status,reason)=>{s.receipt={id,status,reason}};
 s.sendBounds=(x,y)=>{s.bounds={x,y}};
 return {s,scheduled};
}

test('desktop menu runs away from edge and drives matching horizontal window movement',()=>{
 const {s,scheduled}=fixture();
 s.onMenuAction({anim:'run',playbackId:'test'});
 assert.equal(s.facing,'right');assert.equal(s.switched.name,'run');
 const el={duration:10,currentTime:0};s.startMoveDrive(el);
 scheduled.shift()();const start=s.bounds;
 el.currentTime=5;scheduled.shift()();const mid=s.bounds;
 el.currentTime=8;scheduled.shift()();const end=s.bounds;
 assert.equal(start.y,mid.y);assert.equal(mid.y,end.y);
 assert.ok(mid.x>start.x);assert.ok(end.x>mid.x);
 assert.equal(end.x-start.x,120);assert.equal(s.moveRef,null);
});

test('explicit blocked facing reports failure and stays idle rather than falsely running in place',()=>{
 const {s}=fixture();s.onMenuAction({anim:'run',playbackId:'test'},true);
 assert.equal(s.facing,'left');assert.equal(s.switched,undefined);assert.equal(s.fallback,'idle');
 assert.deepEqual(s.receipt,{id:'test',status:'failed',reason:'move-blocked'});
});

test('busy desktop movement does not switch clip or emit a false successful playback',()=>{
 const {s}=fixture();s.moveRef=123;s.onMenuAction({anim:'run',playbackId:'test'});
 assert.equal(s.switched,undefined);assert.equal(s.fallback,undefined);
 assert.deepEqual(s.receipt,{id:'test',status:'failed',reason:'busy'});
});
