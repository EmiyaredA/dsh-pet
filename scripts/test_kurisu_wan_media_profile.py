import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import kurisu_green_worker as worker

class WanMediaProfileTests(unittest.TestCase):
    def meta(self,duration='10.125',audio=True):
        return {'streams':[{'codec_type':'video','duration':duration}]+([{'codec_type':'audio','duration':'30'}] if audio else []),'format':{'duration':'30'}}
    def attempt(self):
        return {'task_id':'existing-wan-task','result_asset_id':'existing-result','model_id':worker.WAN_MODEL_ID,'model_slug':worker.WAN_MODEL_SLUG,'processing_profile':worker.WAN_PROFILE}
    def setup_source(self,folder):
        pack=Path(folder);raw=pack/'source/library/a026/attempt-2/brush.mp4';raw.parent.mkdir(parents=True);raw.write_bytes(b'original-wan-source');return pack,raw,{'id':'a026','name':'brush'}
    def test_short_video_is_not_padded_by_long_audio(self):
        with patch.object(worker.subprocess,'check_output',return_value=json.dumps(self.meta('8.5')).encode()):
            with self.assertRaisesRegex(ValueError,'shorter'):worker.require_ten_seconds_video('source')
    def test_valid_video_stream_duration_overrides_long_audio(self):
        with patch.object(worker.subprocess,'check_output',return_value=json.dumps(self.meta()).encode()):
            result=worker.require_ten_seconds_video('source')
        self.assertEqual(result['video_duration_seconds'],10.125)
        self.assertEqual(result['duration_basis'],'video_stream_duration')
    def test_unknown_video_duration_with_audio_cannot_use_container(self):
        with patch.object(worker.subprocess,'check_output',return_value=json.dumps(self.meta('N/A')).encode()):
            with self.assertRaisesRegex(ValueError,'independently'):worker.require_ten_seconds_video('source')
    def test_frame_count_fallback_proves_duration_without_audio_padding(self):
        meta=self.meta('N/A');meta['streams'][0].update(nb_frames='243',avg_frame_rate='24/1')
        with patch.object(worker.subprocess,'check_output',return_value=json.dumps(meta).encode()):
            self.assertEqual(worker.require_ten_seconds_video('source')['video_duration_seconds'],10.125)
    def test_invalid_profile_cannot_route_h3_into_wan_no_palette(self):
        t=self.attempt();t['model_id']='h3-model'
        with self.assertRaisesRegex(ValueError,'mismatched'):worker.processing_profile(t)
        self.assertEqual(worker.processing_profile({}),'h3_bounded_palette')
    def test_short_wan_stops_before_normalization_and_keying(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a=self.setup_source(folder)
            with patch.object(worker,'PACK',pack),patch.object(worker.subprocess,'check_output',return_value=json.dumps(self.meta('8.5')).encode()),patch.object(worker.subprocess,'run') as run,patch.object(worker,'scan_green_source') as scan,patch.object(worker,'normal_green_candidate') as normal,patch.object(worker,'green_candidate') as palette:
                result=worker.process_snapshot(object(),a,self.attempt(),2,'short-token')
            run.assert_not_called();scan.assert_not_called();normal.assert_not_called();palette.assert_not_called();self.assertIn('shorter',result['attempt_patch']['processing_error'])
    def test_motion_driver_clearance_does_not_allow_new_output(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a=self.setup_source(folder)
            with patch.object(worker,'PACK',pack),patch.object(worker,'require_ten_seconds_video',return_value={'video_duration_seconds':10.125}),patch.object(worker.subprocess,'run'),patch.object(worker,'scan_green_source',return_value={'passed':True}),patch.object(worker,'normal_green_candidate') as normal:
                result=worker.process_snapshot(object(),a,self.attempt(),2,'pending-token')
            normal.assert_not_called();self.assertEqual(result['action_status'],'awaiting_source_review')
    def test_allowed_new_output_uses_normal_key_never_palette(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a=self.setup_source(folder)
            def make(source,out,work,timing):out.write_bytes(b'candidate');return {'normal_green_key':True}
            with patch.object(worker,'PACK',pack),patch.object(worker,'require_ten_seconds_video',return_value={'video_duration_seconds':10.125}),patch.object(worker.subprocess,'run'),patch.object(worker,'scan_green_source',return_value={'passed':True}),patch.object(worker,'load_source_review',return_value={'processing_clearance':worker.ALLOW}),patch.object(worker,'normal_green_candidate',side_effect=make) as normal,patch.object(worker,'green_candidate') as palette:
                result=worker.process_snapshot(object(),a,self.attempt(),2,'allowed-token')
            normal.assert_called_once();palette.assert_not_called();self.assertEqual(result['action_status'],'awaiting_review');self.assertEqual(result['attempt_patch']['processing_method'],worker.WAN_WORKER_VERSION)
    def test_failed_native_green_still_rejects_wan(self):
        with tempfile.TemporaryDirectory() as folder:
            pack,raw,a=self.setup_source(folder)
            with patch.object(worker,'PACK',pack),patch.object(worker,'require_ten_seconds_video',return_value={'video_duration_seconds':10.125}),patch.object(worker.subprocess,'run'),patch.object(worker,'scan_green_source',return_value={'passed':False}),patch.object(worker,'normal_green_candidate') as normal:
                result=worker.process_snapshot(object(),a,self.attempt(),2,'background-token')
            normal.assert_not_called();self.assertTrue(result['hard_defect']);self.assertEqual(result['defect_kind'],'background')
    def test_normal_key_preserves_existing_converter_endpoint_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'out.webm'
            with patch.object(worker,'convert',side_effect=ValueError('Neutral endpoints change size/baseline')) as convert:
                with self.assertRaisesRegex(ValueError,'endpoints'):worker.normal_green_candidate(Path(folder)/'raw.mp4',out,Path(folder)/'work',{'video_duration_seconds':10.125})
            self.assertEqual(convert.call_args.kwargs,{'lossless':True});self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
