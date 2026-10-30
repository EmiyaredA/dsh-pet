#!/usr/bin/env python3
"""Archive accepted Alpha clips through the FPL SDK, without model calls."""
from pathlib import Path
from uuid import uuid4
from kurisu_library import load, save, production_lock, PACK


def delivery_node_id(action):
    return action.get('delivery_node_id') or ('kurisu-delivery-'+action['id']
        + ('-'+action['sha256'][:12] if action.get('withdrawn_approvals') or action.get('media_revisions') else ''))


def source_approval(action):
    edit=action['attempts'][-1].get('local_edit',{}) if action['attempts'] else {}
    repaired=(edit.get('type')=='green_difference_with_tracked_plain_rear_lid'
              or edit.get('removed_gray_tail_pixels',0)>0 or bool(action.get('media_revisions')))
    value={'approved':not repaired}
    if repaired:value['title']='源结果（内容已本地修复） · '+action['name']
    return value


def publish(client, state):
    pid = state['project_id']
    for a in state['actions']:
        if a['status'] != 'approved' or (a.get('reused') and not a.get('media_revisions')):
            continue
        node_id = delivery_node_id(a)
        if not a.get('delivery_asset_id'):
            label = f"透明交付 · {a['id']} · {a['name']} · {a['sha256'][:16]}"
            matches = [x for x in client.files.list_files(project_id=pid, query=label).items
                       if x.display_name == label]
            if len(matches) > 1:
                raise RuntimeError('Ambiguous uploaded results; inspect before publishing')
            if matches:
                a['delivery_asset_id'] = matches[0].id; save(state)
            elif a.get('delivery_upload_started'):
                raise RuntimeError(f"{a['id']} upload outcome unknown; reconcile rather than blindly upload again")
            else:
                a['delivery_upload_started'] = True; save(state)
                path = PACK / a['file']
                with path.open('rb') as stream:
                    asset = client.files.upload_file(body={'project_id':pid,'display_name':label},
                        files={'upload':(path.name,stream,'video/webm')})
                a['delivery_asset_id'] = asset.id; save(state)
        canvas = client.visual.get_canvas(project_id=pid)
        old_nodes={r.get('delivery_node_id') for r in a.get('media_revisions',[])}-{None,node_id}
        retire=[{'entity':'node','action':'update','id':n.id,'value':{
            'approved':False,'title':'旧抠像已替换 · '+a['name']}}
            for n in canvas.nodes if n.id in old_nodes and n.approved]
        if retire:
            client.visual.apply_canvas_operations(project_id=pid,body={
                'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':retire})
            canvas=client.visual.get_canvas(project_id=pid)
        existing = next((n for n in canvas.nodes if n.id == node_id),None)
        if existing:
            assert existing.asset_id == a['delivery_asset_id']
            value=source_approval(a)
            source=next(n for n in canvas.nodes if n.id==a['node_id'])
            if source.approved!=value['approved'] or ('title' in value and source.title!=value['title']):
                result=client.visual.apply_canvas_operations(project_id=pid,body={
                    'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':[
                        {'entity':'node','action':'update','id':a['node_id'],'value':value}]})
                verified=client.visual.get_canvas(project_id=pid)
                assert verified.revision>=result.revision
                assert next(n for n in verified.nodes if n.id==a['node_id']).approved==value['approved']
            a['delivery_node_id'] = node_id; save(state); continue
        i = int(a['id'][1:])
        source_value=source_approval(a)
        operations = [
            {'entity':'node','action':'insert','id':node_id,'value':{
                'id':node_id,'kind':'video','title':'透明交付 · '+a['name'],
                'asset_id':a['delivery_asset_id'],'approved':True,'category_id':a['category_id'],
                'position':{'x':(i%8)*430,'y':7500+(i//8)*300}}},
            {'entity':'node','action':'update','id':a['node_id'],'value':source_value}]
        client.visual.apply_canvas_operations(project_id=pid,body={
            'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':operations})
        verified = client.visual.get_canvas(project_id=pid)
        assert any(n.id == node_id and n.asset_id == a['delivery_asset_id'] for n in verified.nodes)
        a['delivery_node_id'] = node_id; save(state)
        print(a['id']+' published',flush=True)


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        state = load()
        with desktop_client() as client:
            publish(client,state)
