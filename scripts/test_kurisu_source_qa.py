import json
from pathlib import Path
import tempfile
import unittest
from kurisu_source_qa import ALLOW,load_source_review,source_review_path


class SourceQATests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.pack=Path(self.temp.name);self.sha='a'*64
        self.report={'action_id':'a010','attempt_index':5,'source_sha256':self.sha,'visual_review_performed':True,'reviewer':'independent-animation-qa','reviewed_at':'2026-10-30T13:00:00Z','processing_clearance':ALLOW,'defects':[]}
    def write(self):
        path=source_review_path(self.pack,'a010',5);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(self.report))
    def test_missing_or_different_hash_requires_source_review_without_implying_generation_failure(self):
        self.assertEqual(load_source_review(self.pack,'a010',5,self.sha)['processing_clearance'],'pending')
        self.write();result=load_source_review(self.pack,'a010',5,'b'*64)
        self.assertEqual(result['processing_clearance'],'pending');self.assertEqual(result['review_status'],'stale_or_mismatched')
    def test_deliberate_visual_clearance_is_only_for_processing_not_final_media_approval(self):
        self.write();result=load_source_review(self.pack,'a010',5,self.sha)
        self.assertEqual(result['processing_clearance'],ALLOW);self.assertFalse(result['final_media_approved'])
        self.report['visual_review_performed']=False;self.write()
        self.assertEqual(load_source_review(self.pack,'a010',5,self.sha)['processing_clearance'],'pending')
    def test_explicit_hard_defect_overrides_accidental_allow_label(self):
        self.report['defects']=[{'severity':'hard','description':'Green light crosses the iris'}];self.write()
        self.assertEqual(load_source_review(self.pack,'a010',5,self.sha)['processing_clearance'],'reject')
    def test_reviewer_can_reject_an_otherwise_well_formed_source(self):
        self.report['processing_clearance']='reject';self.write()
        self.assertEqual(load_source_review(self.pack,'a010',5,self.sha)['processing_clearance'],'reject')


if __name__=='__main__':unittest.main()
