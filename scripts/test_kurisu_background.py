from io import BytesIO
import json
import subprocess
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import kurisu_background as bg
import kurisu_library as lib
import kurisu_green_worker as worker


class Process:
    def __init__(self,data,code=0,chunk=None):
        class Stream(BytesIO):
            def read(self,n=-1):return super().read(min(n,chunk) if chunk else n)
        self.stdout=Stream(data);self.code=code;self.killed=False;self.waited=False
    def wait(self):self.waited=True;return self.code
    def poll(self):return self.code if self.waited or self.killed else None
    def kill(self):self.killed=True


class BackgroundTests(unittest.TestCase):
    def repeated(self,frame,n=240):return np.broadcast_to(frame,(n,*frame.shape))
    def test_native_green_border_does_not_mix_shoes_eight_pixels_from_bottom(self):
        native=np.full((464,832,3),(0,255,0),np.uint8)
        native[404:456,200:650]=(10,10,15)  # Eight intact background rows remain.
        actual=bg.evaluate_native_frames(self.repeated(native))
        proxy=cv2.resize(native,(64,36),interpolation=cv2.INTER_AREA)
        legacy=bg.evaluate_native_frames(self.repeated(proxy))
        self.assertTrue(actual['passed']);self.assertFalse(legacy['passed'])
        self.assertEqual(actual['method'],'all_frame_saturated_green_native_border_v2')
        self.assertEqual(actual['thresholds']['spatial_delta_max'],35)

    def test_real_outer_white_black_blue_and_dim_pixels_are_rejected(self):
        for bad in [(255,255,255),(0,0,0),(0,0,255),(0,179,0),(150,255,150),(100,180,100)]:
            with self.subTest(pixel=bad):
                frame=np.full((32,64,3),(0,255,0),np.uint8);frame[-1,30]=bad
                report=bg.evaluate_native_frames(self.repeated(frame))
                self.assertFalse(report['passed']);self.assertEqual(report['failed_frame_count'],240)
        self.assertFalse(bg.evaluate_native_frames(self.repeated(np.full((32,64,3),(0,150,0),np.uint8)))['passed'])

    def test_spatial_35_and_temporal_24_thresholds_are_not_relaxed(self):
        for delta,expected in [(35,True),(36,False)]:
            frame=np.full((8,16,3),(0,255,0),np.uint8);frame[-1,7]=(delta,255,0)
            self.assertEqual(bg.evaluate_native_frames(self.repeated(frame))['passed'],expected)
        for delta,expected in [(24,True),(25,False)]:
            frames=np.full((240,8,16,3),(0,255,0),np.uint8);frames[-1]=(0,255-delta,0)
            report=bg.evaluate_native_frames(frames)
            self.assertEqual(report['passed'],expected)
            if not expected:self.assertEqual(report['failed_frames'],[239])

    def test_missing_extra_or_empty_frames_cannot_pass(self):
        frame=np.full((8,16,3),(0,255,0),np.uint8)
        for n in [1,239,241]:self.assertFalse(bg.evaluate_native_frames(self.repeated(frame,n))['passed'])
        with self.assertRaises(ValueError):bg.evaluate_native_frames(self.repeated(frame,0))

    def test_native_gate_does_not_certify_enclosed_white_islands_or_foreground(self):
        frame=np.full((32,64,3),(0,255,0),np.uint8);frame[5:28,15:45]=(255,255,255)
        report=bg.evaluate_native_frames(self.repeated(frame))
        self.assertTrue(report['passed']);self.assertTrue(report['visual_foreground_review_required'])
        self.assertFalse(report['enclosed_background_and_foreground_verified'])
        self.assertFalse(report['white_matte_fallback'])

    def test_decoder_streams_native_frames_with_no_spatial_resampling(self):
        rgb=np.full((240,4,8,3),(0,255,0),np.uint8);process=Process(rgb.tobytes(),chunk=7)
        with patch.object(bg.subprocess,'check_output',return_value=b'{"streams":[{"width":8,"height":4}]}'),\
             patch.object(bg.subprocess,'Popen',return_value=process) as run:
            report=bg.scan_source_background('input.mp4')
        self.assertTrue(report['passed']);self.assertEqual(report['native_size'],[8,4])
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-vf')+1],'fps=24')
        self.assertEqual(command[command.index('-t')+1],'10')
        self.assertNotIn('scale',','.join(command));self.assertIn('-xerror',command)
        self.assertTrue(process.stdout.closed)

    def test_partial_frame_or_decoder_error_cannot_be_accepted(self):
        for data,code,error in [(bytes(13),0,ValueError),(bytes(12),1,subprocess.CalledProcessError)]:
            process=Process(data,code)
            with patch.object(bg.subprocess,'check_output',return_value=b'{"streams":[{"width":2,"height":2}]}'),\
                 patch.object(bg.subprocess,'Popen',return_value=process):
                with self.assertRaises(error):bg.scan_source_background('broken.mp4')
            self.assertTrue(process.waited);self.assertTrue(process.stdout.closed)

    def test_library_and_media_worker_use_one_shared_native_scan(self):
        expected={'method':'all_frame_saturated_green_native_border_v2','passed':True}
        with patch.object(lib,'scan_source_background',return_value=expected) as scan:
            self.assertEqual(lib.source_green_background('source.mp4'),expected)
            scan.assert_called_once_with('source.mp4','green')
        with patch.object(worker,'scan_source_background',return_value=expected) as scan:
            self.assertEqual(worker.scan_green_source('source.mp4'),expected)
            scan.assert_called_once_with('source.mp4','green','ffmpeg','ffprobe')

    def test_blue_legacy_compatibility_preserves_original_channel_values(self):
        frames=self.repeated(np.full((8,16,3),(0,0,255),np.uint8))
        report=bg.evaluate_native_frames(frames,'blue')
        self.assertTrue(report['passed']);self.assertEqual(report['background_rgb_min'],[0,0,255])

    def test_legacy_proxy_is_explicitly_diagnostic_only(self):
        frames=np.full((240,36,64,3),(0,255,0),np.uint8)
        with patch.object(bg.subprocess,'check_output',return_value=frames.tobytes()):
            report=bg.legacy_proxy_source_background('original.mp4')
        self.assertTrue(report['legacy_proxy_diagnostic_only'])
        self.assertFalse(report['production_acceptance_authority'])
        self.assertEqual(report['method'],'all_frame_saturated_green_border_v1')


if __name__=='__main__':unittest.main()
