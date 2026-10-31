const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {options,plan,allowedRequest,collect}=require('./kurisu_playback_collector.cjs');
function fixture(extra={}){
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'kurisu-playback-config-'));
 const file=path.join(folder,'config.json');
 fs.writeFileSync(file,JSON.stringify({url:'http://127.0.0.1:8768/preview.html',output_dir:path.resolve('temp/kurisu/isolated-playback-test-'+Date.now()),...extra}));
 return {file,close:()=>fs.rmSync(folder,{recursive:true})};
}
test('dry run requires no Electron and no output/profile directory creation',()=>{
 const f=fixture();try{const o=options(['--config',f.file,'--dry-run']);assert.equal(o.run,false);assert.equal(plan(o).mode,'dry_run_no_app_started');assert.equal(fs.existsSync(o.output_dir),false);assert.equal(o.user_data,path.join(o.output_dir,'isolated-user-data'));}finally{f.close();}
});
test('real run requires explicit root decode-slot confirmation',()=>{
 const f=fixture();try{assert.throws(()=>options(['--config',f.file,'--run']),/decode slot/);}finally{f.close();}
 const g=fixture({decode_slots_confirmed_by:'root',decode_slots_confirmed_at:'2026-10-31T00:00:00Z'});
 try{assert.equal(options(['--config',g.file,'--run']).run,true);}finally{g.close();}
});
test('only exact local gallery and isolated new output paths allowed',()=>{
 for(const extra of [{url:'http://evil.invalid/preview.html'},{url:'http://127.0.0.1:8770/preview.html'},
  {output_dir:path.resolve('pet-packs/kurisu')},{output_dir:path.resolve('temp/kurisu')},{action_ids:['a001','bogus']}]){
  const f=fixture(extra);try{assert.throws(()=>options(['--config',f.file]));}finally{f.close();}
 }
 const f=fixture({output_dir:path.resolve('temp/kurisu')+'/..'});try{assert.throws(()=>options(['--config',f.file]));}finally{f.close();}
});
test('network requests confined to the gallery origin',()=>{
 assert(allowedRequest('http://127.0.0.1:8768/library.json'));
 assert.equal(allowedRequest('http://127.0.0.1:8768/library.json','POST'),false);
 assert.equal(allowedRequest('http://127.0.0.1:8768/library.json','DELETE'),false);
 assert(allowedRequest('http://127.0.0.1:8768/pet/kurisu-animation/test.webm'));
 for(const url of ['http://localhost:8768/preview.html','http://127.0.0.1:8770/','https://example.com','file:///etc/passwd','http://127.0.0.1:8768.evil.invalid/'])assert.equal(allowedRequest(url),false);
});
test('injected collector compiles and explicitly limits review claims',()=>{
 assert.doesNotThrow(()=>new Function('return ('+collect.toString()+')'));
 const body=collect.toString();assert(body.includes("status==='approved'"));assert(body.includes('requestVideoFrameCallback'));
 assert(body.includes('human_continuous_visual_review:false'));assert(body.includes('not_tested_fewer_than_two_selected_approved_clips'));
 assert(body.includes("pause.click()"));assert(body.includes('getImageData'));
});

