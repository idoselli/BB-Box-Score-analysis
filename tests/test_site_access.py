import re
import unittest
from unittest.mock import patch

import web_tool
from site_access import COOKIE, MAX_AGE, _signer


class LandingPageTests(unittest.TestCase):
    def test_root_lands_on_new_site_and_legacy_remains_available(self):
        client = web_tool.app.test_client()
        response = client.get('/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.location,'/beta/')
        home = client.get('/',follow_redirects=True)
        self.assertEqual(home.status_code,200)
        self.assertIn(b'Open Match Analysis',home.data)
        self.assertIn(b'/legacy/',home.data)
        self.assertEqual(client.get('/legacy/').status_code,200)

    def test_match_analysis_is_primary_mode_before_secondary_tools(self):
        html=web_tool.app.test_client().get('/beta/').data.decode()
        self.assertLess(html.index('match-analysis-title'),html.index('more-tools-title'))
        self.assertIn('class="button hero-cta"',html)
        self.assertIn('href="/beta/multi-match"',html)


class SiteAccessTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict('os.environ',{'NIKA_SITE_PASSWORD':'local-test-only-password'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client=web_tool.app.test_client()

    def csrf(self,path='/'):
        response=self.client.get(path)
        self.assertEqual(response.status_code,401)
        return re.search(rb'name="csrf" value="([^"]+)"',response.data).group(1).decode()

    def login(self,password='local-test-only-password',destination='/beta/multi-match'):
        csrf=self.csrf()
        return self.client.post('/access',data={'csrf':csrf,'password':password,'next':destination})

    def test_every_page_blocked_before_authentication_or_report_work(self):
        with patch('beta_v1.auth.current_session',side_effect=AssertionError('Protected handler ran')):
            for path in ['/','/beta/','/beta/multi-match','/legacy/','/beta/oauth/start?feature=public','/beta/oauth/callback?code=test&state=test']:
                response=self.client.get(path)
                self.assertEqual(response.status_code,401,path)
                self.assertIn(b'role="dialog"',response.data)
                self.assertIn(b'inert aria-hidden="true"',response.data)
                self.assertNotIn(b'/_vercel/insights/script.js',response.data)
                self.assertNotIn(b'local-test-only-password',response.data)

    def test_api_and_exports_are_blocked_server_side(self):
        for path in ['/beta/api/market/archive','/api/u21-tracker?season=73']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.json['error'],'SiteAccessRequired')
        response=self.client.post('/beta/export-multi',json={'report':{'world':'v1','matches':[]},'format':'json'})
        self.assertEqual(response.status_code,401)

    def test_correct_password_unlocks_all_routes_and_resumes_destination(self):
        response=self.login()
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.location,'/beta/multi-match')
        cookie=self.client.get_cookie(COOKIE)
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site,'Lax')
        self.assertNotIn('local-test-only-password',cookie.value)
        self.assertEqual(self.client.get('/beta/multi-match').status_code,200)
        self.assertEqual(self.client.get('/legacy/').status_code,200)
        self.assertEqual(self.client.get('/beta/api/market/archive').status_code,200)

    def test_background_requests_do_not_invalidate_open_form(self):
        csrf=self.csrf()
        self.client.get('/favicon.ico')
        response=self.client.post('/access',data={'csrf':csrf,'password':'local-test-only-password'})
        self.assertEqual(response.status_code,303)

    def test_wrong_password_stays_locked(self):
        response=self.login('wrong')
        self.assertEqual(response.status_code,401)
        self.assertIn(b'Incorrect password',response.data)
        self.assertIsNone(self.client.get_cookie(COOKIE))

    def test_post_requires_matching_csrf_cookie(self):
        response=self.client.post('/access',data={'csrf':'fake','password':'local-test-only-password'})
        self.assertEqual(response.status_code,403)
        self.assertIsNone(self.client.get_cookie(COOKIE))

    def test_unicode_csrf_is_rejected_without_server_error(self):
        self.csrf()
        response=self.client.post('/access',data={'csrf':'nonascii-\u05d0','password':'local-test-only-password'})
        self.assertEqual(response.status_code,403)

    def test_tampered_and_expired_cookies_cannot_bypass_gate(self):
        self.client.set_cookie(COOKIE,'forged')
        self.assertEqual(self.client.get('/beta/').status_code,401)
        with patch('itsdangerous.timed.time.time',return_value=1000):
            token=_signer().dumps('allowed')
        self.client.set_cookie(COOKIE,token)
        with patch('itsdangerous.timed.time.time',return_value=1000+MAX_AGE+1):
            self.assertEqual(self.client.get('/beta/').status_code,401)

    def test_password_rotation_invalidates_old_access(self):
        self.login()
        with patch.dict('os.environ',{'NIKA_SITE_PASSWORD':'changed-password'}):
            self.assertEqual(self.client.get('/beta/').status_code,401)

    def test_no_external_redirect_after_unlock(self):
        for destination in ['https://example.com','//example.com','/\\example.com','/access']:
            response=self.login(destination=destination)
            self.assertEqual(response.location,'/')
            self.client.delete_cookie(COOKIE)

    def test_production_cookie_is_secure(self):
        csrf=self.csrf()
        with patch.dict('os.environ',{'VERCEL':'1'}):
            response=self.client.post('/access',data={'csrf':csrf,'password':'local-test-only-password'})
        self.assertIn('Secure',response.headers['Set-Cookie'])

    def test_gated_content_is_never_publicly_cached(self):
        locked=self.client.get('/')
        self.assertIn('no-store',locked.headers['Cache-Control'])
        self.assertIn('Cookie',locked.headers['Vary'])
        self.login()
        self.assertIn('no-store',self.client.get('/beta/').headers['Cache-Control'])

    def test_static_assets_available_for_blurred_preview(self):
        with self.client.get('/static/site-access.css') as response:
            self.assertEqual(response.status_code,200)


if __name__=='__main__':
    unittest.main()
