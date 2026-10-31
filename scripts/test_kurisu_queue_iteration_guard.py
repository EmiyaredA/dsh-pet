from contextlib import contextmanager
import copy,hashlib
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
import test_kurisu_queue as fixtures
from test_kurisu_iteration_policy import state as policy_state


class QueueIterationGuardTests(unittest.TestCase):
    setUp=fixtures.QueueTests.setUp
    tearDown=fixtures.QueueTests.tearDown
    save=fixtures.QueueTests.save
    def policy(self,*actions):return policy_state(*actions)['iteration_policy']
    def test_first_pass_ranks_before_old_priority_id_but_legacy_order_stays(self):
        old=fixtures.action(9,attempt={'task_id':'prior'});new=fixtures.action(31,batch=9)
        s=self.save([old,new],priority_ids=['a009'])
        self.assertEqual(queue.ranked(s)[0]['id'],'a009')
        s['iteration_policy']=self.policy(old,new)
        self.assertEqual(queue.ranked(s)[0]['id'],'a031')
    def test_exhausted_correction_rejects_before_source_reads_or_archive_creation(self):
        a=fixtures.action(31,status='processing_failed',attempt={'task_id':'second','result_asset_id':'source','source_file':'missing.mp4'})
        a['attempts'].insert(0,{'task_id':'first'})
        before=self.save([a],iteration_policy=self.policy(a))
        with self.assertRaises(PermissionError):queue.request_local('a031','another repair')
        self.assertEqual(lib.load(),before);self.assertFalse((self.pack/'quality/processing-history').exists())
    def test_concurrent_correction_claim_rechecked_under_fresh_lock(self):
        raw=self.pack/'raw.mp4';raw.write_bytes(b'original-source')
        a=fixtures.action(31,status='processing_failed',attempt={'task_id':'first','result_asset_id':'source','source_file':'raw.mp4','source_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'candidate_file':'old.webm'})
        self.save([a],iteration_policy=self.policy(a));original=lib.production_lock
        @contextmanager
        def race():
            fresh=lib.load();fresh['actions'][0]['attempts'][0]['local_reprocess_requests']=[{'at':'concurrent','reason':'already claimed sole correction'}];lib.save(fresh)
            with original():yield
        with patch.object(queue,'load_source_review',return_value={'processing_clearance':queue.ALLOW}),patch.object(lib,'production_lock',race):
            with self.assertRaises(PermissionError):queue.request_local('a031','racing repair')
        saved=lib.load();self.assertEqual(len(saved['actions'][0]['attempts'][0]['local_reprocess_requests']),1)
        self.assertEqual(saved['actions'][0]['attempts'][0]['candidate_file'],'old.webm');self.assertEqual(saved['actions'][0]['status'],'processing_failed');self.assertEqual(lib.calls(saved),1)
