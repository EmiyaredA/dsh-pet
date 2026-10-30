import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {liveConfiguration} from './kurisu_live_preview.mjs';
const require=createRequire(import.meta.url);
const {applyAnimations,menuLabels}=require('../dsh-pet/runtime/electron-helper/live-preview.js');

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
