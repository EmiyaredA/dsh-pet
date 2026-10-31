import copy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import kurisu_library as lib
import kurisu_queue as queue
from kurisu_submission_errors import safe_submission_error
from test_kurisu_queue import Client,action
import test_kurisu_queue as fixtures


class ApiFailure(Exception):
    def __init__(self):
        super().__init__('素材不能引用自身')
        self.status=422;self.code='self_asset_reference'
        self.problem={'detail':{'code':self.code,'message':'素材不能引用自身'},
                      'headers':{'Authorization':'Bearer never-save-this'},
                      'current':{'session_secret':'never-save-current'}}


class ErrorTests(unittest.TestCase):
    def test_sdk_status_and_nested_message_are_kept_without_private_snapshots(self):
        result=safe_submission_error(ApiFailure())
        self.assertEqual(result['http_status'],422);self.assertEqual(result['code'],'self_asset_reference')
        self.assertEqual(result['message'],'素材不能引用自身')
        self.assertNotIn('never-save',str(result));self.assertNotIn('headers',result)

    def test_messages_strip_credentials_and_url_query(self):
        e=ApiFailure();e.problem['message']='Authorization: Bearer super-secret api_key=abc123 cookie="session=secret" https://user:password@example.com/v1/task?token=hello'
        result=safe_submission_error(e)
        for secret in ['super-secret','abc123','session=secret','user:password','token=hello']:
            self.assertNotIn(secret,result['message'])
        self.assertIn('example.com/v1/task',result['message'])

    def test_httpx_status_fallback_and_message_length_are_bounded(self):
        e=ValueError('x'*5000);e.response=NS(status_code=503)
        result=safe_submission_error(e)
        self.assertEqual(result['http_status'],503);self.assertLessEqual(len(result['message']),2000)


class QueueErrorTests(unittest.TestCase):
    setUp=fixtures.QueueTests.setUp
    tearDown=fixtures.QueueTests.tearDown
    save=fixtures.QueueTests.save
    def test_rejected_response_details_are_saved_but_attempt_is_never_auto_released(self):
        self.save([action(1)]);client=Client()
        with patch.object(client,'create_generation_task',side_effect=ApiFailure()) as create:
            queue.submit_one(client)
            s=lib.load();t=s['actions'][0]['attempts'][0]
            self.assertEqual(t['submission_error']['http_status'],422)
            self.assertEqual(t['submission_error']['code'],'self_asset_reference')
            self.assertNotIn('never-save',str(t['submission_error']))
            self.assertEqual(s['actions'][0]['status'],'submission_uncertain')
            self.assertEqual(lib.calls(s),1)
            self.assertFalse(queue.submit_one(client));self.assertEqual(create.call_count,1)


if __name__=='__main__':unittest.main()