test('Electron default-app dynamic-import entry is recognized without require.main equality',()=>{
 const {isEntry}=require('./kurisu_playback_collector.cjs');
 const filename=path.resolve('scripts/kurisu_playback_collector.cjs');
 assert.equal(isEntry({nodeMain:false,electronVersion:'43.3.0',processType:'browser',argv:['Electron',filename,'--run'],filename}),true);
 assert.equal(isEntry({nodeMain:false,electronVersion:'43.3.0',processType:'browser',argv:['Electron','/tmp/other-entry.cjs','--run'],filename}),false);
 assert.equal(isEntry({nodeMain:false,electronVersion:'43.3.0',processType:'renderer',argv:['Electron',filename],filename}),false);
 assert.equal(isEntry({nodeMain:false,electronVersion:undefined,processType:undefined,argv:['node',filename],filename}),false);
 assert.equal(isEntry({nodeMain:true,electronVersion:undefined,argv:['node',filename],filename}),true);
});
test('Node import() does not launch the app, log a launch, or require an Electron dependency',()=>{
 const {spawnSync}=require('node:child_process');
 const {pathToFileURL}=require('node:url');
 const file=path.resolve('scripts/kurisu_playback_collector.cjs');
 const program='await import('+JSON.stringify(pathToFileURL(file).href)+'); console.log("import-only-ok")';
 const result=spawnSync(process.execPath,['--input-type=module','--eval',program],{encoding:'utf8',timeout:3000});
 assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'import-only-ok');
 assert.equal(result.stderr,'');
});
test('safe launch diagnostic logs only known flags and no arbitrary argument values',()=>{
 const {launchInfo}=require('./kurisu_playback_collector.cjs');
 const info=launchInfo({pid:12,type:'browser',versions:{electron:'43.3.0'},
  argv:['Electron','/repo/scripts/kurisu_playback_collector.cjs','--run','--config','/tmp/private-token.json','secret-value']});
 assert.equal(info.entry_basename,'kurisu_playback_collector.cjs');
 assert.deepEqual(info.argument_flags,['--run','--config']);
 assert(!JSON.stringify(info).includes('secret'));assert(!JSON.stringify(info).includes('private-token'));
});
test('watchdog uses 42 seconds and its timer is cancelled after completion',()=>{
 const {startWatchdog}=require('./kurisu_playback_collector.cjs');
 let delay,callback,cancelled;const marker={};
 const cancel=startWatchdog(()=>{},(fn,ms)=>{callback=fn;delay=ms;return marker},t=>{cancelled=t});
 assert.equal(delay,42000);assert.equal(typeof callback,'function');cancel();assert.equal(cancelled,marker);
});

test('A/B rates default to 60fps and low-frequency alpha sampling with bounded overrides',()=>{
 const f=fixture();try{const o=options(['--config',f.file]);assert.equal(o.frame_rate,60);assert.equal(o.alpha_sample_interval_ms,2500);}finally{f.close();}
 const g=fixture({frame_rate:30,alpha_sample_interval_ms:3000});try{const o=options(['--config',g.file]);assert.equal(o.frame_rate,30);assert.equal(o.alpha_sample_interval_ms,3000);}finally{g.close();}
 for(const extra of [{frame_rate:0},{frame_rate:240},{frame_rate:59.5},{alpha_sample_interval_ms:500},{alpha_sample_interval_ms:3001}]){
  const h=fixture(extra);try{assert.throws(()=>options(['--config',h.file]));}finally{h.close();}
 }
});
test('quality delta excludes startup drops and preserves the existing 200 callback criterion',()=>{
 const {playbackQualityDelta}=require('./kurisu_playback_collector.cjs');
 assert.deepEqual(playbackQualityDelta({totalVideoFrames:12,droppedVideoFrames:4,corruptedVideoFrames:0},
  {totalVideoFrames:270,droppedVideoFrames:4,corruptedVideoFrames:0}),{totalVideoFrames:258,droppedVideoFrames:0,corruptedVideoFrames:0});
 assert.equal(playbackQualityDelta(null,{}),null);
 const body=collect.toString();assert(body.includes('frame_callbacks>=200'));
 assert(body.includes('item.missedCallbackCount+=gap-1'));assert(body.includes('item.firstPresented=meta.presentedFrames'));
 const callback=body.slice(body.indexOf('const onFrame='),body.indexOf('item.measurement_started_at_ms=performance.now()'));
 assert(!callback.includes('getImageData'));assert(!callback.includes('toDataURL'));assert(!callback.includes('sample(meta.mediaTime)'));
 assert(body.indexOf('await until(()=>!video.seeking')<body.indexOf('item.qualityBefore=quality()'));
});
