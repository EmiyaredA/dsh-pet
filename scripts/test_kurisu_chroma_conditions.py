import copy
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
from test_kurisu_queue import Client,action,remote
import test_kurisu_queue as fixtures


class ChromaConditionTests(unittest.TestCase):
    setUp=fixtures.QueueTests.setUp
    tearDown=fixtures.QueueTests.tearDown
    save=fixtures.QueueTests.save
    def blue(self):
        a=action(1);a.update(next_chroma_background='blue',next_prompt_file='blue.txt')
        text=lib.prompt_for(a,a['direction'],True).replace('GREEN','BLUE').replace('green','blue').replace('0,255,0','0,0,255')
        (self.pack/'blue.txt').write_text(text);return a
    def test_explicit_blue_is_immutable_attempt_condition_without_extra_supplier_field(self):
        self.save([self.blue()]);client=Client();self.assertTrue(queue.submit_one(client))
        t=lib.load()['actions'][0]['attempts'][0]
        self.assertEqual(t['chroma_background'],'blue')
        self.assertNotIn('chroma_background',client.tasks[0].request_payload)
        self.assertIn('BLUE',client.tasks[0].request_payload['prompt'])
        self.assertIn('chroma_background',queue.PROTECTED)
    def test_default_green_remains_compatible(self):
        self.save([action(1)]);client=Client();queue.submit_one(client)
        self.assertEqual(lib.load()['actions'][0]['attempts'][0]['chroma_background'],'green')
    def test_invalid_chroma_or_missing_explicit_blue_prompt_never_reserves_or_creates(self):
        for value in [None,'BLUE','white','',42,True,[],{}]:
            with self.subTest(value=value):
                a=self.blue();a['next_chroma_background']=value;before=self.save([a]);client=Client()
                with self.assertRaises(ValueError):queue.submit_one(client)
                self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
        a=self.blue();a.pop('next_prompt_file');before=self.save([a]);client=Client()
        with self.assertRaisesRegex(ValueError,'authored blue'):queue.submit_one(client)
        self.assertEqual(lib.load(),before);self.assertEqual(client.created,0)
    def test_background_condition_changed_during_preflight_does_not_reserve(self):
        self.save([self.blue()]);client=Client();original=client.get_canvas
        def mutate(**kwargs):
            current=lib.load();current['actions'][0]['next_chroma_background']='green';lib.save(current);return original(**kwargs)
        with patch.object(client,'get_canvas',side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):queue.submit_one(client)
        self.assertEqual(client.created,0);self.assertEqual(lib.calls(lib.load()),0)
    def test_original_blue_unknown_submit_reconciles_and_recovers_without_resubmission(self):
        self.save([self.blue()]);client=Client();client.raise_after_create=True
        queue.submit_one(client);self.assertEqual(client.created,1)
        client.tasks[0].status='completed';client.tasks[0].result_asset_id='original-blue-result'
        queue.poll_originals(client);queue.poll_originals(client)
        t=lib.load()['actions'][0]['attempts'][0]
        self.assertEqual(t['chroma_background'],'blue');self.assertEqual(t['task_id'],'new1')
        self.assertEqual(t['result_asset_id'],'original-blue-result');self.assertEqual(client.created,1)
        payload=copy.deepcopy(client.tasks[0].request_payload);payload['prompt']=payload['prompt'].replace('BLUE','GREEN').replace('0,0,255','0,255,0')
        self.assertFalse(queue.matches_reservation(remote('wrong-color',payload=payload),t))
    def test_worker_cannot_change_saved_chroma_condition(self):
        self.save([self.blue()]);client=Client();queue.submit_one(client)
        state=lib.load();state['actions'][0]['status']='awaiting_processing';state['actions'][0]['attempts'][0]['result_asset_id']='source';lib.save(state)
        job=queue.claim_local()
        with self.assertRaisesRegex(ValueError,'immutable'):
            queue.commit_processing(job,{'attempt_patch':{'chroma_background':'green'}})
