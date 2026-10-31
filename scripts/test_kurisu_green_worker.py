import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import kurisu_green_worker as worker
from repair_kurisu_palette import IDENTITY
from green_edge_despill import despill_auburn_collar


class GreenWorkerTests(unittest.TestCase):
    def test_normal_green_edge_despill_keeps_alpha_skin_eyes_and_lace(self):
        rgba=np.zeros((3,6,4),np.uint8)
        rgba[1,1:5]=[[150,128,65,255],[250,210,180,255],[80,105,180,255],[242,242,244,255]]
        result,report=despill_auburn_collar(rgba)
        self.assertLess(int(result[1,1,1]),100)
        np.testing.assert_array_equal(result[...,3],rgba[...,3])
        np.testing.assert_array_equal(result[1,2:5],rgba[1,2:5])
        self.assertFalse(report['alpha_changed'])

    def fixture(self):
        rgb=np.full((160,240,3),(84,250,90),np.uint8)
        rgb[20:145,80:160]=[145,65,50]
        rgb[25:40,95:145]=[240,240,242]
        rgb[65:80,98:110]=[75,100,180]
        rgb[85:110,100:140]=[250,231,220]
        rgb[115:135,100:140]=[50,48,52]
        return rgb

    def test_connected_green_backdrop_clears_low_chroma_background_without_skin_masks(self):
        rgb=self.fixture();rgb[40:80,10:40]=[100,155,105]
        rgb[45:55,120:130]=[84,250,90]  # enclosed real negative space
        matte=worker.ConnectedGreenMatte(np.array([IDENTITY]))
        rgba=matte(rgb,0)
        self.assertEqual(int(rgba[50,20,3]),0)
        self.assertEqual(int(rgba[50,125,3]),0)
        for y,x in [(30,110),(70,104),(95,120),(125,120)]:
            self.assertEqual(int(rgba[y,x,3]),255)
        np.testing.assert_array_equal(rgba[70,104,:3],rgb[70,104])
        np.testing.assert_array_equal(rgba[95,120,:3],rgb[95,120])

    def test_large_palette_correction_is_rejected_instead_of_repainting(self):
        frames=np.array([self.fixture()]);track=np.array([IDENTITY.copy()]);track[0,3]=[0,.15,0]
        with self.assertRaisesRegex(ValueError,'matrix/offset'):
            worker.bound_palette_track(frames,track)
        track=np.array([IDENTITY.copy()]);track[0,3]=[0,-.09,0]
        with self.assertRaisesRegex(ValueError,'not mild'):
            worker.bound_palette_track(frames,track)

    def test_identity_palette_is_mild_and_does_not_warp_geometry(self):
        result=worker.bound_palette_track(np.array([self.fixture()]),np.array([IDENTITY]))
        self.assertFalse(result['geometry_warped'])
        self.assertFalse(result['individual_face_skin_eye_edits'])

    def source_case(self,folder):
        pack=Path(folder);raw=pack/'source/library/a010/attempt-5/jog.mp4';raw.parent.mkdir(parents=True);raw.write_bytes(b'known-source')
        a={'id':'a010','name':'jog'};t={'task_id':'existing-paid-task','result_asset_id':'existing-result'}
        return pack,raw,a,t

    def test_missing_source_review_never_converts_or_mutates_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a,t=self.source_case(folder);before=copy.deepcopy((a,t))
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                 patch.object(worker,'scan_green_source',return_value={'passed':True}),\
                 patch.object(worker,'green_candidate') as convert:
                result=worker.process_snapshot(object(),a,t,5,'claim-token-123')
            convert.assert_not_called();self.assertEqual((a,t),before)
            self.assertEqual(result['action_status'],'awaiting_source_review')
            self.assertEqual(result['attempt_patch']['source_sha256'],hashlib.sha256(b'known-source').hexdigest())
            self.assertEqual(result['task_id'],'existing-paid-task')

    def test_explicit_source_hard_rejection_never_enters_media_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a,t=self.source_case(folder)
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                 patch.object(worker,'scan_green_source',return_value={'passed':True}),\
                 patch.object(worker,'load_source_review',return_value={'processing_clearance':'reject','reason':'green spot on forehead'}),\
                 patch.object(worker,'green_candidate') as convert:
                result=worker.process_snapshot(object(),a,t,5,'claim-token-123')
            convert.assert_not_called();self.assertTrue(result['hard_defect'])
            self.assertEqual(result['action_status'],'processing_failed')

    def test_failed_green_background_cannot_use_white_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a,t=self.source_case(folder)
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                 patch.object(worker,'scan_green_source',return_value={'passed':False}),\
                 patch.object(worker,'green_candidate') as convert:
                result=worker.process_snapshot(object(),a,t,5,'claim-token-123')
            convert.assert_not_called();self.assertTrue(result['hard_defect'])
            self.assertIn('saturated green',result['attempt_patch']['processing_error'])

    def test_blue_native_scan_is_source_only_even_with_allowed_review(self):
        for passed in [True,False]:
            with self.subTest(passed=passed),tempfile.TemporaryDirectory() as folder:
                pack,raw,a,t=self.source_case(folder);t['chroma_background']='blue'
                with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                     patch.object(worker,'scan_source_background',return_value={'passed':passed}) as scan,\
                     patch.object(worker,'scan_green_source') as green_scan,\
                     patch.object(worker,'load_source_review',return_value={'processing_clearance':worker.ALLOW}),\
                     patch.object(worker,'green_candidate') as palette,\
                     patch.object(worker,'normal_green_candidate') as normal:
                    result=worker.process_snapshot(object(),a,t,5,'claim-token-123')
                scan.assert_called_once_with(raw,'blue');green_scan.assert_not_called()
                palette.assert_not_called();normal.assert_not_called()
                self.assertNotIn('candidate_file',result['attempt_patch'])
                self.assertTrue(result['attempt_patch']['blue_source_recovery_only'])
                self.assertEqual(result['action_status'],'awaiting_source_review' if passed else 'processing_failed')
                self.assertEqual(result['hard_defect'],not passed)

    def test_invalid_explicit_background_fails_before_download_or_scan(self):
        for chroma in ['white',None,[],123]:
            with self.subTest(chroma=chroma),tempfile.TemporaryDirectory() as folder:
                pack,raw,a,t=self.source_case(folder);t['chroma_background']=chroma
                with patch.object(worker,'PACK',pack),patch.object(worker,'scan_source_background') as scan,\
                     patch.object(worker,'scan_green_source') as green_scan,patch.object(worker.subprocess,'run') as run:
                    result=worker.process_snapshot(object(),a,t,5,'claim-token-123')
                scan.assert_not_called();green_scan.assert_not_called();run.assert_not_called()
                self.assertEqual(result['action_status'],'processing_failed')
                self.assertIn('Unsupported approved chroma',result['attempt_patch']['processing_error'])

    def test_interrupted_download_recovers_same_paid_asset_without_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=Path(folder);calls=[]
            class Files:
                def download_file(self,asset_id):
                    calls.append(asset_id)
                    failed=len(calls)==1
                    class Download:
                        def __enter__(self):return self
                        def __exit__(self,*args):return False
                        def save(self,path):
                            Path(path).write_bytes(b'partial' if failed else b'complete-source')
                            if failed:raise ConnectionError('interrupted transport')
                    return Download()
            class Generation:
                def create_generation_task(self,**kwargs):raise AssertionError('No model submission during download recovery')
            class Client:
                files=Files();generation=Generation()
            a={'id':'a026','name':'brush'};t={'task_id':'original-task','result_asset_id':'original-paid-asset'}
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'run'),\
                 patch.object(worker,'scan_green_source',return_value={'passed':True}):
                with self.assertRaises(ConnectionError):worker.process_snapshot(Client(),a,t,1,'first-claim-123')
                self.assertFalse((pack/'source/library/a026/attempt-1/brush.mp4').exists())
                result=worker.process_snapshot(Client(),a,t,1,'second-claim-123')
            self.assertEqual(calls,['original-paid-asset','original-paid-asset'])
            self.assertEqual(result['task_id'],'original-task')
            self.assertEqual(result['action_status'],'awaiting_source_review')
            self.assertEqual((pack/'source/library/a026/attempt-1/brush.mp4').read_bytes(),b'complete-source')


if __name__=='__main__':unittest.main()
