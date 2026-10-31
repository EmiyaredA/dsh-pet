import copy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np
from unittest.mock import patch

import kurisu_library as lib
from pet_pack_manifest import animation_names, validate_pack
from finalize_kurisu_library import full_config


def action(attempts=0):
    return {'attempts': [{} for _ in range(attempts)]}


def state(actions):
    return {'limits': {'total_calls': 130, 'repair_calls': 26}, 'actions': actions}


class BudgetTests(unittest.TestCase):

    def test_all_frame_gate_accepts_only_flat_saturated_green(self):
        for color,expected in [((250,250,250),False),((0,255,0),True),((0,250,12),True),
                               ((0,0,0),False),((0,0,255),False),((150,230,150),False)]:
            with self.subTest(color=color):
                rgb=np.full((240,8,8,3),color,dtype=np.uint8)
                rgb[:,2:6,2:6]=(80,40,40)
                result=lib.green_background_frames(rgb)
                self.assertEqual(result['passed'],expected)
                self.assertFalse(result['white_matte_fallback'])

    def test_single_late_white_frame_cannot_pass_initial_green_check(self):
        rgb=np.full((240,8,8,3),(0,255,0),dtype=np.uint8)
        rgb[219]=250
        result=lib.green_background_frames(rgb)
        self.assertFalse(result['passed'])
        self.assertEqual(result['failed_frames'],[219])
        self.assertEqual(result['failed_frame_count'],1)
        self.assertFalse(lib.green_background_frames(rgb[:239])['passed'])

    def test_green_background_scan_decodes_all_frames_not_only_first_frame(self):
        rgb=np.full((240,36,64,3),(0,255,0),dtype=np.uint8);rgb[200]=250
        process=SimpleNamespace(stdout=BytesIO(rgb.tobytes()),wait=lambda:0,poll=lambda:0)
        with patch.object(lib.subprocess,'check_output',return_value=b'{"streams":[{"width":64,"height":36}]}'),\
             patch.object(lib.subprocess,'Popen',return_value=process) as run:
            result=lib.source_green_background(Path('fixture.mp4'))
        command=run.call_args.args[0]
        self.assertNotIn('-frames:v',command)
        self.assertEqual(command[command.index('-vf')+1],'fps=24')
        self.assertEqual(result['failed_frames'],[200])

    def test_failed_green_background_never_runs_white_conversion_or_resubmits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pack=root/'pack'
            folder=pack/'source/library/a014/attempt-1';folder.mkdir(parents=True)
            (folder/'nap.mp4').write_bytes(b'already-downloaded-source')
            contact=root/'temp/kurisu/library/review/a014-attempt-1.png';contact.parent.mkdir(parents=True);contact.write_bytes(b'contact')
            attempt={'result_asset_id':'existing-paid-result','task_id':'original-paid-task'}
            a={'id':'a014','name':'nap','group':'daily','status':'generating','attempts':[attempt]}
            s=state([a]);failed={'passed':False,'frames':240,'failed_frame_count':239}
            with patch.object(lib,'ROOT',root),patch.object(lib,'PACK',pack),patch.object(lib,'save'),\
                 patch.object(lib,'source_green_background',return_value=failed),\
                 patch.object(lib,'convert') as convert,patch.object(lib.subprocess,'run') as run:
                # Repeating recovery only rechecks the original result.
                lib.prepare_result(object(),s,a,attempt)
                lib.prepare_result(object(),s,a,attempt)
            convert.assert_not_called();run.assert_not_called()
            self.assertEqual(lib.calls(s),1)
            self.assertEqual(attempt['task_id'],'original-paid-task')
            self.assertEqual(a['status'],'awaiting_review')
            self.assertIn('uniform saturated green',attempt['processing_error'])

    def test_h3_prompt_separates_solid_green_background_from_neutral_character_lighting(self):
        prompt=lib.prompt_for({'group':'日常小动作','name':'整理围裙'},'Smooth her apron.',True)
        sections=['subject_definitions:','summary:','retention_analysis:','detailed_description:','overall_soundscape:','non_diegetic_music:']
        self.assertEqual([prompt.index(s) for s in sections],sorted(prompt.index(s) for s in sections))
        self.assertIn('RGB(0,255,0)',prompt)
        self.assertIn('Character colors remain exactly the reference under uniform neutral illumination',prompt)
        self.assertIn('spaces between hair locks',prompt)
        self.assertIn('NO tail',prompt)
        self.assertNotIn('white',prompt.lower())
        self.assertLess(len(prompt),2200)


    def test_global_cap_includes_every_reserved_submission(self):
        s = state([action(2) for _ in range(65)])
        self.assertFalse(lib.can_submit(s, action()))

    def test_repair_budget_does_not_block_unattempted_actions(self):
        s = state([action(2) for _ in range(26)])
        self.assertFalse(lib.can_submit(s, action(1)))
        self.assertTrue(lib.can_submit(s, action()))

    def test_no_third_attempt_for_an_action(self):
        self.assertFalse(lib.can_submit(state([]), action(2)))

    def test_source_review_may_reject_without_authorizing_a_final_candidate(self):
        a={'id':'a027','status':'awaiting_source_review','attempts':[{'task_id':'original-task'}]}
        s=state([a])
        with patch.object(lib,'save'):
            with self.assertRaises(AssertionError):lib.review(s,'a027','pass','source clearance is insufficient')
            lib.review(s,'a027','reject','prop covers an eye')
        self.assertEqual(a['status'],'rejected')
        self.assertEqual(a['attempts'][0]['task_id'],'original-task')
        self.assertEqual(lib.calls(s),1)

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

    def test_withdrawing_reused_sample_preserves_origin_without_inventing_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            pack=Path(temp);folder=pack/'pet/kurisu-animation';folder.mkdir(parents=True)
            (folder/'idle.webm').write_bytes(b'old-sample')
            (folder/'idle.report.json').write_text('{}')
            a={'id':'a001','status':'approved','reused':True,'file':'pet/kurisu-animation/idle.webm',
               'sha256':'originalhash','delivery_asset_id':'original-result','attempts':[]}
            s=state([a]);before=lib.quota_counts(s)
            with patch.object(lib,'PACK',pack),patch.object(lib,'STATE',pack/'state.json'):
                lib.withdraw(s,'a001','independent review found an extra foreground appendage')
            self.assertEqual(lib.quota_counts(s),before)
            self.assertEqual(a['attempts'],[]);self.assertFalse(a['reused'])
            self.assertEqual(a['status'],'rejected');self.assertNotIn('file',a)
            origin=a['reused_origin_history'][0]
            self.assertTrue(origin['reused_origin']);self.assertEqual(origin['origin_record'],'production.json')
            self.assertEqual(origin['delivery_asset_id'],'original-result')
            archive=pack/a['withdrawn_approvals'][0]['archive_file']
            self.assertEqual(archive.read_bytes(),b'old-sample')
            self.assertFalse((folder/'idle.webm').exists())


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
