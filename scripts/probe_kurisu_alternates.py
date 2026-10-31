#!/usr/bin/env python3
"""Exactly two approved alternate-workflow first-attempt tests; shared ledger."""
import hashlib
from kurisu_library import PACK,load,save,production_lock,now,can_submit,calls,ACTIVE

PROBES=(('a024','44fa0e72-df87-4c52-9f29-8cf99a3e5c19','reference'),
        ('a025','fcd7c573-a208-411a-8636-80e2658919c0','reference'))


def submit(c,s):
    assert s['limits']['other_model_calls']>=4
    plan=s.setdefault('alternate_workflow_probe',{'actions':[x[0] for x in PROBES],'max_calls':2,
        'authorized_at':now(),'authorization':'User: 允许额外 2 次其他模型测试; total130 unchanged'})
    options={m.id:m for m in c.generation.generation_options().models}
    active=sum(t.status in ACTIVE for t in c.generation.list_generation_tasks(project_id=s['project_id'],page_size=100).items)
    for aid,mid,mode in PROBES:
        a=next(a for a in s['actions'] if a['id']==aid)
        if a['attempts']:
            if a['attempts'][-1].get('task_id'):continue
            reserved=a['attempts'][-1]
            if not reserved.get('preflight_reconciled_no_remote_task'):
                raise RuntimeError('Unknown submission; reconcile only')
            existing=c.generation.list_generation_tasks(project_id=s['project_id'],canvas_node_id=a['node_id']).items
            assert not existing, 'Remote task exists; do not resubmit'
        else:reserved=None
        a['next_model_id']=mid
        assert (reserved is not None or (a['status']=='planned' and can_submit(s,a))) and active<s['limits']['concurrent_tasks']
        model=options[mid];caps=model.video_capabilities
        assert model.slug not in s['excluded_models'] and mode in caps.supported_modes and '16:9' in caps.resolution_ratios['768p']
        prompt=(PACK/a['prompt_file']).read_text()
        canvas=c.visual.get_canvas(project_id=s['project_id']);old=c.generation.list_generation_tasks(project_id=s['project_id'],canvas_node_id=a['node_id']).items
        path=PACK/'prompts/library'/(aid+'-attempt-1.txt');assert not path.exists()
        t={'started_at':now(),'status':'submission_started','model_id':mid,'model_slug':model.slug,
            'reference_asset_id':s['reference_asset_id'],'reference_sha256':s['reference_sha256'],'chroma_background':'green',
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'prompt_file':str(path.relative_to(PACK)),
            'previous_task_ids':[x.id for x in old],'alternate_workflow_test':True,'generation_mode':mode}
        if reserved is not None:
            t['preflight_failures']=reserved.get('preflight_failures',[])
            a['attempts'][-1]=t
        else:a['attempts'].append(t)
        a['status']='generating';path.write_text(prompt);save(s)
        body={'kind':'video','model_id':mid,'mode':mode,'duration':10,'ratio':'16:9','resolution':'768p','prompt':prompt,
            'canvas_node_id':a['node_id'],'expected_canvas_revision':canvas.revision}
        if mode=='frames':body.update(first_frame_asset_id=s['reference_asset_id'],last_frame_asset_id=s['reference_asset_id'])
        else:body['reference_asset_ids']=[s['reference_asset_id']]
        task=c.generation.create_generation_task(project_id=s['project_id'],body=body)
        t.update(task_id=task.id,status=task.status);save(s);active+=1
        print({'submitted':aid,'task':task.id,'model':model.slug,'mode':mode,'calls':calls(s)},flush=True)


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        state=load()
        with desktop_client() as c:submit(c,state)
