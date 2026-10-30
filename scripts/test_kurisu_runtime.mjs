import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,copyFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {readAllConfig} from '../dsh-pet/src/host/config.ts';
import {flattenConfigPets} from '../dsh-pet/src/shared/config.ts';
import {animationNames} from '../pet-packs/kurisu/install.mjs';

test('the real config loader preserves all 106 Kurisu slots without fish fallback',()=>{
 const root=mkdtempSync(join(tmpdir(),'kurisu-full-runtime-'));
 try{
  const petDir=join(root,'pet');mkdirSync(petDir);
  copyFileSync(resolve('pet-packs/kurisu/kurisu-config.full.json'),join(petDir,'kurisu-config.json'));
  const expected=JSON.parse(readFileSync(join(petDir,'kurisu-config.json')));
  const config=readAllConfig({defaultFile:resolve('dsh-pet/assets/config.jsonc'),userFile:join(root,'main-config.jsonc'),petDir});
  const actual=flattenConfigPets(config).find(p=>p.id==='kurisu1');
  assert.ok(actual);
  assert.deepEqual(actual.animations,expected.animations);
  assert.equal(animationNames(actual).size,106);
  assert.deepEqual(actual.animations.events.workStatus,expected.animations.events.workStatus);
  assert.deepEqual(actual.animationWeights,{idle:10,turn:5,move:5});
  assert.equal(actual.fixedEnabled,false);assert.equal(actual.balanceEnabled,true);
  assert.equal(actual.workStatusEnabled,true);assert.equal(actual.whisperEnabled,false);
 }finally{rmSync(root,{recursive:true,force:true})}
});
