#!/usr/bin/env python3
"""Two explicitly bounded same-H3 blue-background first-attempt probes.

The ordinary production hold remains active. All other budget, reservation,
canvas CAS and unknown-submission safeguards remain mandatory.
"""
import hashlib
from pathlib import Path
from kurisu_library import PACK,load,save,production_lock,now,can_submit,calls,ACTIVE

IDS=('a022','a023')


def submit(client,state):
    probe=state.setdefault('blue_background_probe',{'actions':list(IDS),'max_calls':2,
        'authorization':'User permits green or blue background and explicitly requests other animations continue in parallel; two same-H3 first attempts only','created_at':now()})
    reference=PACK/'references/kurisu-front-safe-blue.png'
    digest=hashlib.sha256(reference.read_bytes()).hexdigest()
    label='定稿原图 · 纯蓝底诊断 · '+digest[:16]
    if not probe.get('asset_id'):
        matches=[f for f in client.files.list_files(project_id=state['project_id'],query=label).items if f.display_name==label]
        if len(matches)>1:raise RuntimeError('Ambiguous reference result')
        if matches:probe['asset_id']=matches[0].id
        elif probe.get('upload_started'):raise RuntimeError('Reference upload unknown; reconcile only')
        else:
            probe['upload_started']=True;save(state)
            with reference.open('rb') as stream:
                probe['asset_id']=client.files.upload_file(body={'project_id':state['project_id'],'display_name':label},files={'upload':(reference.name,stream,'image/png')}).id
        probe['reference_sha256']=digest;save(state)
    live=client.generation.list_generation_tasks(project_id=state['project_id'],page_size=100).items
    active=sum(t.status in ACTIVE for t in live)
    for aid in IDS:
        a=next(a for a in state['actions'] if a['id']==aid)
        if a['attempts']:
            if a['attempts'][-1].get('task_id'):continue
            raise RuntimeError('Unknown prior submission; query original node, never resubmit')
        assert a['status']=='planned' and can_submit(state,a)
        if active>=state['limits']['concurrent_tasks']:break
        prompt=(PACK/a['prompt_file']).read_text().replace('green','blue').replace('#00FF00','#0000FF').replace('(0,255,0)','(0,0,255)')
        prompt=prompt.replace('black, blue, transparency','black, green, transparency')
        assert '#0000FF' in prompt and 'black, blue, transparency' not in prompt
        previous=client.generation.list_generation_tasks(project_id=state['project_id'],canvas_node_id=a['node_id']).items
        canvas=client.visual.get_canvas(project_id=state['project_id'])
        snapshot=PACK/'prompts/library'/(aid+'-attempt-1.txt');assert not snapshot.exists()
        t={'started_at':now(),'status':'submission_started','model_id':state['model_id'],'model_slug':state['model_slug'],
            'reference_asset_id':probe['asset_id'],'reference_sha256':digest,'chroma_background':'blue',
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'prompt_file':str(snapshot.relative_to(PACK)),
            'previous_task_ids':[x.id for x in previous],'bounded_background_probe':True}
        a['attempts'].append(t);a['status']='generating';snapshot.write_text(prompt);save(state)
        task=client.generation.create_generation_task(project_id=state['project_id'],body={
            'kind':'video','model_id':state['model_id'],'mode':'reference','duration':10,'ratio':'16:9','resolution':'768p',
            'prompt':prompt,'reference_asset_ids':[probe['asset_id']],'canvas_node_id':a['node_id'],'expected_canvas_revision':canvas.revision})
        t.update(task_id=task.id,status=task.status);save(state);active+=1
        print({'submitted':aid,'task':task.id,'calls':calls(state),'background':'blue'},flush=True)


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        state=load()
        with desktop_client() as client:submit(client,state)
