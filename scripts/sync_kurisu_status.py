#!/usr/bin/env python3
"""Synchronize direction withdrawals and the production blocker to the FPL canvas."""
from uuid import uuid4
from kurisu_library import load, save, production_lock, PACK, calls


if __name__=='__main__':
    from future_props_lab.desktop import desktop_client
    with production_lock():
        state=load();pid=state['project_id']
        with desktop_client() as client:
            canvas=client.visual.get_canvas(project_id=pid)
            ids={n.id for n in canvas.nodes};ops=[]
            for a in state['actions']:
                if a['group']!='移动' and not a.get('withdrawn_approvals'):continue
                for old in a.get('withdrawn_approvals',[]):
                    node=old.get('delivery_node_id')
                    if node and node in ids:
                        label=('旧正面步态' if a['group']=='移动' else
                               '电脑朝向错误' if 'orientation error' in old.get('reason','') else '旧纸质记录')
                        ops.append({'entity':'node','action':'update','id':node,'value':{
                            'approved':False,'title':'已撤回 · '+label+' · '+a['name']}})
                if a['status']=='approved':continue
                ops.append({'entity':'node','action':'update','id':a['node_id'],'value':{
                    'approved':False,'title':('方向返修待生成 · ' if a['group']=='移动' else '电脑版返修待生成 · ')+a['name'],
                    'generation_draft':{'model_id':state['model_id'],'mode':'reference','duration':10,
                        'ratio':'16:9','resolution':'768p','prompt':(PACK/a['prompt_file']).read_text(),
                        'reference_asset_ids':[state['reference_asset_id']]}}})
            count=sum(a['status']=='approved' for a in state['actions'])
            text=(f'完整库目标106条；当前通过{count}条，新增模型调用{calls(state)}/130。正式安装配置保留原两条样片。\n'
                  '移动方向已按用户纠正：左向严格侧身原地步态，向右由运行时镜像。旧三条移动透明交付已撤销；'
                  '前后各2秒转入/退出侧身，实际步态在2–8秒，主程序只沿X轴移动窗口。\n'
                  '整理实验记录改为灰色笔记本电脑：核对数据、少量触控板归档、点头确认，合上并收起；与持续敲键盘区分。\n'
                  '轻步行走、小跑最多4次，拖拽、鼓腮最多3次，其余动作最多2次；总额130不变，其他模型切换2次已用完。\n'
                  + ('原任务结果回收仍受阻；不盲目重提，不提交新任务。\n' if state.get('blocker') else
                     f"原网络失败任务已恢复查询，沿用供应商任务ID，不新增模型调用。最多同时运行{state['limits'].get('concurrent_tasks',2)}个生成任务。\n")+
                  '后续源片逐帧验证饱和纯绿底，白底不再进入自动抠像验收。已生成旧素材进行有记录的残白和绿溢色本地修复，零模型调用；合格版本热更新实时桌宠。\n'+
                  '状态和逐条提示词以仓库pet-packs/kurisu/library.json及prompts/library为准。')
            ops.append({'entity':'node','action':'update','id':'production-brief','value':{'text':text}})
            result=client.visual.apply_canvas_operations(project_id=pid,body={
                'expected_revision':canvas.revision,'request_id':str(uuid4()),'operations':ops})
            state['canvas_status_revision']=result.revision
            save(state)
            print('Canvas status revision',result.revision)
