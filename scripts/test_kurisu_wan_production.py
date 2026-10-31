import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import kurisu_library as lib
import kurisu_queue as queue
from test_kurisu_queue import Client,action,remote
import test_kurisu_queue as fixtures


class WanClient(Client):
    def __init__(self):
        super().__init__();self.files=self;self.assets=[NS(id='ref',media_kind='image'),NS(id='motion-video',media_kind='video')];self.canvas_nodes=None;self.puts=0
    def get_canvas(self,**kwargs):
        self.unlocked()
        if self.canvas_nodes is None:self.canvas_nodes=[{'id':a['node_id'],'kind':'video','asset_id':None} for a in lib.load()['actions']]
        return NS(revision=self.revision,nodes=copy.deepcopy(self.canvas_nodes),edges=[],categories=[])
    def put_canvas(self,project_id,body):
        self.unlocked();assert body['expected_revision']==self.revision
        self.canvas_nodes=copy.deepcopy(body['nodes']);self.revision+=1;self.puts+=1
    def generation_options(self):
        options=super().generation_options()
        cap=NS(supported_modes=['reference'],supports_prompt=False,supports_duration=False,supports_ratio=False,
            supports_seed=True,resolutions=['832x464'],reference_limits={'image':1,'video':1},
            reference_video_upload_configured=True,seed_minimum=1,seed_maximum=999999)
        options.models.append(NS(id=queue.WAN_MODEL_ID,slug=queue.WAN_MODEL_SLUG,video_capabilities=cap))
        return options
    def list_files(self,**kwargs):self.unlocked();return NS(items=self.assets)


