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
export const cleanAnimationName=name=>name.replace(VERSION,'');

export function liveConfiguration(full,library,previous={}) {
 const available=new Map(library.actions.filter(a=>a.status==='approved').map(a=>[a.name,a]));
 const version=name=>{const a=available.get(name);return a?`${name}__v_${a.sha256.slice(0,12)}`:null};
 const pool=items=>items.filter(n=>available.has(n)).map(version);
 const conf=structuredClone(full),a=conf.animations;
 for(const key of ['idle','turn','drag','clicks'])a[key]=pool(a[key]);
 if(!a.idle.length)throw new Error('Live preview needs an approved idle clip');
 a.moves.actions=a.moves.actions.filter(m=>available.has(m.name)).map(m=>{
  const action=available.get(m.name),next={...m,name:version(m.name)};
  if(action.motion_mode==='continuous-left-profile')next.params={...next.params,leadSec:0,tailSec:0};
  return next;
 });
 a.categories=a.categories.map(c=>({...c,actions:pool(c.actions)})).filter(c=>c.actions.length);
 a.events=Object.fromEntries(Object.entries(a.events).map(([key,slots])=>[key,slots.map(slot=>Array.isArray(slot)?pool(slot):version(slot)).filter(slot=>Array.isArray(slot)?slot.length:slot)]).filter(([,slots])=>slots.length));
 if(!a.events.balance?.length)throw new Error('Live preview needs an approved balance slot for the existing config contract');
 const turn=a.turn.length?10:0,move=a.moves.actions.length?10:0;
 const categoryWeight=a.categories.length?40:0;
 conf.animationWeights={idle:100-turn-move-categoryWeight,turn,move};
 const oldTotal=a.categories.reduce((sum,c)=>sum+c.weight,0);
 a.categories=a.categories.map(c=>({...c,weight:categoryWeight*c.weight/oldTotal}));
 conf.pets=[{id:'kurisu-live',name:'红莉栖 · 实时体验',size:462,display:'desktop',position:{corner:'bottom-right',marginX:180,marginY:55},fixedEnabled:false,balanceEnabled:false,workStatusEnabled:false,whisperEnabled:false,...previous.pets?.[0]}];
 conf.pets[0].whisperEnabled=false;
 return {config:conf,available:[...available.values()],version};
}

function atomicWrite(path,text) {const temp=path+'.next';writeFileSync(temp,text);renameSync(temp,path)}
function shellQuote(text) {return "'"+text.replaceAll("'","'\"'\"'")+"'"}

async function main() {
 const args=process.argv.slice(2);let home=join(ROOT,'temp/kurisu/live-runtime'),port=8770;
 let electron=process.env.DSH_PET_ELECTRON_PATH||join(homedir(),'.dsh/electron/Electron.app/Contents/MacOS/Electron');
 for(let i=0;i<args.length;i++) {
  if(args[i]==='--home')home=resolve(args[++i]);
  else if(args[i]==='--port')port=Number(args[++i]);
  else if(args[i]==='--electron')electron=resolve(args[++i]);
  else throw new Error('Unknown option '+args[i]);
 }
 if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid port');
 if(!existsSync(electron))throw new Error('Provide the installed Electron executable with --electron');
 const directory=join(home,'dsh-pet/pet'),media=join(directory,'kurisu-live-animation');
 mkdirSync(media,{recursive:true});
 const configPath=join(directory,'kurisu-live-config.json');let signature='';
 function sync() {
  const library=JSON.parse(readFileSync(join(PACK,'library.json')));
  const approved=library.actions.filter(a=>a.status==='approved');
  const nextSignature=JSON.stringify(approved.map(a=>[a.id,a.sha256,a.motion_mode]));
  if(nextSignature===signature)return;
  const previous=existsSync(configPath)?JSON.parse(readFileSync(configPath)):{};
  const full=JSON.parse(readFileSync(join(PACK,'kurisu-config.full.json')));
  const result=liveConfiguration(full,library,previous);
  for(const action of result.available) {
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
  console.log('[kurisu-live] synchronized '+result.available.length+' approved animations');
 }
 sync();
 const mainConfig=join(home,'dsh-pet/main-config.jsonc');
 if(!existsSync(mainConfig))atomicWrite(mainConfig,JSON.stringify({notificationsEnabled:false,pets:[{id:'preview-main-hidden',name:'主宠隐藏',size:462,balanceEnabled:false,whisperEnabled:false,workStatusEnabled:false,fixedEnabled:true,display:'none',position:{corner:'bottom-right',marginX:40,marginY:40}}]},null,2));
 const profile=join(home,'electron-profile');mkdirSync(profile,{recursive:true});
 const bootstrap=join(home,'preview-electron.cjs'),launcher=join(home,'preview-electron.sh');
 writeFileSync(bootstrap,"const {app}=require('electron');app.setPath('userData',"+JSON.stringify(profile)+");require(process.argv[2]);\n");
 writeFileSync(launcher,'#!/bin/sh\nexec '+shellQuote(electron)+' '+shellQuote(bootstrap)+' "$@"\n');chmodSync(launcher,0o755);
 const child=spawn(process.execPath,[join(ROOT,'dsh-pet/lib/standalone.js'),'--port',String(port)],{
  cwd:join(ROOT,'dsh-pet'),stdio:'inherit',env:{...process.env,DSH_HOME:home,DSH_PET_ELECTRON_PATH:launcher,DSH_PET_LIVE_PREVIEW:'1'},
 });
 const timer=setInterval(()=>{try{sync()}catch(error){console.error('[kurisu-live] update deferred: '+error.message)}},2000);
 const statusFile=join(ROOT,'temp/kurisu/live-preview.json');
 atomicWrite(statusFile,JSON.stringify({supervisorPid:process.pid,servicePid:child.pid,home,requestedPort:port,config:configPath,startedAt:new Date().toISOString()},null,2));
 const stop=()=>{clearInterval(timer);child.kill('SIGTERM')};
 process.on('SIGINT',stop);process.on('SIGTERM',stop);
 child.on('exit',code=>{clearInterval(timer);process.exitCode=code??0});
 child.on('error',error=>{clearInterval(timer);console.error(error.message);process.exitCode=1});
}

if(process.argv[1]&&realpathSync(process.argv[1])===fileURLToPath(import.meta.url)) {
 main().catch(error=>{console.error(error.message);process.exitCode=1});
}
