#!/usr/bin/env python3
"""Register the user-approved padded original; never calls a generation model."""
from uuid import uuid4
from kurisu_library import load,save,production_lock,PACK,prompt_for


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        s=load();preparation=s['reference_preparation'];pid=s['project_id']
        label='定稿原图 · 等比缩小绿幕留白 · '+preparation['sha256'][:16]
        with desktop_client() as c:
            if not preparation.get('fpl_asset_id'):
                found=[a for a in c.files.list_files(project_id=pid,query=label).items if a.display_name==label]
                if len(found)>1:raise RuntimeError('Ambiguous reference upload; inspect before continuing')
                if found:
                    preparation['fpl_asset_id']=found[0].id;save(s)
                elif preparation.get('upload_started'):
                    raise RuntimeError('Reference upload outcome unknown; do not upload again blindly')
                else:
                    preparation['upload_started']=True;save(s)
                    path=PACK/preparation['file']
                    with path.open('rb') as stream:
                        asset=c.files.upload_file(body={'project_id':pid,'display_name':label},files={'upload':(path.name,stream,'image/png')})
                    preparation['fpl_asset_id']=asset.id;save(s)
            reference_id=preparation['fpl_asset_id'];node_id='approved-front-safe'
            canvas=c.visual.get_canvas(project_id=pid)
            existing=next((n for n in canvas.nodes if n.id==node_id),None)
            if existing:
                assert existing.asset_id==reference_id
            else:
                c.visual.apply_canvas_operations(project_id=pid,body={'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':[
                    {'entity':'node','action':'insert','id':node_id,'value':{'id':node_id,'kind':'image','title':'视频构图 · 原图等比缩小与绿幕留白 · 用户确认','asset_id':reference_id,'approved':True,'category_id':'character','position':{'x':1500,'y':-650}}}]})
            planned=[a for a in s['actions'] if a['status']=='planned']
            for start in range(0,len(planned),20):
                operations=[]
                for a in planned[start:start+20]:
                    prompt=prompt_for(a,a['direction'],prepared_reference=True)
                    (PACK/a['prompt_file']).write_text(prompt)
                    operations.append({'entity':'node','action':'update','id':a['node_id'],'value':{'approved':False,'generation_draft':{
                        'model_id':s['model_id'],'mode':'reference','duration':10,'ratio':'16:9','resolution':'768p','prompt':prompt,'reference_asset_ids':[reference_id]}}})
                canvas=c.visual.get_canvas(project_id=pid)
                result=c.visual.apply_canvas_operations(project_id=pid,body={'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':operations})
                preparation['canvas_revision']=result.revision;save(s)
            s['reference_asset_id']=reference_id;s['reference_sha256']=preparation['sha256'];preparation['status']='active';save(s)
            print({'reference_asset_id':reference_id,'planned_drafts_updated':len(planned),'model_calls_added':0})