class WanProductionTests(unittest.TestCase):
    setUp=fixtures.QueueTests.setUp
    tearDown=fixtures.QueueTests.tearDown
    save=fixtures.QueueTests.save
    def wan_action(self):
        source=self.pack/'motion.mp4';source.write_bytes(b'verified-official-motion-video')
        sha=hashlib.sha256(source.read_bytes()).hexdigest()
        self.review={'action_id':'a001','driver_asset_id':'motion-video','driver_sha256':sha,
            'source_file':'motion.mp4','source_duration_seconds':10.125,'source_frame_count':243,'source_fps':'24/1',
            'expected_action':'Small celebratory fist pump, then neutral standing pose',
            'motion_clearance':'allow_motion_transfer_only','final_media_approved':False,
            'reviewer':'independent_animation_qa_agent','reviewed_at':lib.now(),
            'visual_review_performed':True,'automated_metrics_only':False,
            'composition':{'reference_sha256':'refhash','matched_to_reference':True,'first_last_same':True},
            'original_source_background':{'passed':False},'original_final_source_verdict':'reject'}
        folder=self.pack/'quality/motion-drivers';folder.mkdir(parents=True,exist_ok=True)
        self.review_path=folder/'a001.json';self.review_path.write_text(json.dumps(self.review))
        a=action(1);a.update(next_model_id=queue.WAN_MODEL_ID,next_generation_mode='reference',
            next_video_asset_id='motion-video',next_driver_sha256=sha,next_driver_review_file='quality/motion-drivers/a001.json',
            next_workflow_parameters={'seed':314159},next_first_frame_asset_id='stale-H3-first',
            next_last_frame_asset_id='stale-H3-last',next_prompt_file='stale-H3-prompt.txt')
        return a

    def test_later_anatomy_withdrawal_overrides_old_motion_allow_before_reservation(self):
        a=self.wan_action();state=self.save([a]);self.client=WanClient()
        report=self.pack/'anatomy.json'
        report.write_text(json.dumps({'action_id':a['id'],'classification':'unapproved_foreground_appendage',
            'withdraw_recommended':True,'raw_source_sha256':a['next_driver_sha256']}))
        state['actions'][0]['withdrawn_approvals']=[{'independent_review_file':'anatomy.json',
            'independent_review_sha256':hashlib.sha256(report.read_bytes()).hexdigest()}];lib.save(state)
        before=copy.deepcopy(lib.load())
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)

    def test_wan_request_has_only_supported_motion_inputs_and_seed(self):
        a=self.wan_action();self.save([a]);self.client=WanClient()
        self.assertTrue(queue.submit_one(self.client));payload=self.client.tasks[0].request_payload
        self.assertEqual(payload['model_id'],queue.WAN_MODEL_ID)
        self.assertFalse({'prompt','duration','ratio','first_frame_asset_id','last_frame_asset_id'}&payload.keys())
        self.assertEqual(payload['reference_asset_ids'],['ref']);self.assertEqual(payload['video_asset_ids'],['motion-video'])
        self.assertEqual(payload['workflow_parameters'],{'seed':314159});self.assertEqual(payload['resolution'],'832x464')
        t=lib.load()['actions'][0]['attempts'][0]
        self.assertEqual(t['strategy'],'wan_motion_reference_v1')
        self.assertEqual(t['driver_asset_id'],'motion-video');self.assertEqual(t['driver_sha256'],a['next_driver_sha256'])
        self.assertEqual(t['driver_review_sha256'],hashlib.sha256(self.review_path.read_bytes()).hexdigest())
        self.assertFalse(t['raw_duration_controlled_by_request']);self.assertNotIn('duration',t);self.assertNotIn('prompt_file',t)
        self.assertEqual(t['expected_output']['frames'],240)
        self.assertEqual(t['expected_output']['short_source_policy'],'reject_no_repeat_or_time_stretch')
        self.assertEqual(t['processing_profile'],'wan_normal_green_key_no_palette')
        request=self.pack/t['request_file'];self.assertEqual(hashlib.sha256(request.read_bytes()).hexdigest(),t['request_sha256'])
        self.assertNotIn('prompt',json.loads(request.read_text()))

    def test_motion_clearance_does_not_approve_original_or_new_final_media(self):
        a=self.wan_action();self.save([a]);self.client=WanClient();queue.submit_one(self.client)
        s=lib.load();self.assertEqual(s['actions'][0]['status'],'generating')
        self.assertEqual(self.review['original_final_source_verdict'],'reject')
        self.assertFalse(self.review['original_source_background']['passed'])
        self.assertNotEqual(s['actions'][0]['status'],'approved')
        self.assertEqual(lib.calls(s),1)

    def test_incomplete_or_wrong_identity_motion_reviews_never_reserve(self):
        for mutation in [dict(motion_clearance='pending'),dict(action_id='a105'),dict(driver_asset_id='other-video'),
                         dict(final_media_approved=True),dict(visual_review_performed=False),dict(automated_metrics_only=True),
                         dict(reviewer=None),dict(source_duration_seconds=9.99),dict(source_duration_seconds=float('inf')),
                         dict(composition={'reference_sha256':'wrong','matched_to_reference':True,'first_last_same':True}),
                         dict(composition={'reference_sha256':'refhash','matched_to_reference':False,'first_last_same':True}),
                         dict(composition={'reference_sha256':'refhash','matched_to_reference':True,'first_last_same':False})]:
            with self.subTest(mutation=mutation):
                a=self.wan_action();self.review.update(mutation);self.review_path.write_text(json.dumps(self.review))
                before=self.save([a]);self.client=WanClient()
                with self.assertRaises(ValueError):queue.submit_one(self.client)
                self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)

    def test_missing_driver_changed_bytes_and_unregistered_asset_never_reserve(self):
        for mutation in [dict(next_video_asset_id=None),dict(next_driver_sha256='wrong'),
                         dict(next_driver_review_file=None),dict(next_driver_review_file='../outside.json'),
                         dict(next_workflow_parameters={'seed':314159,'duration':10}),
                         dict(next_workflow_parameters={'seed':True}),dict(next_workflow_parameters={'seed':0})]:
            with self.subTest(mutation=mutation):
                a=self.wan_action();a.update(mutation);before=self.save([a]);self.client=WanClient()
                with self.assertRaises(ValueError):queue.submit_one(self.client)
                self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)
        a=self.wan_action();before=self.save([a]);(self.pack/'motion.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before)
        a=self.wan_action();before=self.save([a]);self.client.assets=self.client.assets[:1]
        with self.assertRaisesRegex(ValueError,'formal project'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)

    def test_live_wan_capability_mismatch_is_preflight_without_paid_attempt(self):
        a=self.wan_action();before=self.save([a]);self.client=WanClient();options=self.client.generation_options()
        options.models[-1].video_capabilities.supports_duration=True
        with patch.object(self.client,'generation_options',return_value=options):
            with self.assertRaisesRegex(ValueError,'Wan model'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)

    def test_unknown_wan_submit_reconciles_exact_video_and_seed_without_recreating(self):
        a=self.wan_action();self.save([a]);self.client=WanClient();self.client.raise_after_create=True
        queue.submit_one(self.client)
        t=lib.load()['actions'][0]['attempts'][0]
        self.assertEqual(t['task_id'],'new1');self.assertEqual(self.client.created,1)
        queue.poll_originals(self.client);self.assertEqual(self.client.created,1)
        payload=copy.deepcopy(self.client.tasks[0].request_payload)
        self.assertTrue(queue.matches_reservation(remote('same',payload=payload),t))
        for mutation in [dict(video_asset_ids=['wrong']),dict(reference_asset_ids=['wrong']),
                         dict(workflow_parameters={'seed':42}),dict(prompt='H3 instructions'),dict(resolution='768p')]:
            with self.subTest(mutation=mutation):
                self.assertFalse(queue.matches_reservation(remote('wrong',payload={**payload,**mutation}),t))
        missing=remote('missing');missing.request_payload=None;self.assertFalse(queue.matches_reservation(missing,t))

    def test_motion_conditioning_cannot_be_rewritten_by_local_worker(self):
        a=self.wan_action();self.save([a]);self.client=WanClient();queue.submit_one(self.client)
        s=lib.load();s['actions'][0]['status']='awaiting_processing';s['actions'][0]['attempts'][0]['result_asset_id']='known';lib.save(s)
        job=queue.claim_local()
        for field in ['driver_asset_id','driver_sha256','driver_review_sha256','expected_action','workflow_parameters',
                      'expected_output','raw_duration_controlled_by_request','processing_profile']:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'immutable'):
                queue.commit_processing(job,{'attempt_patch':{field:'changed'}})
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['driver_asset_id'],'motion-video')

    def test_review_change_during_preflight_is_rejected_before_any_paid_reservation(self):
        a=self.wan_action();self.save([a]);self.client=WanClient()
        def mutate_review(**kwargs):
            self.review['expected_action']='Changed while model and assets were being checked'
            self.review_path.write_text(json.dumps(self.review))
            return NS(revision=1,nodes=[{'id':'node1','kind':'video','asset_id':None}])
        with patch.object(self.client,'get_canvas',side_effect=mutate_review):
            with self.assertRaisesRegex(RuntimeError,'changed during preflight'):queue.submit_one(self.client)
        self.assertEqual(lib.calls(lib.load()),0);self.assertEqual(self.client.created,0)

    def test_driver_owned_by_target_node_is_rejected_before_reservation(self):
        a=self.wan_action();before=self.save([a]);self.client=WanClient()
        canvas=NS(revision=1,nodes=[{'id':'node1','kind':'video','asset_id':'motion-video'}])
        with patch.object(self.client,'get_canvas',return_value=canvas):
            with self.assertRaisesRegex(ValueError,'self_asset_reference'):queue.submit_one(self.client)
        self.assertEqual(lib.load(),before);self.assertEqual(self.client.created,0)

    def test_new_source_variant_preserves_old_node_asset_action_id_and_attempt_history(self):
        a=self.wan_action();a['status']='rejected';self.save([a]);self.client=WanClient()
        self.client.canvas_nodes=[{'id':'node1','kind':'video','asset_id':'motion-video','final_output_id':'preserved-output'}]
        node=queue.prepare_wan_variant(self.client,'a001','wan-production-01')
        self.assertEqual(self.client.canvas_nodes[0]['asset_id'],'motion-video')
        self.assertEqual(self.client.canvas_nodes[0]['final_output_id'],'preserved-output')
        self.assertEqual(lib.load()['actions'][0]['id'],'a001');self.assertEqual(lib.load()['actions'][0]['attempts'],[])
        self.assertEqual(lib.load()['actions'][0]['node_id'],node)
        self.assertEqual(lib.load()['actions'][0]['node_history'][0]['previous_node_id'],'node1')
        self.assertEqual(self.client.created,0)
        queue.prepare_wan_variant(self.client,'a001','wan-production-01')
        self.assertEqual(self.client.puts,1);self.assertEqual(len(lib.load()['actions'][0]['node_history']),1)

    def test_variant_cannot_bypass_an_unresolved_existing_submission(self):
        a=self.wan_action();a['status']='submission_uncertain';self.save([a]);self.client=WanClient()
        with self.assertRaisesRegex(ValueError,'Resolve'):queue.prepare_wan_variant(self.client,'a001','wan-production-01')
        self.assertEqual(self.client.puts,0);self.assertEqual(lib.calls(lib.load()),0)

    def test_worker_may_echo_the_same_profile_without_changing_conditions(self):
        a=self.wan_action();self.save([a]);self.client=WanClient();queue.submit_one(self.client)
        s=lib.load();s['actions'][0]['status']='awaiting_processing';s['actions'][0]['attempts'][0]['result_asset_id']='known';lib.save(s)
        job=queue.claim_local();profile=job['attempt']['processing_profile']
        self.assertTrue(queue.commit_processing(job,{'attempt_patch':{'processing_profile':profile},'action_status':'awaiting_source_review'}))
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['processing_profile'],profile)


if __name__=='__main__':unittest.main()
