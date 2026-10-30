import copy
from pathlib import Path
import tempfile
import unittest
import io
import numpy as np
from PIL import Image
from unittest.mock import patch

import kurisu_library as lib
from pet_pack_manifest import animation_names, validate_pack
from finalize_kurisu_library import full_config


def action(attempts=0):
    return {'attempts': [{} for _ in range(attempts)]}


def state(actions):
    return {'limits': {'total_calls': 130, 'repair_calls': 26}, 'actions': actions}


class BudgetTests(unittest.TestCase):
    def test_flat_matte_gate_accepts_green_and_white_but_rejects_dark_background(self):
        for color,expected in [((250,250,250),True),((0,255,0),True),((0,0,0),False)]:
            with self.subTest(color=color):
                rgb=np.full((8,8,3),color,dtype=np.uint8)
                rgb[2:6,2:6]=(80,40,40)
                data=io.BytesIO();Image.fromarray(rgb).save(data,format='PNG')
                with patch.object(lib.subprocess,'check_output',return_value=data.getvalue()):
                    self.assertEqual(lib.source_has_keyable_border(Path('fixture.mp4')),expected)

    def test_global_cap_includes_every_reserved_submission(self):
        s = state([action(2) for _ in range(65)])
        self.assertFalse(lib.can_submit(s, action()))

    def test_repair_budget_does_not_block_unattempted_actions(self):
        s = state([action(2) for _ in range(26)])
        self.assertFalse(lib.can_submit(s, action(1)))
        self.assertTrue(lib.can_submit(s, action()))

    def test_no_third_attempt_for_an_action(self):
        self.assertFalse(lib.can_submit(state([]), action(2)))

    def test_rejection_uses_the_authorized_action_cap_and_can_resume_a_new_exception(self):
        a={'id':'a010','status':'awaiting_review','attempts':[{},{}]}
        s=state([a]);s['action_attempt_limits']={'a010':3}
        with patch.object(lib,'save'):
            lib.review(s,'a010','reject','wrong side gait')
            self.assertEqual(a['status'],'rejected')
            a['attempts'].append({});a['status']='awaiting_review'
            lib.review(s,'a010','reject','cropped ears')
            self.assertEqual(a['status'],'exhausted')
            with self.assertRaises(AssertionError):lib.retry(s,'a010','retry without authorization')
            s['action_attempt_limits']['a010']=4
            lib.retry(s,'a010','user approved padded framing')
            self.assertEqual(a['status'],'planned')
            self.assertEqual(lib.calls(s),3)

    def test_user_exception_is_scoped_to_one_action_and_keeps_global_cap(self):
        s=state([]);s['action_attempt_limits']={'a010':3}
        a={'id':'a010','attempts':[{},{}]}
        self.assertTrue(lib.can_submit(s,a))
        a['id']='a009';self.assertFalse(lib.can_submit(s,a))
        a['id']='a010';a['attempts'].append({});self.assertFalse(lib.can_submit(s,a))
        s['actions']=[action(2) for _ in range(65)]
        a['attempts'].pop();self.assertFalse(lib.can_submit(s,a))

    def test_only_two_alternate_model_calls(self):
        s = state([{'attempts':[{'model_id':'alternate'}]} for _ in range(2)])
        s['model_id']='default'
        a = {'attempts':[], 'next_model_id':'alternate'}
        self.assertFalse(lib.can_submit(s,a))
        a['next_model_id']='default'
        self.assertTrue(lib.can_submit(s,a))

    def test_live_lock_blocks_second_producer(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(lib, 'STATE', Path(temp) / 'state.json'):
            with lib.production_lock():
                with self.assertRaisesRegex(RuntimeError, 'Another production'):
                    with lib.production_lock():
                        pass
            self.assertFalse((Path(temp) / 'state.lock').exists())

    def test_unknown_submission_is_not_retried(self):
        class Results:
            items = []
        class Generation:
            def list_generation_tasks(self, **kwargs):
                return Results()
            def create_generation_task(self, **kwargs):
                raise AssertionError('Unsafe duplicate submission')
        class Client:
            generation = Generation()
        s = {'project_id': 'test', 'actions': [{'id': 'a', 'node_id': 'node', 'status': 'generating',
            'attempts': [{'previous_task_ids': []}]}]}
        with self.assertRaisesRegex(RuntimeError, 'uncertain submission'):
            lib.tick(Client(), s)

    def test_another_operator_action_is_untouched_but_its_active_tasks_still_limit_submission(self):
        from types import SimpleNamespace
        foreign={'id':'a009','status':'generating','batch':1,'reused':False,'attempts':[{'task_id':'paid-existing'}]}
        own={'id':'a014','status':'planned','batch':3,'queue_order':1,'reused':False,'attempts':[]}
        s=state([foreign,own]);s['project_id']='project'
        for active in [2,0]:
            with self.subTest(active=active):
                class Generation:
                    def list_generation_tasks(self,**kwargs):
                        return SimpleNamespace(items=[SimpleNamespace(status='processing') for _ in range(active)])
                    def get_generation_task(self,**kwargs):raise AssertionError('Must not touch the other operator task')
                    def create_generation_task(self,**kwargs):raise AssertionError('Must not create a new task')
                seen=[]
                with patch.object(lib,'can_submit',side_effect=lambda s,a:seen.append(a['id']) or False):
                    lib.tick(SimpleNamespace(generation=Generation()),s,skip_actions={'a009'})
                self.assertEqual(seen,[] if active==2 else ['a014'])
                self.assertEqual(lib.calls(s),1)

    def test_provider_accepted_but_polling_failed_blocks_new_submissions(self):
        s={'project_id':'project','actions':[{'id':'a101','status':'generation_failed',
            'attempts':[{'provider_task_id':'remote-existing','error':'任务处理失败（ConnectError）'}]}]}
        with patch.object(lib,'save'):
            lib.tick(object(),s)
        self.assertEqual(s['stage'],'blocked_task_reconciliation')
        self.assertEqual(s['blocker']['actions'],['a101'])

    def test_recovery_reuses_original_ids_without_consuming_an_attempt(self):
        from types import SimpleNamespace
        class Generation:
            def get_generation_task(self,task_id):
                return SimpleNamespace(id=task_id,status='failed',can_retry_materialization=True,
                    provider_task_id='remote-'+task_id,error_message='ConnectError',result_asset_id=None)
            def retry_materialization(self,task_id):
                return SimpleNamespace(id=task_id,status='pending',provider_task_id='remote-'+task_id,
                    error_message=None,result_asset_id=None)
        actions=[{'id':aid,'status':'generation_failed','attempts':[{'task_id':aid,'provider_task_id':'remote-'+aid}]} for aid in ['a101','a102']]
        s=state(actions);s['blocker']={'actions':['a101','a102']}
        with patch.object(lib,'save'):
            lib.recover(SimpleNamespace(generation=Generation()),s)
        self.assertEqual(lib.calls(s),2)
        self.assertEqual(s['stage'],'producing')
        self.assertNotIn('blocker',s)
        self.assertTrue(all(a['status']=='generating' for a in actions))
        self.assertEqual(actions[0]['attempts'][0]['task_id'],'a101')

    def test_withdrawing_wrong_direction_preserves_files_and_revokes_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            pack=Path(temp);folder=pack/'pet/kurisu-animation';folder.mkdir(parents=True)
            (folder/'walk.webm').write_bytes(b'old-walk')
            (folder/'walk.report.json').write_text('{}')
            a={'id':'a009','status':'approved','reused':False,'file':'pet/kurisu-animation/walk.webm',
               'sha256':'oldhash','attempts':[{'review':{'verdict':'pass'}}]}
            s=state([a])
            with patch.object(lib,'PACK',pack),patch.object(lib,'STATE',pack/'state.json'):
                lib.withdraw(s,'a009','needs side profile')
            self.assertEqual(a['status'],'rejected');self.assertNotIn('file',a)
            self.assertEqual(a['attempts'][-1]['review']['verdict'],'withdrawn')
            archive=pack/a['withdrawn_approvals'][0]['archive_file']
            self.assertEqual(archive.read_bytes(),b'old-walk')
            self.assertFalse((folder/'walk.webm').exists())


class ManifestTests(unittest.TestCase):
    def test_local_repair_gets_a_new_delivery_node_without_a_model_attempt(self):
        from publish_kurisu_library import delivery_node_id,source_approval
        a={'id':'a103','sha256':'aaaaaaaaaaaa0000','attempts':[{},{}],'withdrawn_approvals':[{},{}]}
        old=delivery_node_id(a);a['sha256']='bbbbbbbbbbbb0000'
        self.assertNotEqual(delivery_node_id(a),old)
        self.assertEqual(len(a['attempts']),2)
        a['name']='records';a['attempts'][-1]['local_edit']={'type':'green_difference_with_tracked_plain_rear_lid'}
        self.assertFalse(source_approval(a)['approved'])

    def test_full_catalog_maps_once_to_runtime_slots_in_exact_order(self):
        import json
        groups = json.loads((lib.PACK/'action-groups.json').read_text())
        current = json.loads((lib.PACK/'pet/kurisu-config.json').read_text())
        config = full_config(current,groups)
        self.assertEqual(len(animation_names(config)),106)
        events = config['animations']['events']
        self.assertEqual(events['workStatus'],groups['工作状态'])
        self.assertEqual(events['balance'],groups['余额'])
        self.assertEqual(events['whisper'],groups['碎碎念'])
        self.assertFalse(config['pets'][0]['whisperEnabled'])
        self.assertFalse(config['pets'][0]['fixedEnabled'])
        self.assertEqual(sum(x['weight'] for x in config['animations']['categories']),80)
    def test_nested_event_and_move_pools_are_included(self):
        config = {'animations': {'idle': ['idle'], 'turn': [], 'drag': [], 'clicks': ['click'],
            'moves': {'actions': [{'name': 'walk'}]}, 'categories': [{'actions': ['research']}],
            'events': {'balance': [['rich-a', 'rich-b']], 'workStatus': ['work']}}}
        self.assertEqual(animation_names(config), {'idle','click','walk','research','rich-a','rich-b','work'})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'pet/kurisu-animation'; directory.mkdir(parents=True)
            for name in animation_names(config) - {'walk'}:
                (directory / (name + '.webm')).write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError, 'walk'):
                validate_pack(root, config)


if __name__ == '__main__':
    unittest.main()
