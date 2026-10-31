#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync,readFileSync,writeFileSync,mkdirSync,renameSync,chmodSync,realpathSync} from 'node:fs';
import {homedir} from 'node:os';
import {resolve,dirname,join,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const PACK=join(ROOT,'pet-packs/kurisu');
const VERSION=/__v_[a-f0-9]{12}$/;
const STATIC_NAME='静态定稿占位_不计106';
export const cleanAnimationName=name=>name.replace(VERSION,'');

export function previewSignature(library) {
 return JSON.stringify({approved:library.actions.filter(a=>a.status==='approved').map(a=>[a.id,a.sha256,a.motion_mode,a.automatic_playback_hold]),
  preview_idle_override:library.preview_idle_override??null,preview_static_placeholder:library.preview_static_placeholder??null});
}

function explicitStaticPlaceholder(library,packRoot) {
 const value=library.preview_static_placeholder;
 if(!value||typeof value!=='object'||value.approved!==true)throw new Error('Static placeholder requires an explicit approved preview_static_placeholder declaration');
 if(typeof value.label!=='string'||!/(静态|static)/i.test(value.label)||!/(不计|not counted)/i.test(value.label)||!value.label.includes('106'))throw new Error('Static placeholder label must clearly state static and not counted toward106');
 if(typeof value.sha256!=='string'||!/^[a-f0-9]{64}$/.test(value.sha256))throw new Error('Static placeholder needs an exact WebM SHA');
 if(typeof value.file!=='string'||!value.file.endsWith('.webm'))throw new Error('Static placeholder must identify its preview-only WebM');
 const root=realpathSync(packRoot),allowed=resolve(root,'previews/static-preview'),candidate=resolve(root,value.file);
 if(!candidate.startsWith(allowed+sep))throw new Error('Static placeholder must remain in previews/static-preview');
 const source=realpathSync(candidate);
 if(!source.startsWith(allowed+sep))throw new Error('Static placeholder symlink escaped preview-only media');
 if(createHash('sha256').update(readFileSync(source)).digest('hex')!==value.sha256)throw new Error('Static placeholder WebM SHA mismatch');
 const reference=realpathSync(join(root,'references/kurisu-front.png'));
 if(!reference.startsWith(root+sep))throw new Error('Static source reference escaped pet pack');
 const originalSha=createHash('sha256').update(readFileSync(reference)).digest('hex');
 if(value.source_reference_sha256!==originalSha||library.canonical_reference_sha256!==originalSha)throw new Error('Static placeholder source must match the exact approved original front reference SHA');
 return {name:STATIC_NAME,file:value.file,sha256:value.sha256,label:value.label,preview_only:true,
  source_reference_sha256:originalSha,counts_as_new_animation:false};
}

function explicitIdleOverride(library,packRoot) {
 const value=library.preview_idle_override;
 if(value===undefined||value===null)return null;
 const id=typeof value==='string'?value:value?.action_id;
 if(typeof id!=='string'||!/^a\d{3}$/.test(id))throw new Error('preview_idle_override must explicitly identify a stable action ID');
 const selected=library.actions.find(a=>a.id===id);
 if(!selected||selected.status!=='approved')throw new Error('Temporary default is not an approved action: '+id);
 if(typeof selected.sha256!=='string'||!/^[a-f0-9]{64}$/.test(selected.sha256))throw new Error('Temporary default has no verified media SHA: '+id);
 if(typeof value==='object'&&value.sha256!==selected.sha256)throw new Error('Temporary default declaration SHA does not match the approved action: '+id);
 if(typeof selected.file!=='string'||!selected.file)throw new Error('Temporary default has no recorded media file: '+id);
 const root=realpathSync(packRoot),source=realpathSync(resolve(root,selected.file));
 if(!source.startsWith(root+sep))throw new Error('Temporary default escaped the pet pack');
 if(createHash('sha256').update(readFileSync(source)).digest('hex')!==selected.sha256)throw new Error('Temporary default media SHA mismatch: '+id);
 return selected;
}

function filteredConfiguration(full,library,previous,{packRoot=PACK,live=true}={}) {
 const available=new Map(library.actions.filter(a=>a.status==='approved').map(a=>[a.name,a]));
 let selected=null,placeholder=null;
 const version=name=>{const a=available.get(name)||(placeholder?.name===name?placeholder:null);return a?(live?`${name}__v_${a.sha256.slice(0,12)}`:name):null};
 const pool=items=>items.filter(n=>available.has(n)).map(version);
 const conf=structuredClone(full),a=conf.animations;
 for(const key of ['idle','turn','drag','clicks'])a[key]=pool(a[key]);
 const temporary=!a.idle.length;
 if(!a.idle.length) {
  if(library.preview_idle_override!=null&&library.preview_static_placeholder!=null)throw new Error('Declare only one temporary default: approved action or static preview');
  if(library.preview_idle_override!=null)selected=explicitIdleOverride(library,packRoot);
  else if(library.preview_static_placeholder!=null) {
   if(!live)throw new Error('Static placeholder is preview-only and cannot populate a partial delivery');
   placeholder=explicitStaticPlaceholder(library,packRoot);
   if(available.has(STATIC_NAME))throw new Error('Static preview name collides with a recorded animation');
  }
  if(!selected&&!placeholder)throw new Error('No approved idle; an explicit preview_idle_override or preview_static_placeholder is required for a temporary default');
  const replacement=selected??placeholder;
  a.idle=[version(replacement.name)];
  if(!a.drag.length)a.drag=[version(replacement.name)];
 }
 a.moves.actions=a.moves.actions.filter(m=>available.has(m.name)).map(m=>{
  const action=available.get(m.name),next={...m,name:version(m.name)};
  if(action.motion_mode==='continuous-left-profile')next.params={...next.params,leadSec:0,tailSec:0};
  return next;
 });
 a.categories=a.categories.map(c=>({...c,actions:pool(c.actions)})).filter(c=>c.actions.length);
 a.events=Object.fromEntries(Object.entries(a.events).map(([key,slots])=>[key,slots.map(slot=>Array.isArray(slot)?pool(slot):version(slot)).filter(slot=>Array.isArray(slot)?slot.length:slot)]).filter(([,slots])=>slots.length));
 // The host requires a nonempty balance pool even when balance is disabled.
 // Use an approved idle only as that disabled placeholder; never retain a withdrawn clip.
 const hasBalance=!!a.events.balance?.length;
 if(!hasBalance)a.events.balance=[a.idle[0]];
 const hasAutomaticMove=a.moves.actions.some(m=>{
  const original=cleanAnimationName(m.name);return !available.get(original)?.automatic_playback_hold;
 });
 const turn=a.turn.length?10:0,move=hasAutomaticMove?10:0;
 const categoryWeight=a.categories.length?40:0;
 conf.animationWeights={idle:100-turn-move-categoryWeight,turn,move};
 const oldTotal=a.categories.reduce((sum,c)=>sum+c.weight,0);
 a.categories=a.categories.map(c=>({...c,weight:categoryWeight*c.weight/oldTotal}));
 if(placeholder) {
  conf.animationWeights={idle:100,turn:0,move:0};
  a.categories=a.categories.map(c=>({...c,weight:0}));
 }
 conf.pets=live?[{id:'kurisu-live',name:'红莉栖 · 实时体验',size:462,display:'desktop',position:{corner:'bottom-right',marginX:180,marginY:55},fixedEnabled:false,balanceEnabled:false,workStatusEnabled:false,whisperEnabled:false,...previous.pets?.[0]}]
  :structuredClone(previous.pets?.length?previous.pets:full.pets);
 for(const pet of conf.pets) {
  pet.whisperEnabled=false;
  if(!hasBalance||temporary||!live)pet.balanceEnabled=false;
  if(temporary||!live)pet.workStatusEnabled=false;
 }
 const replacement=selected??placeholder;
 return {config:conf,available:[...available.values()],approvedCount:available.size,previewOnlyAssets:placeholder?[placeholder]:[],version,temporaryDefault:temporary?{
  action_id:selected?.id??null,name:replacement.name,sha256:replacement.sha256,counts_as_new_animation:false,
  ...(placeholder?{preview_only:true,static:true,label:placeholder.label}:{}),
  contractPlaceholders:['idle',...(!full.animations.drag.some(n=>available.has(n))?['drag']:[]),...(!hasBalance?['events.balance (disabled)']:[])],
 }:null};
}

export function liveConfiguration(full,library,previous={},options={}) {
 return filteredConfiguration(full,library,previous,{...options,live:true});
}

export function partialConfiguration(full,library,previous={},options={}) {
 return filteredConfiguration(full,library,previous,{...options,live:false});
}

function atomicWrite(path,text) {const temp=path+'.next';writeFileSync(temp,text);renameSync(temp,path)}
function shellQuote(text) {return "'"+text.replaceAll("'","'\"'\"'")+"'"}

async function main() {
 const args=process.argv.slice(2);let home=join(ROOT,'temp/kurisu/live-runtime'),port=8770,attach=false;
 let electron=process.env.DSH_PET_ELECTRON_PATH||join(homedir(),'.dsh/electron/Electron.app/Contents/MacOS/Electron');
 for(let i=0;i<args.length;i++) {
  if(args[i]==='--home')home=resolve(args[++i]);
  else if(args[i]==='--port')port=Number(args[++i]);
  else if(args[i]==='--electron')electron=resolve(args[++i]);
  else if(args[i]==='--attach')attach=true;
  else throw new Error('Unknown option '+args[i]);
 }
 if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid port');
 if(!attach&&!existsSync(electron))throw new Error('Provide the installed Electron executable with --electron');
 const statusFile=join(ROOT,'temp/kurisu/live-preview.json');
 let attachedPid;
 if(attach){
  const old=JSON.parse(readFileSync(statusFile));
  if(resolve(old.home)!==home||old.requestedPort!==port)throw new Error('Attach target does not match the managed preview');
  process.kill(old.servicePid,0);
  const health=await fetch('http://127.0.0.1:'+port+'/health',{signal:AbortSignal.timeout(5000)});
  if(!health.ok)throw new Error('Existing preview service is unhealthy');
  attachedPid=old.servicePid;
 }
 const directory=join(home,'dsh-pet/pet'),media=join(directory,'kurisu-live-animation');
 mkdirSync(media,{recursive:true});
 const configPath=join(directory,'kurisu-live-config.json');let signature='';
 function sync() {
  const library=JSON.parse(readFileSync(join(PACK,'library.json')));
  const nextSignature=previewSignature(library);
  if(nextSignature===signature)return;
  const previous=existsSync(configPath)?JSON.parse(readFileSync(configPath)):{};
  const full=JSON.parse(readFileSync(join(PACK,'kurisu-config.full.json')));
  const result=liveConfiguration(full,library,previous);
  for(const action of [...result.available,...result.previewOnlyAssets]) {
   const source=resolve(PACK,action.file);
   if(!source.startsWith(PACK+sep))throw new Error('Source escaped pet pack');
   const destination=join(media,result.version(action.name)+'.webm');
   if(!existsSync(destination)) {
    const bytes=readFileSync(source);
    if(createHash('sha256').update(bytes).digest('hex')!==action.sha256)throw new Error('Approved media hash mismatch: '+action.id);
    atomicWrite(destination,bytes);
   }
  }
  atomicWrite(configPath,JSON.stringify(result.config,null,2)+'\n');signature=nextSignature;
  console.log('[kurisu-live] synchronized '+result.available.length+' approved animations'+(result.previewOnlyAssets.length?' + explicit static preview (not counted)':''));
 }
 sync();
 const mainConfig=join(home,'dsh-pet/main-config.jsonc');
 if(!existsSync(mainConfig))atomicWrite(mainConfig,JSON.stringify({notificationsEnabled:false,pets:[{id:'preview-main-hidden',name:'主宠隐藏',size:462,balanceEnabled:false,whisperEnabled:false,workStatusEnabled:false,fixedEnabled:true,display:'none',position:{corner:'bottom-right',marginX:40,marginY:40}}]},null,2));
 let child;
 if(!attach){
  const profile=join(home,'electron-profile');mkdirSync(profile,{recursive:true});
  const bootstrap=join(home,'preview-electron.cjs'),launcher=join(home,'preview-electron.sh');
  writeFileSync(bootstrap,"const {app}=require('electron');app.setPath('userData',"+JSON.stringify(profile)+");require(process.argv[2]);\n");
  writeFileSync(launcher,'#!/bin/sh\nexec '+shellQuote(electron)+' '+shellQuote(bootstrap)+' "$@"\n');chmodSync(launcher,0o755);
  child=spawn(process.execPath,[join(ROOT,'dsh-pet/lib/standalone.js'),'--port',String(port)],{
   cwd:join(ROOT,'dsh-pet'),stdio:'inherit',env:{...process.env,DSH_HOME:home,DSH_PET_ELECTRON_PATH:launcher,DSH_PET_LIVE_PREVIEW:'1'},
  });
 }
 const timer=setInterval(()=>{try{sync()}catch(error){console.error('[kurisu-live] update deferred: '+error.message)}},2000);
 atomicWrite(statusFile,JSON.stringify({supervisorPid:process.pid,servicePid:child?.pid||attachedPid,attached:attach,home,requestedPort:port,config:configPath,startedAt:new Date().toISOString()},null,2));
 const stop=()=>{clearInterval(timer);child?.kill('SIGTERM')};
 process.on('SIGINT',stop);process.on('SIGTERM',stop);
 child?.on('exit',code=>{clearInterval(timer);process.exitCode=code??0});
 child?.on('error',error=>{clearInterval(timer);console.error(error.message);process.exitCode=1});
}

if(process.argv[1]&&existsSync(process.argv[1])&&realpathSync(process.argv[1])===fileURLToPath(import.meta.url)) {
 main().catch(error=>{console.error(error.message);process.exitCode=1});
}
