import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch

import kurisu_library as lib
import sync_kurisu_status as sync


class Conflict(Exception):
    status=409
    code='canvas_revision_conflict'
    problem={'message':'画布已变化，请刷新后重试'}


class StatusSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.state_path=self.root/'state.json'
        p=patch.object(lib,'STATE',self.state_path);p.start();self.addCleanup(p.stop)
        self.initial={'project_id':'project','model_id':'h3','limits':{'total_calls':130,'repair_calls':26,'other_model_calls':4},
            'standing_authorization':{'approved':True},'canvas_status_revision':10,'unrelated':{'keep':'initial'},
            'actions':[{'id':'a012','name':'伸懒腰','status':'rejected','node_id':'source-12','attempts':[{'model_id':'h3'}],
                        'withdrawn_approvals':[{'delivery_node_id':'old-delivery'}]}]}
        lib.save(copy.deepcopy(self.initial));self.revision=10
        self.nodes=[NS(id='source-12',approved=True,title='old source'),NS(id='old-delivery',approved=True,title='old delivery'),
                    NS(id='production-brief',text='old brief')]
        self.network_calls=[];self.apply_count=0;self.get_count=0;self.during_apply=None;self.during_get=None
        self.apply_error=None;self.ignore_text=False;owner=self
        class Visual:
            def get_canvas(self,project_id):
                owner.assertFalse(owner.state_path.with_suffix('.lock').exists(),'get_canvas held production_lock')
                owner.network_calls.append('get');owner.get_count+=1
                if owner.during_get:owner.during_get(owner.get_count)
                return NS(revision=owner.revision,nodes=copy.deepcopy(owner.nodes))
            def apply_canvas_operations(self,project_id,body):
                owner.assertFalse(owner.state_path.with_suffix('.lock').exists(),'apply held production_lock')
                owner.network_calls.append('apply');owner.apply_count+=1
                owner.assertEqual(body['expected_revision'],owner.revision)
                if owner.during_apply:owner.during_apply(owner.apply_count)
                if owner.apply_error:raise owner.apply_error
                for op in body['operations']:
                    node=next(n for n in owner.nodes if n.id==op['id'])
                    for key,value in op['value'].items():
                        if not (owner.ignore_text and key=='text'):setattr(node,key,value)
                owner.revision+=1;return NS(revision=owner.revision)
        self.create=Mock(side_effect=AssertionError('Status sync must never generate media'))
        self.client=NS(visual=Visual(),generation=NS(create_generation_task=self.create))

    def change(self,mutator):
        with lib.production_lock():
            state=lib.load();mutator(state);lib.save(state)

    def tearDown(self):
        self.create.assert_not_called()

    def test_all_network_steps_are_unlocked_and_verified_before_local_commit(self):
        result=sync.sync_status(self.client)
        self.assertEqual(self.network_calls,['get','apply','get'])
        self.assertEqual(result['status'],'synced');self.assertFalse(result['needs_retry'])
        self.assertEqual(lib.load()['canvas_status_revision'],11)
        self.assertFalse(next(n for n in self.nodes if n.id=='source-12').approved)
        self.assertIn('用户已授权持续制作至106条合格',next(n for n in self.nodes if n.id=='production-brief').text)
        self.assertEqual(self.initial['actions'],lib.load()['actions'])

    def test_concurrent_unrelated_fields_are_preserved_without_false_stale(self):
        self.during_apply=lambda _:self.change(lambda s:s.update(unrelated={'keep':'new concurrent value'},future_field=42))
        result=sync.sync_status(self.client)
        self.assertEqual(result['status'],'synced');self.assertEqual(self.apply_count,1)
        saved=lib.load();self.assertEqual(saved['unrelated'],{'keep':'new concurrent value'})
        self.assertEqual(saved['future_field'],42);self.assertEqual(saved['canvas_status_revision'],11)

    def test_newer_concurrent_status_revision_is_not_regressed_by_older_apply(self):
        def on_read(n):
            if n==2:
                self.revision=20
                self.change(lambda s:s.update(canvas_status_revision=20))
        self.during_get=on_read
        result=sync.sync_status(self.client)
        self.assertEqual(result['status'],'synced');self.assertEqual(result['applied_revision'],11)
        self.assertEqual(result['verified_revision'],20)
        self.assertEqual(lib.load()['canvas_status_revision'],20)

    def test_relevant_status_change_records_stale_and_does_not_advance_revision(self):
        self.during_apply=lambda _:self.change(lambda s:s['actions'][0].update(status='approved'))
        result=sync.sync_status(self.client,max_stale_retries=0)
        self.assertEqual(result['status'],'stale');self.assertTrue(result['needs_retry'])
        saved=lib.load();self.assertEqual(saved['canvas_status_revision'],10)
        self.assertEqual(saved['actions'][0]['status'],'approved')
        self.assertTrue(saved['canvas_status_sync_history'][-1]['snapshot_stale'])
        self.assertEqual(saved['canvas_status_sync']['applied_revision'],11)

    def test_one_fresh_retry_can_sync_the_new_intent_without_overwriting_others(self):
        def first_only(n):
            if n==1:self.change(lambda s:s['actions'][0].update(status='approved'))
        self.during_apply=first_only
        result=sync.sync_status(self.client,max_stale_retries=1)
        self.assertEqual(self.apply_count,2);self.assertEqual(result['status'],'synced')
        self.assertEqual(lib.load()['canvas_status_revision'],12)
        self.assertEqual([e['status'] for e in lib.load()['canvas_status_sync_history']],['stale','synced'])
        self.assertIn('合格 1/106',next(n for n in self.nodes if n.id=='production-brief').text)

    def test_continuous_changes_stop_after_one_retry_and_require_later_retry(self):
        def toggle(_):
            def edit(s):s['actions'][0]['status']='approved' if s['actions'][0]['status']!='approved' else 'rejected'
            self.change(edit)
        self.during_apply=toggle
        result=sync.sync_status(self.client,max_stale_retries=1)
        self.assertEqual(self.apply_count,2);self.assertEqual(result['status'],'stale')
        self.assertTrue(result['needs_retry']);self.assertEqual(result['attempt'],2)
        self.assertEqual(lib.load()['canvas_status_revision'],10)

    def test_canvas_cas_failure_never_commits_local_revision_or_retries_blindly(self):
        self.apply_error=Conflict('画布版本冲突')
        self.during_apply=lambda _:self.change(lambda s:s.update(concurrent_nonce='preserve-me'))
        with self.assertRaises(Conflict):sync.sync_status(self.client)
        saved=lib.load();self.assertEqual(saved['canvas_status_revision'],10)
        self.assertEqual(saved['concurrent_nonce'],'preserve-me');self.assertEqual(self.apply_count,1)
        self.assertEqual(saved['canvas_status_sync']['status'],'apply_failed')
        self.assertEqual(saved['canvas_status_sync']['error']['http_status'],409)

    def test_failed_content_readback_does_not_claim_success(self):
        self.ignore_text=True
        with self.assertRaisesRegex(RuntimeError,'readback'):sync.sync_status(self.client)
        self.assertEqual(lib.load()['canvas_status_revision'],10)
        self.assertEqual(lib.load()['canvas_status_sync']['status'],'verify_failed')

    def test_network_read_failure_does_not_commit_revision(self):
        with patch.object(self.client.visual,'get_canvas',side_effect=ConnectionError('temporary read failure')):
            with self.assertRaises(ConnectionError):sync.sync_status(self.client)
        self.assertEqual(lib.load()['canvas_status_revision'],10)
        self.assertEqual(lib.load()['canvas_status_sync']['status'],'get_failed')

    def test_empty_operation_set_never_calls_mutation_endpoint(self):
        self.nodes=[]
        result=sync.sync_status(self.client)
        self.assertEqual(result['operation_count'],0);self.assertEqual(self.apply_count,0)
        self.assertEqual(self.network_calls,['get','get']);self.assertEqual(result['status'],'synced')

    def test_more_than_one_automatic_retry_is_rejected_before_network(self):
        for value in [2,99,True,-1]:
            with self.subTest(value=value),self.assertRaises(ValueError):sync.sync_status(self.client,value)
        self.assertFalse(self.network_calls)


if __name__=='__main__':unittest.main()
