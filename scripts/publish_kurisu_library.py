#!/usr/bin/env python3
"""Archive accepted Alpha clips through the FPL SDK, without model calls."""
import hashlib
import io
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


def current_action(state,aid,digest):
    a=next((a for a in state['actions'] if a['id']==aid),None)
    lock=a.get('human_action_hold',{}) if a else {}
    if (lock.get('active') is True and lock.get('mode')=='immutable_selected_media'
            and digest!=lock.get('sha256')):
        raise PermissionError('Human selected an immutable existing media SHA; refusing another version')
    return a if a and a['status']=='approved' and a['sha256']==digest else None


def ensure_upload(client,snapshot):
    """Reserve/commit briefly; listing and media upload never hold the ledger lock."""
    state=load();a=current_action(state,snapshot['id'],snapshot['sha256'])
    if not a:return None
    if a.get('delivery_asset_id'):return a['delivery_asset_id']
    pid=state['project_id'];label=f"透明交付 · {a['id']} · {a['name']} · {a['sha256'][:16]}"
    matches=[x for x in client.files.list_files(project_id=pid,query=label).items if x.display_name==label]
    if len(matches)>1:raise RuntimeError('Ambiguous uploaded results; inspect before publishing')
    asset_id=matches[0].id if matches else None
    if asset_id is None:
        path=PACK/a['file']
        try:media=path.read_bytes()
        except FileNotFoundError:
            if not current_action(load(),a['id'],a['sha256']):return None
            raise
        if hashlib.sha256(media).hexdigest()!=a['sha256']:
            raise ValueError('Approved media hash changed before upload: '+a['id'])
        with production_lock():
            fresh=load();live=current_action(fresh,a['id'],a['sha256'])
            if not live:return None
            if live.get('delivery_asset_id'):return live['delivery_asset_id']
            if live.get('delivery_upload_started'):
                raise RuntimeError(a['id']+' upload outcome unknown; reconcile rather than blindly upload again')
            live['delivery_upload_started']=True;save(fresh)
        with io.BytesIO(media) as stream:
            asset_id=client.files.upload_file(body={'project_id':pid,'display_name':label},
                files={'upload':(path.name,stream,'video/webm')}).id
    with production_lock():
        fresh=load();live=current_action(fresh,a['id'],a['sha256'])
        if not live:return None
        live['delivery_asset_id']=asset_id;save(fresh)
    return asset_id


def publish_canvas(client,state,a):
    # Only the short, revision-checked canvas write is serialized with the queue.
    pid=state['project_id'];node_id=delivery_node_id(a)
    canvas = client.visual.get_canvas(project_id=pid)
    old_nodes={r.get('delivery_node_id') for r in
        a.get('media_revisions',[])+a.get('withdrawn_approvals',[])}-{None,node_id}
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
        # Human acceptance may restore the exact previously withdrawn SHA/node.
        # Restore only this current delivery; its source retains its own verdict.
        operations=[]
        delivery_value={'approved':True,'title':'透明交付 · '+a['name']}
        if existing.approved is not True or existing.title!=delivery_value['title']:
            operations.append({'entity':'node','action':'update','id':node_id,
                               'value':delivery_value})
        value=source_approval(a)
        source=next(n for n in canvas.nodes if n.id==a['node_id'])
        if source.approved!=value['approved'] or ('title' in value and source.title!=value['title']):
            operations.append({'entity':'node','action':'update','id':a['node_id'],'value':value})
        if operations:
            result=client.visual.apply_canvas_operations(project_id=pid,body={
                'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':operations})
            verified=client.visual.get_canvas(project_id=pid)
            assert verified.revision>=result.revision
            assert next(n for n in verified.nodes if n.id==a['node_id']).approved==value['approved']
            restored=next(n for n in verified.nodes if n.id==node_id)
            assert restored.asset_id==a['delivery_asset_id'] and restored.approved is True
            assert restored.title==delivery_value['title']
        a['delivery_node_id'] = node_id; save(state); return
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
    inserted=next(n for n in verified.nodes if n.id==node_id)
    assert inserted.asset_id==a['delivery_asset_id']
    # FPL inserts may initialize review state to false despite the insert value.
    # Commit the explicit delivery verdict separately, then verify it persisted.
    if inserted.approved is not True:
        result=client.visual.apply_canvas_operations(project_id=pid,body={
            'expected_revision':verified.revision,'request_id':str(uuid4()),'operations':[
                {'entity':'node','action':'update','id':node_id,'value':{
                    'approved':True,'title':'透明交付 · '+a['name']}}]})
        verified=client.visual.get_canvas(project_id=pid)
        assert verified.revision>=result.revision
    assert any(n.id==node_id and n.asset_id==a['delivery_asset_id'] and n.approved is True
               for n in verified.nodes)
    a['delivery_node_id'] = node_id; save(state)
    print(a['id']+' published',flush=True)


def publish(client,state=None):
    snapshot=state or load()
    for saved in snapshot['actions']:
        if saved['status']!='approved' or (saved.get('reused') and not saved.get('media_revisions')):continue
        asset=ensure_upload(client,saved)
        if not asset:continue
        with production_lock():
            fresh=load();a=current_action(fresh,saved['id'],saved['sha256'])
            if not a or a.get('delivery_asset_id')!=asset:continue
            # A generation-create reservation serializes canvas writes even
            # while its network operation is outside the ledger lock.
            if any(x['attempts'] and x['status'] in {'generating','submission_uncertain'}
                    and not x['attempts'][-1].get('task_id') for x in fresh['actions']):continue
            publish_canvas(client,fresh,a)


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with desktop_client() as client:publish(client)
