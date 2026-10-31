#!/usr/bin/env node
/* Isolated playback instrumentation. Dry-run under Node; real run under Electron.
 * No server, profile reuse, FPL token, generation API or ledger write.
 */
const fs=require('node:fs');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'..');
const PREVIEW='http://127.0.0.1:8768/preview.html';
function options(argv){
 const run=argv.includes('--run');
 const at=argv.indexOf('--config');
 if(at<0||!argv[at+1])throw Error('--config PATH is required');
 const config=JSON.parse(fs.readFileSync(path.resolve(argv[at+1]),'utf8'));
 if(config.url!==PREVIEW)throw Error('Only the existing local gallery URL is allowed');
 const out=path.resolve(config.output_dir||'');
 const base=path.join(ROOT,'temp','kurisu');
 if(!out.startsWith(base+path.sep)||out===base)throw Error('output_dir must be a new child of temp/kurisu');
 if(fs.existsSync(out))throw Error('Refusing an existing output/profile directory');
 let ancestor=path.dirname(out);while(!fs.existsSync(ancestor))ancestor=path.dirname(ancestor);
 if(fs.realpathSync(ancestor)!==ancestor)throw Error('Output path may not traverse a symlink');
 const frameRate=config.frame_rate??60,alphaInterval=config.alpha_sample_interval_ms??2500;
 if(!Number.isInteger(frameRate)||frameRate<24||frameRate>120)throw Error('frame_rate must be 24..120');
 if(!Number.isInteger(alphaInterval)||alphaInterval<2000||alphaInterval>3000)throw Error('alpha_sample_interval_ms must be 2000..3000');
 const maxActions=config.max_actions??3;
 if(!Number.isInteger(maxActions)||maxActions<1||maxActions>3)throw Error('max_actions must be 1..3');
 if(config.action_ids&&(!Array.isArray(config.action_ids)||config.action_ids.length>3||config.action_ids.some(x=>!/^a\d{3}$/.test(x))))throw Error('Invalid action_ids');
 if(run&&(!config.decode_slots_confirmed_by||!config.decode_slots_confirmed_at))throw Error('Root must explicitly confirm a decode slot before --run');
 return {run,url:PREVIEW,output_dir:out,user_data:path.join(out,'isolated-user-data'),max_actions:maxActions,
   action_ids:config.action_ids||[],frame_rate:frameRate,alpha_sample_interval_ms:alphaInterval,decode_slots_confirmed_by:config.decode_slots_confirmed_by||null,
   decode_slots_confirmed_at:config.decode_slots_confirmed_at||null};
}
function allowedRequest(url,method='GET'){if(!['GET','HEAD'].includes(method))return false;if(url==='about:blank')return true;try{return new URL(url).origin==='http://127.0.0.1:8768';}catch{return url==='about:blank';}}
function plan(o){return {...o,mode:o.run?'real_playback':'dry_run_no_app_started',
 executable_hint:path.join(process.env.HOME||'','/.dsh/electron/Electron.app/Contents/MacOS/Electron'),
 constraints:{show_window:false,independent_profile:true,background_throttling:false,offscreen:true,network_origin:'http://127.0.0.1:8768',
  approved_only:true,one_video_decoder:true,no_real_profile_or_service_changes:true},
 protocol:['Confirm one available video decoding slot before --run. Do not compete with the two FFmpeg slots.',
  'Load the existing gallery; select up to three currently approved real clips via gallery buttons.',
  'For each clip collect requestVideoFrameCallback and playback quality across one real loop (duration + margin).',
  'Pause/resume through gallery control. If two distinct approved clips exist, observe real src changes between them.',
  'Save small alpha/composite PNG evidence and statistics; never claim continuous human visual review.']};}
