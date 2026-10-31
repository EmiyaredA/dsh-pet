import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kurisu_motion_reuse import assert_motion_source_reusable


class MotionReuseGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.pack=Path(self.tmp.name)
        self.driver='a'*64;self.path=self.pack/'withdrawal.json'
        self.report={'action_id':'a001','classification':'unapproved_foreground_appendage',
                     'withdraw_recommended':True,'raw_source_sha256':self.driver}
        self.state={'actions':[{'id':'a001','quality_hold':{'report_file':'withdrawal.json'},'withdrawn_approvals':[]}]}
        self.bind()
    def tearDown(self):self.tmp.cleanup()
    def bind(self):
        self.path.write_text(json.dumps(self.report))
        self.state['actions'][0]['withdrawn_approvals']=[{'independent_review_file':'withdrawal.json',
            'independent_review_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}]
    def test_same_bytes_blocked_even_under_new_asset_or_diagnostic_identity(self):
        before=copy.deepcopy(self.state)
        for asset in ['original','new-formal-copy']:
            with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
                assert_motion_source_reusable(self.state,self.pack,self.driver,asset)
        self.assertEqual(self.state,before)
    def test_recorded_diagnostic_descendant_is_held_without_changing_completed_history(self):
        self.state['diagnostic_attempts']=[{'status':'completed','task_id':'old-paid-task',
            'source_sha256':'b'*64,'result_asset_id':'derived-driver',
            'inputs':{'driver':{'sha256':self.driver,'asset_id':'original-driver'}}}]
        before=copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
            assert_motion_source_reusable(self.state,self.pack,'b'*64,'derived-driver')
        self.assertEqual(self.state,before)

    def test_unrelated_motion_only_driver_or_background_rejection_not_blocked(self):
        assert_motion_source_reusable(self.state,self.pack,'b'*64,'a105-driver')
        self.report['classification']='background_failure';self.bind()
        assert_motion_source_reusable(self.state,self.pack,self.driver,'motion-allowed-white-background')
    def test_tampering_missing_evidence_and_wrong_action_fail_closed(self):
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'SHA changed'):
            assert_motion_source_reusable(self.state,self.pack,self.driver)
        self.path.unlink()
        with self.assertRaisesRegex(ValueError,'unavailable'):
            assert_motion_source_reusable(self.state,self.pack,self.driver)
        self.report['action_id']='a105';self.bind()
        with self.assertRaisesRegex(ValueError,'identity'):
            assert_motion_source_reusable(self.state,self.pack,self.driver)
    def test_unbound_old_warning_does_not_become_false_authoritative_revocation(self):
        self.state['actions'][0]['withdrawn_approvals']=[]
        assert_motion_source_reusable(self.state,self.pack,self.driver)
    def test_explicit_same_asset_link_blocks_even_when_different_hash_claimed(self):
        self.report['driver_asset_id']='blocked-asset';self.bind()
        with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
            assert_motion_source_reusable(self.state,self.pack,'b'*64,'blocked-asset')

    def test_real_a101_style_qa_schema_blocks_exact_source_and_descendant(self):
        self.state['actions'][0]['id']='a101'
        self.report={'action_id':'a101','recommendation':'WITHDRAW_DO_NOT_RELEASE',
            'source_sha256':self.driver,'defects':[{'severity':'hard','type':'unapproved_foreground_appendage',
            'source_trace_frames':[80,88,96,104,112,120,128,136,144,152,160,168,176,180]}]}
        self.bind()
        self.state['diagnostic_attempts']=[{'status':'completed','task_id':'existing-paid-task',
            'source_sha256':'b'*64,'inputs':{'driver':{'sha256':self.driver}}}]
        before=copy.deepcopy(self.state)
        for source in [self.driver,'b'*64]:
            with self.assertRaisesRegex(ValueError,'anatomy-withdrawn'):
                assert_motion_source_reusable(self.state,self.pack,source)
        self.assertEqual(self.state,before)

    def test_qa_background_or_soft_appendage_without_withdrawal_is_not_anatomy_hold(self):
        self.report={'action_id':'a001','recommendation':'WITHDRAW_DO_NOT_RELEASE','source_sha256':self.driver,
            'defects':[{'severity':'hard','type':'background_failure'}]}
        self.bind();assert_motion_source_reusable(self.state,self.pack,self.driver)
        self.report['defects']=[{'severity':'soft','type':'unapproved_foreground_appendage'}]
        self.bind();assert_motion_source_reusable(self.state,self.pack,self.driver)
        self.report['defects'][0]['severity']='hard';self.report['recommendation']='RECHECK'
        self.bind();assert_motion_source_reusable(self.state,self.pack,self.driver)

    def test_both_schemas_reject_invalid_source_sha_or_wrong_action(self):
        for schema in ['green','qa']:
            self.report={'action_id':'a001','source_sha256':'z'*64}
            if schema=='green':self.report.update(classification='unapproved_foreground_appendage',withdraw_recommended=True)
            else:self.report.update(recommendation='WITHDRAW_DO_NOT_RELEASE',
                defects=[{'severity':'hard','type':'unapproved_foreground_appendage'}])
            self.bind()
            with self.assertRaisesRegex(ValueError,'bound original source SHA'):
                assert_motion_source_reusable(self.state,self.pack,self.driver)
            self.report.update(source_sha256=self.driver,action_id='a105');self.bind()
            with self.assertRaisesRegex(ValueError,'identity'):
                assert_motion_source_reusable(self.state,self.pack,self.driver)
