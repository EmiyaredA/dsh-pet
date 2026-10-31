import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync, copyFileSync, symlinkSync } from 'node:fs';
import {execFileSync} from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {createRequire} from 'node:module';
import { installPack } from '../pet-packs/kurisu/install.mjs';
const require=createRequire(import.meta.url);
const {applyAnimations}=require('../dsh-pet/runtime/electron-helper/live-preview.js');

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'kurisu-install-'));
  const pack = join(root, 'pack'); mkdirSync(join(pack, 'pet/kurisu-animation'), { recursive: true });
  const config = { pets: [{ id: 'kurisu1', name: '红莉栖', size: 462, display: 'both', position: { corner: 'bottom-right' }, fixedEnabled: false, balanceEnabled: true, workStatusEnabled: true, whisperEnabled: false }], animations: { idle: ['idle'], turn: [], drag: [], clicks: [], moves: { actions: [] }, categories: [], events: { balance: ['balance'] } } };
  writeFileSync(join(pack, 'pet/kurisu-config.json'), JSON.stringify(config));
  for (const name of ['idle', 'balance']) writeFileSync(join(pack, 'pet/kurisu-animation', name + '.webm'), name);
  return { root, pack, home: join(root, 'home'), config };
}

test('CLI entry runs when the extraction directory is reached through a symlink',()=>{
 const f=fixture();
 try{
  copyFileSync(new URL('../pet-packs/kurisu/install.mjs',import.meta.url),join(f.pack,'install.mjs'));
  const alias=join(f.root,'pack-alias');symlinkSync(f.pack,alias,'dir');
  execFileSync(process.execPath,[join(alias,'install.mjs'),'--dsh-home',f.home]);
  assert.ok(existsSync(join(f.home,'dsh-pet/pet/kurisu-config.json')));
 }finally{rmSync(f.root,{recursive:true,force:true})}
});

test('update backs up old files and preserves instance preferences while enabling new behavior', () => {
  const f = fixture();
  try {
    const first = installPack({ packRoot: f.pack, dshHome: f.home });
    const file = join(first.destination, 'kurisu-config.json');
    const old = JSON.parse(readFileSync(file)); old.pets[0] = { ...old.pets[0], id: 'my-kurisu', name: '助手', size: 310, display: 'desktop', fixedEnabled: true, balanceEnabled: false };
    writeFileSync(file, JSON.stringify(old));
    const main = join(f.home, 'dsh-pet/main-config.jsonc'); writeFileSync(main, 'unchanged');
    const result = installPack({ packRoot: f.pack, dshHome: f.home, update: true });
    const current = JSON.parse(readFileSync(file));
    assert.equal(current.pets[0].id, 'my-kurisu'); assert.equal(current.pets[0].size, 310);
    assert.equal(current.pets[0].display, 'desktop'); assert.equal(current.pets[0].balanceEnabled, true);
    assert.equal(current.pets[0].fixedEnabled, false); assert.equal(current.pets[0].whisperEnabled, false);
    assert.equal(JSON.parse(readFileSync(join(result.backup, 'kurisu-config.json'))).pets[0].size, 310);
    assert.equal(readFileSync(main, 'utf8'), 'unchanged');
    assert.throws(() => installPack({ packRoot: f.pack, dshHome: f.home }), /--update/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test('missing event material is rejected before touching an existing installation', () => {
  const f = fixture();
  try {
    installPack({ packRoot: f.pack, dshHome: f.home });
    rmSync(join(f.pack, 'pet/kurisu-animation/balance.webm'));
    assert.throws(() => installPack({ packRoot: f.pack, dshHome: f.home, update: true }), /balance/);
    assert.ok(existsSync(join(f.home, 'dsh-pet/pet/kurisu-animation/idle.webm')));
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test('update retains multiple instances, display preferences and hot-update facing without restarting a sprite',()=>{
 const f=fixture();
 try{
  const first=installPack({packRoot:f.pack,dshHome:f.home});const file=join(first.destination,'kurisu-config.json');
  const old=JSON.parse(readFileSync(file));
  old.pets=[
   {...old.pets[0],id:'my-kurisu-a',name:'实验助手 A',size:315.5,display:'desktop',position:{corner:'top-left',marginX:127,marginY:63},facing:'right'},
   {...old.pets[0],id:'my-kurisu-b',name:'实验助手 B',size:280,display:'none',position:{corner:'bottom-left',marginX:-36,marginY:82},facing:'left'},
  ];
  old.font={family:'comic',size:22,followPet:false};old.confineToScreen=true;writeFileSync(file,JSON.stringify(old));
  const main=join(f.home,'dsh-pet/main-config.jsonc');const mainBytes='// Preserve unrelated fish and global settings\n{"custom":"unchanged"}\n';writeFileSync(main,mainBytes);
  const next=structuredClone(f.config);next.animations.idle=['idle-v2'];writeFileSync(join(f.pack,'pet/kurisu-config.json'),JSON.stringify(next));writeFileSync(join(f.pack,'pet/kurisu-animation/idle-v2.webm'),'new-media');
  const result=installPack({packRoot:f.pack,dshHome:f.home,update:true});const current=JSON.parse(readFileSync(file));
  for(let i=0;i<2;i++)for(const key of ['id','name','size','display','position','facing'])assert.deepEqual(current.pets[i][key],old.pets[i][key]);
  assert.deepEqual(current.font,old.font);assert.equal(current.confineToScreen,true);assert.deepEqual(current.animations.idle,['idle-v2']);
  assert.deepEqual(JSON.parse(readFileSync(join(result.backup,'kurisu-config.json'))),old);
  assert.equal(readFileSync(join(result.backup,'kurisu-animation/idle.webm'),'utf8'),'idle');assert.equal(readFileSync(main,'utf8'),mainBytes);
  const pos={x:435,y:221};const customPos={rx:.61,ry:.42};const sprite={pet:old.pets[0],pos,customPos,facing:'right',front:0,anim:'idle',videoA:{loop:true},handleEnded(){}};
  applyAnimations(sprite,{...current.pets[0],animations:current.animations,animationWeights:{idle:100,turn:0,move:0}});
  assert.equal(sprite.facing,'right');assert.equal(sprite.pos,pos);assert.equal(sprite.customPos,customPos);assert.deepEqual(sprite.animations.idle,['idle-v2']);assert.equal(sprite.videoA.loop,false);
 }finally{rmSync(f.root,{recursive:true,force:true})}
});
