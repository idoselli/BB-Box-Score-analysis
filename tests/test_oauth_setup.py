import unittest
from unittest.mock import patch

import web_tool
from beta_v1 import auth
from beta_v1.check_auth import main


class PublicSignInTests(unittest.TestCase):
    settings = {'BB_V1_CLIENT_ID': 'bbc_test', 'BB_V1_CLIENT_SECRET': 'bbcs_test',
                'BB_V1_REDIS_URL': 'rediss://test', 'BB_V1_TOKEN_ENCRYPTION_KEY': 'test'}

    def test_public_home_offers_oauth_without_personal_token_form(self):
        with patch.dict('os.environ', self.settings), patch.object(auth, 'current_session', return_value=None):
            response = web_tool.app.test_client().get('/beta/', base_url='https://box-score-analysis.vercel.app')
        self.assertIn(b'Sign in with BuzzerBeater', response.data)
        self.assertIn(b'/beta/oauth/start?feature=public', response.data)
        self.assertNotIn(b'name="api_token"', response.data)

    def test_hosted_token_login_refused_even_with_storage_and_local_headers(self):
        with patch.dict('os.environ', dict(self.settings, VERCEL='1', BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN='true')), web_tool.app.test_request_context('/beta/', environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertFalse(auth.token_signin_available())
            with self.assertRaises(RuntimeError):
                auth.sign_in_with_token('not-a-real-token')

    def test_signed_in_managers_can_request_optional_scopes(self):
        record = {'me': {'username': 'Manager'}, 'csrf': 'test'}
        with patch.dict('os.environ', self.settings), patch.object(auth, 'current_session', return_value=(object(), record)):
            response = web_tool.app.test_client().get('/beta/', base_url='https://box-score-analysis.vercel.app')
        for feature in ['training', 'national', 'market']:
            self.assertIn(('feature=' + feature).encode(), response.data)
        self.assertNotIn(b'name="api_token"', response.data)

    def test_setup_checker_names_missing_keys_without_disclosing_values(self):
        with patch.dict('os.environ', {'BB_V1_CLIENT_SECRET': 'hidden-secret'}, clear=True), patch('builtins.print') as output:
            self.assertEqual(main(), 1)
        message = str(output.call_args)
        self.assertIn('BB_V1_CLIENT_ID', message)
        self.assertNotIn('hidden-secret', message)


if __name__ == '__main__':
    unittest.main()
