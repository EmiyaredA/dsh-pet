import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import kurisu_green_worker as worker


class U24MediaProfileTests(unittest.TestCase):
    def attempt(self):
        return {'task_id':'original-u24-task','result_asset_id':'original-u24-result',
            'model_id':worker.U24_MODEL_ID,'model_slug':worker.U24_MODEL_SLUG,
            'processing_profile':worker.U24_PROFILE}

    def fixture(self,folder):
        pack=Path(folder);raw=pack/'source/library/a064/attempt-1/pudding.mp4';raw.parent.mkdir(parents=True);raw.write_bytes(b'known-u24-source')
        return pack,raw,{'id':'a064','name':'pudding'},self.attempt()

    def test_only_exact_u24_profile_identity_allowed_and_default_unchanged(self):
        t=self.attempt();self.assertEqual(worker.processing_profile(t),worker.U24_PROFILE)
        self.assertEqual(worker.processing_profile({}),'h3_bounded_palette')
        for change in [{'model_id':worker.WAN_MODEL_ID},{'model_slug':worker.WAN_MODEL_SLUG},
                       {'processing_profile':worker.WAN_PROFILE},{'processing_profile':'unknown'},
                       {'processing_profile':[]}]:
            with self.subTest(change=change),self.assertRaises(ValueError):worker.processing_profile({**t,**change})

    def test_allowed_u24_uses_normal_green_only_and_its_own_version(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a,t=self.fixture(folder);before=copy.deepcopy((a,t))
            def create(source,output,*args):
                Path(output).write_bytes(b'new-alpha-candidate');return {'verification':{'frames':240}}
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                 patch.object(worker,'require_ten_seconds_video',return_value={'video_duration_seconds':10.125}) as timing,\
                 patch.object(worker,'scan_green_source',return_value={'passed':True}) as scan,\
                 patch.object(worker,'load_source_review',return_value={'processing_clearance':worker.ALLOW}) as review,\
                 patch.object(worker,'normal_u24_green_candidate',side_effect=create) as normal,\
                 patch.object(worker,'normal_green_candidate') as wan,patch.object(worker,'green_candidate') as palette:
                result=worker.process_snapshot(object(),a,t,1,'u24-claim-token')
            normal.assert_called_once();wan.assert_not_called();palette.assert_not_called();scan.assert_called_once_with(raw)
            timing.assert_called_once_with(raw,source_label='H3 U24')
            review.assert_called_once_with(pack,'a064',1,hashlib.sha256(b'known-u24-source').hexdigest())
            self.assertEqual(result['action_status'],'awaiting_review');self.assertEqual((a,t),before)
            self.assertEqual(result['attempt_patch']['worker_version'],worker.U24_WORKER_VERSION)
            self.assertEqual(result['attempt_patch']['processing_profile'],worker.U24_PROFILE)

    def test_u24_profile_never_bypasses_background_or_independent_source_gate(self):
        cases=[(False,worker.ALLOW,'processing_failed'),(True,'reject','processing_failed'),
               (True,'pending','awaiting_source_review')]
        for bg,clearance,status in cases:
            with self.subTest(bg=bg,clearance=clearance),tempfile.TemporaryDirectory() as folder:
                pack,raw,a,t=self.fixture(folder)
                with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                     patch.object(worker,'require_ten_seconds_video',return_value={'video_duration_seconds':10.125}),\
                     patch.object(worker,'scan_green_source',return_value={'passed':bg}),\
                     patch.object(worker,'load_source_review',return_value={'processing_clearance':clearance}),\
                     patch.object(worker,'normal_u24_green_candidate') as convert:
                    result=worker.process_snapshot(object(),a,t,1,'u24-claim-token')
                convert.assert_not_called();self.assertEqual(result['action_status'],status)
                self.assertNotIn('candidate_file',result['attempt_patch'])

    def test_short_u24_source_rejected_before_scan_or_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a,t=self.fixture(folder)
            with patch.object(worker,'PACK',pack),\
                 patch.object(worker,'require_ten_seconds_video',side_effect=ValueError('H3 U24 source video is shorter than10seconds')),\
                 patch.object(worker,'scan_green_source') as scan,patch.object(worker.subprocess,'run') as run,\
                 patch.object(worker,'normal_u24_green_candidate') as convert:
                result=worker.process_snapshot(object(),a,t,1,'u24-claim-token')
            scan.assert_not_called();run.assert_not_called();convert.assert_not_called()
            self.assertIn('H3 U24',result['attempt_patch']['processing_error'])

    def test_u24_ordinary_convert_has_no_palette_semantic_or_wan_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);src=p/'raw.mp4';src.write_bytes(b'raw');out=p/'candidate.webm'
            with patch.object(worker,'convert',return_value={'verification':{'frames':240}}) as convert,\
                 patch.object(worker,'estimate_track') as fit,patch.object(worker,'select_palette_anchor') as anchor:
                report=worker.normal_u24_green_candidate(src,out,p/'work',{'video_duration_seconds':10.125})
            convert.assert_called_once_with(src,out,'ffmpeg','ffprobe',p/'work',False,lossless=True)
            fit.assert_not_called();anchor.assert_not_called()
            meta=report['green_source_processing'];self.assertEqual(meta['worker_version'],worker.U24_WORKER_VERSION)
            self.assertEqual(meta['processing_profile'],worker.U24_PROFILE);self.assertNotEqual(meta['worker_version'],worker.WAN_WORKER_VERSION)
            self.assertFalse(meta['global_palette_fitting']);self.assertFalse(meta['white_classifier_used']);self.assertFalse(meta['semantic_segmentation_used'])
            self.assertEqual(json.loads(out.with_suffix('.report.json').read_text()),report)


if __name__=='__main__':unittest.main()