function playbackQualityDelta(before,after){
 if(!before||!after)return null;
 return Object.fromEntries(['totalVideoFrames','droppedVideoFrames','corruptedVideoFrames'].map(k=>[k,after[k]-before[k]]));
}
async function collect(o,qualityDelta){
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async(fn,ms=15000)=>{const start=performance.now();while(!fn()){if(performance.now()-start>ms)throw Error('Timed out waiting for gallery/video');await wait(50);}};
 await until(()=>document.querySelector('#gallery .action'));
 const video=document.querySelector('#pet');if(!video||!video.requestVideoFrameCallback)throw Error('requestVideoFrameCallback is required');
 const response=await fetch('library.json',{cache:'no-store'});if(!response.ok)throw Error('Cannot read gallery catalog');
 const library=await response.json();
 const approved=library.actions.filter(a=>a.status==='approved');
 let actions=o.action_ids.length?o.action_ids.map(id=>{const a=approved.find(a=>a.id===id);if(!a)throw Error('Requested action is not approved: '+id);return a;}):approved.slice(0,o.max_actions);
 if(!actions.length)throw Error('No approved real clips available; static placeholder is not an approved animation');
 const report={started_at:new Date().toISOString(),url:location.href,visible:document.visibilityState,
  user_agent:navigator.userAgent,approved_count:approved.length,live_default_notice:document.querySelector('#live-default-notice')?.textContent||'',
  human_continuous_visual_review:false,scope:'Browser decode/playback instrumentation, not source anatomy approval or native desktop runtime validation',
  measurement_version:'prebuffer_rvfc_low_sampling_v3',
  instrumentation_sources:['https://wicg.github.io/video-rvfc/','https://www.electronjs.org/docs/latest/tutorial/offscreen-rendering'],
  clips:[],switches:[],evidence:[]};
 let previous=null;
 for(const action of actions){
  const card=[...document.querySelectorAll('#gallery .action')].find(b=>b.getAttribute('aria-label')?.startsWith(action.name+'，'));
  if(!card||card.disabled)throw Error('Approved gallery button unavailable: '+action.id);
  const oldSrc=video.currentSrc;const switchAt=performance.now();card.click();
  await until(()=>video.readyState>=2&&video.currentSrc.includes(encodeURI(action.file.split('/').pop())));
  if(previous)report.switches.push({from:previous,to:action.id,src_changed:oldSrc!==video.currentSrc,
    load_ms:performance.now()-switchAt,new_current_time:video.currentTime});
  const expectedSrc=video.currentSrc;
  if(new URL(expectedSrc).searchParams.get('v')!==action.sha256)throw Error('Gallery source SHA/version changed before playback');
  if(!(video.duration>=9.9&&video.duration<=10.2))throw Error('Expected ten-second actual clip, got '+video.duration);
  video.muted=true;video.loop=true;
  const item={action_id:action.id,name:action.name,sha256:action.sha256,src:video.currentSrc,duration:video.duration,
    dimensions:[video.videoWidth,video.videoHeight],events:[],errors:[],frame_callbacks:0,loops:0,media_time_min:null,
    media_time_max:0,max_callback_gap_ms:0,alpha_samples:[],pause_resume:null,firstPresented:null,lastPresented:null,missedCallbackCount:0,presentedCounterResets:0};
  const listeners=[];for(const event of ['error','stalled','waiting','playing','pause','ended']){
   const fn=()=>{item.events.push({event,time:video.currentTime,at_ms:performance.now(),phase:item.measurement_started_at_ms===undefined?'prebuffer_seek':'measured_playback'});if(event==='error')item.errors.push(video.error?.message||'video error');};
   video.addEventListener(event,fn);listeners.push([event,fn]);
  }
  video.preload='auto';video.pause();
  await until(()=>video.readyState>=3&&video.buffered.length>0&&video.buffered.end(video.buffered.length-1)>=video.duration-.05,10000);
  video.currentTime=0;await until(()=>!video.seeking&&Math.abs(video.currentTime)<.06&&video.readyState>=2);
  item.prebuffer={ready_state:video.readyState,buffered_end:video.buffered.end(video.buffered.length-1),seek_complete:true};
  const quality=()=>video.getVideoPlaybackQuality?Object.fromEntries(['totalVideoFrames','droppedVideoFrames','corruptedVideoFrames'].map(k=>[k,video.getVideoPlaybackQuality()[k]])):null;
  item.qualityBefore=quality();
  const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});let callbackId,lastNow=null,lastMedia=null,stopped=false,pendingSample=false,sampleTimer=null;
  const evidenceSlots=new Set();
  function sample(mediaTime){
   ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(video,0,0);
   const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data;let transparent=0,partial=0,opaque=0;
   for(let i=3;i<rgba.length;i+=4){if(rgba[i]===0)transparent++;else if(rgba[i]===255)opaque++;else partial++;}
   item.alpha_samples.push({media_time:mediaTime,transparent,partial,opaque,total:rgba.length/4});
   const ordinal=item.alpha_samples.length;
   const slot=item.loops>=1?'after-loop':mediaTime>=video.duration/2?'middle':'opening';
   if(!evidenceSlots.has(slot)){
    evidenceSlots.add(slot);
    const proof=document.createElement('canvas');proof.width=canvas.width*3;proof.height=canvas.height;
    const c=proof.getContext('2d');['#fafafa','#171821','checker'].forEach((bg,j)=>{
     const x=j*canvas.width;if(bg==='checker'){for(let y=0;y<canvas.height;y+=12)for(let dx=0;dx<canvas.width;dx+=12){c.fillStyle=((dx/12+y/12)%2)?'#aaa':'#eee';c.fillRect(x+dx,y,12,12);}}
     else{c.fillStyle=bg;c.fillRect(x,0,canvas.width,canvas.height);}c.drawImage(canvas,x,0);
    });
    report.evidence.push({name:action.id+'-sample-'+ordinal+'.png',media_time:mediaTime,loop:item.loops,evidence_slot:slot,data_url:proof.toDataURL('image/png')});
   }
  }
  function scheduleSample(){
   if(stopped||pendingSample)return;
   pendingSample=true;
   // Canvas readback/PNG happens in a separate task, never within RVFC.
   setTimeout(()=>{pendingSample=false;if(stopped)return;try{sample(video.currentTime);}catch(e){item.errors.push(String(e));stopped=true;}},0);
  }
  const onFrame=(now,meta)=>{if(stopped)return;try{
   if(video.currentSrc!==expectedSrc)throw Error('Source changed or was withdrawn during collection');
   item.frame_callbacks++;if(lastNow!==null)item.max_callback_gap_ms=Math.max(item.max_callback_gap_ms,now-lastNow);
   if(lastMedia!==null&&meta.mediaTime<lastMedia-video.duration/2){item.loops++;scheduleSample();}
   item.media_time_min=item.media_time_min===null?meta.mediaTime:Math.min(item.media_time_min,meta.mediaTime);
   item.media_time_max=Math.max(item.media_time_max,meta.mediaTime);
   if(item.firstPresented===null)item.firstPresented=meta.presentedFrames;
   if(item.lastPresented!==null){
    const gap=meta.presentedFrames-item.lastPresented;
    if(gap>1)item.missedCallbackCount+=gap-1;
    if(gap<0)item.presentedCounterResets++;
   }
   item.lastPresented=meta.presentedFrames;item.last_presented_frames=meta.presentedFrames;
   if(item.frame_callbacks===1)scheduleSample();
   lastNow=now;lastMedia=meta.mediaTime;
  }catch(e){item.errors.push(String(e));stopped=true;}
   if(!stopped)callbackId=video.requestVideoFrameCallback(onFrame);
  };
  item.measurement_started_at_ms=performance.now();
  callbackId=video.requestVideoFrameCallback(onFrame);
  sampleTimer=setInterval(scheduleSample,o.alpha_sample_interval_ms);
  await video.play();
  const start=performance.now();while(performance.now()-start<(video.duration+2)*1000&&item.loops<1&&!stopped)await wait(100);
  // Keep a short decoded tail after the first observed wrap.
  if(item.loops)await wait(500);
  const pause=document.querySelector('#pause');if(pause&&!pause.disabled){
   if(video.paused)await video.play();pause.click();const t=video.currentTime;await wait(300);
   const held=video.paused&&Math.abs(video.currentTime-t)<.06;pause.click();await wait(300);
   item.pause_resume={paused_time_stable:held,resumed:!video.paused&&video.currentTime>t};
  }
  stopped=true;clearInterval(sampleTimer);video.cancelVideoFrameCallback(callbackId);for(const [event,fn] of listeners)video.removeEventListener(event,fn);
  item.qualityAfter=quality();item.playback_quality=item.qualityAfter;item.qualityDelta=qualityDelta(item.qualityBefore,item.qualityAfter);
  item.measurement_elapsed_ms=performance.now()-item.measurement_started_at_ms;
  item.criteria={minimum_rvfc_callbacks:200,minimum_real_loops:1,media_errors:0,alpha_required:true,pause_resume_required:true};
  item.metric_note='RVFC callbacks are best-effort compositor notifications; missedCallbackCount is not a decoded-frame or dropped-frame count. qualityDelta excludes counters accumulated before prebuffer/seek.';
  item.alpha_confirmed=item.alpha_samples.length>0&&item.alpha_samples.every(s=>s.transparent>0&&s.opaque>0);
  item.passed=item.loops>=1&&item.frame_callbacks>=200&&!item.errors.length&&item.alpha_confirmed&&item.pause_resume?.paused_time_stable&&item.pause_resume?.resumed;
  report.clips.push(item);previous=action.id;
 }
 video.pause();
 report.switch_validation=actions.length>=2?'actual_distinct_approved_clip_switches_observed':'not_tested_fewer_than_two_selected_approved_clips';
 report.completed_at=new Date().toISOString();report.passed=report.clips.every(c=>c.passed)&&report.switches.every(s=>s.src_changed);
 return report;
}
async function main(argv,{onOptions=()=>{}}={}){
 const o=options(argv);onOptions(o);if(!o.run){console.log(JSON.stringify(plan(o),null,2));return;}
 const {app,BrowserWindow,session}=require('electron');
 fs.mkdirSync(o.user_data,{recursive:true});app.setPath('userData',o.user_data);
 app.commandLine.appendSwitch('autoplay-policy','no-user-gesture-required');
 app.commandLine.appendSwitch('disable-renderer-backgrounding');
 app.commandLine.appendSwitch('disable-background-timer-throttling');
 let win;const topErrors=[];
 app.on('window-all-closed',()=>{});
 await app.whenReady();
  app.dock?.hide();
 const isolated=session.fromPartition('kurisu-playback-'+Date.now(),{cache:false});
 isolated.webRequest.onBeforeRequest((d,cb)=>cb({cancel:!allowedRequest(d.url,d.method)}));
 win=new BrowserWindow({show:false,width:1100,height:900,webPreferences:{session:isolated,backgroundThrottling:false,nodeIntegration:false,contextIsolation:true,sandbox:true,offscreen:true}});
 win.webContents.setFrameRate(o.frame_rate);
  win.webContents.on('paint',()=>{});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',(e,url)=>{if(url!==o.url)e.preventDefault();});
 win.webContents.on('render-process-gone',(_e,d)=>topErrors.push({event:'render-process-gone',reason:d.reason}));
 try{
  await win.loadURL(o.url);
  const stats=await win.webContents.executeJavaScript('('+collect.toString()+')('+JSON.stringify(o)+',('+playbackQualityDelta.toString()+'))');
  for(const proof of stats.evidence){const bytes=Buffer.from(proof.data_url.split(',')[1],'base64');fs.writeFileSync(path.join(o.output_dir,proof.name),bytes);delete proof.data_url;}
  stats.collector={...plan(o),electron_version:process.versions.electron,chromium_version:process.versions.chrome,top_errors:topErrors};
  fs.writeFileSync(path.join(o.output_dir,'playback-report.json'),JSON.stringify(stats,null,2)+'\n');
  console.log(JSON.stringify({report:path.join(o.output_dir,'playback-report.json'),passed:stats.passed,clips:stats.clips.map(c=>({id:c.action_id,loops:c.loops,frames:c.frame_callbacks,passed:c.passed})),switch_validation:stats.switch_validation}));
  app.exit(stats.passed?0:2);
 }catch(error){fs.writeFileSync(path.join(o.output_dir,'collector-error.json'),JSON.stringify({error:String(error),plan:plan(o),top_errors:topErrors},null,2)+'\n');console.error(String(error));app.exit(1);}
}
function isEntry({nodeMain,electronVersion,processType,argv,filename}){
 if(nodeMain)return true;
 // Electron43's default app imports CommonJS through import(fileURL), so its
 // require.main points at the wrapper rather than this module. Never launch
 // merely because this helper is imported by another Electron/Node module.
 return !!electronVersion&&processType==='browser'&&!!argv[1]
   &&path.resolve(argv[1])===path.resolve(filename);
}
function launchInfo(runtime=process){
 return {event:'kurisu_playback_collector_launch',pid:runtime.pid,
  electron_version:runtime.versions.electron||null,process_type:runtime.type||'node',
  entry_basename:path.basename(runtime.argv[1]||''),
  argument_flags:runtime.argv.slice(2).filter(x=>['--run','--dry-run','--config'].includes(x))};
}
function startWatchdog(onTimeout,setTimer=setTimeout,clearTimer=clearTimeout){
 const timer=setTimer(onTimeout,42000);return ()=>clearTimer(timer);
}
async function launch(argv){
 console.log(JSON.stringify(launchInfo()));
 let activeOptions=null;
 const cancel=startWatchdog(()=>{
  const failure={event:'collector_watchdog_timeout',timeout_ms:42000,launch:launchInfo(),
    scope:'Collector launch/playback timed out; this alone is not a media-quality failure.'};
  console.error(JSON.stringify(failure));
  // Only use the already validated, new collector directory. Never overwrite
  // an earlier failed run or write to the app's existing user profile.
  if(activeOptions?.run&&fs.existsSync(activeOptions.output_dir)){
   try{fs.writeFileSync(path.join(activeOptions.output_dir,'collector-watchdog.json'),JSON.stringify(failure,null,2)+'\n',{flag:'wx'});}catch{}
  }
  if(process.versions.electron&&process.type==='browser'){
   // app.exit only terminates this isolated process. A short hard-exit fallback
   // prevents a stuck Electron shutdown from leaving this QA process resident.
   setTimeout(()=>process.exit(124),1000);
   require('electron').app.exit(124);
  }else process.exit(124);
 });
 try{
  await main(argv,{onOptions:o=>{activeOptions=o;}});
  if(process.versions.electron&&process.type==='browser')require('electron').app.exit(0);
 }catch(error){
  console.error(String(error));
  if(process.versions.electron&&process.type==='browser')require('electron').app.exit(1);
  else process.exitCode=1;
 }finally{cancel();}
}
module.exports={options,allowedRequest,plan,collect,isEntry,launchInfo,startWatchdog,playbackQualityDelta};
if(isEntry({nodeMain:require.main===module,electronVersion:process.versions.electron,
 processType:process.type,argv:process.argv,filename:__filename}))void launch(process.argv.slice(2));
