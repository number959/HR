import unittest

from support import PASSWORD, PortalCase
from wr import security


class FirstAccessAndLogin(PortalCase):
    def test_activation_creates_full_session_and_recovery_codes(self):
        self.assertEqual(len(self.admin.recovery), 10)
        me = self.admin.ok('GET', '/api/me')
        self.assertEqual(me['user']['role'], 'admin')
        self.assertTrue(me['caps']['utenti.gestisci'])
        state = self.admin.ok('GET', '/api/session')
        self.assertEqual(state['stage'], 'full')
        self.assertEqual(state['recovery_remaining'], 10)

    def test_activation_code_works_once(self):
        cid = self.portal.center()
        self.portal.step_up(self.admin)
        created = self.admin.ok('POST', '/api/users', {'username': 'compilatore', 'name': 'Compilatore', 'role': 'operator',
                                                       'centers': [cid]})
        self.portal.activate('compilatore', created['activation_code'])
        again = self.portal.client()
        again.ok('GET', '/api/session')
        self.assertStatus(again.post('/api/session/activation', {'username': 'compilatore',
                                                                 'activation': created['activation_code']}), 400)

    def test_login_requires_second_factor(self):
        c = self.portal.client()
        c.ok('GET', '/api/session')
        state = c.ok('POST', '/api/session/login', {'username': 'admin', 'password': PASSWORD})
        self.assertEqual(state['stage'], 'password')
        self.assertStatus(c.get('/api/me'), 401)
        self.assertStatus(c.post('/api/session/verify', {'code': '000000'}), 400)
        c.ok('POST', '/api/session/verify', {'code': self.portal.code('admin')})
        self.assertEqual(c.ok('GET', '/api/me')['user']['username'], 'admin')

    def test_wrong_password_is_generic_and_rate_limited(self):
        c = self.portal.client()
        c.ok('GET', '/api/session')
        for _ in range(5):
            self.assertStatus(c.post('/api/session/login', {'username': 'admin', 'password': 'sbagliata-davvero'}), 401,
                              'Nome utente o password non corretti')
        self.assertStatus(c.post('/api/session/login', {'username': 'admin', 'password': PASSWORD}), 429)
        self.portal.clock.advance(301)
        c.ok('POST', '/api/session/login', {'username': 'admin', 'password': PASSWORD})

    def test_unknown_user_same_message(self):
        c = self.portal.client()
        c.ok('GET', '/api/session')
        self.assertStatus(c.post('/api/session/login', {'username': 'nessuno', 'password': PASSWORD}), 401,
                          'Nome utente o password non corretti')

    def test_recovery_code_login_consumes_code(self):
        code = self.admin.recovery[0]
        for attempt in range(2):
            c = self.portal.client()
            c.ok('GET', '/api/session')
            c.ok('POST', '/api/session/login', {'username': 'admin', 'password': PASSWORD})
            response = c.post('/api/session/verify', {'code': code, 'recovery': True})
            self.assertEqual(response.status, 200 if attempt == 0 else 400)

    def test_totp_code_cannot_be_reused(self):
        c = self.portal.client()
        c.ok('GET', '/api/session')
        c.ok('POST', '/api/session/login', {'username': 'admin', 'password': PASSWORD})
        code = self.portal.code('admin')
        c.ok('POST', '/api/session/verify', {'code': code})
        d = self.portal.client()
        d.ok('GET', '/api/session')
        d.ok('POST', '/api/session/login', {'username': 'admin', 'password': PASSWORD})
        self.assertStatus(d.post('/api/session/verify', {'code': code}), 400)

    def test_logout_and_idle_expiry(self):
        c = self.portal.login('admin')
        self.portal.clock.advance(901)
        self.assertStatus(c.get('/api/me'), 401)
        c = self.portal.login('admin')
        c.ok('POST', '/api/session/logout')
        self.assertStatus(c.get('/api/me'), 401)


class RequestProtection(PortalCase):
    def test_write_requires_csrf_token_and_origin(self):
        c = self.admin
        token = c.csrf
        c.csrf = ''
        self.assertStatus(c.post('/api/session/step-up', {'password': PASSWORD, 'code': '123456'}), 403)
        c.csrf = token
        self.assertStatus(c.post('/api/session/step-up', {'password': PASSWORD, 'code': '123456'},
                                 headers={'Origin': 'https://altro-sito.example'}), 403)
        self.assertStatus(c.post('/api/session/step-up', {'password': PASSWORD, 'code': '123456'},
                                 headers={'Origin': None}), 403)
        self.assertStatus(c.get('/api/me', headers={'Host': 'altro:8080'}), 403)
        self.assertStatus(c.get('/api/me', headers={'Sec-Fetch-Site': 'cross-site'}), 403)

    def test_json_only_and_unknown_routes(self):
        response = self.admin.request('POST', '/api/session/step-up', raw=b'password=x', content_type='text/plain')
        self.assertStatus(response, 415)
        self.assertStatus(self.admin.get('/api/inesistente'), 404)
        self.assertStatus(self.admin.request('PATCH', '/api/me'), 405)

    def test_security_headers(self):
        response = self.admin.get('/api/me')
        headers = {k: v for k, v in response.headers}
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.admin.get('/health').data['product'], 'NefroCenter WR')


class StepUp(PortalCase):
    def test_sensitive_operation_requires_recent_confirmation(self):
        self.portal.clock.advance(301)
        response = self.admin.post('/api/centers', {'name': 'Centro Nord', 'code': 'NORD'})
        self.assertStatus(response, 428)
        self.portal.step_up(self.admin)
        self.admin.ok('POST', '/api/centers', {'name': 'Centro Nord', 'code': 'NORD'})
        self.portal.clock.advance(301)
        self.assertStatus(self.admin.post('/api/centers', {'name': 'Centro Sud', 'code': 'SUD'}), 428)

    def test_step_up_wrong_password(self):
        self.assertStatus(self.admin.post('/api/session/step-up', {'password': 'non-è-questa', 'code': '000000'}), 400)


class AccountAdministration(PortalCase):
    def test_role_change_revokes_sessions(self):
        cid = self.portal.center()
        viewer = self.portal.user('lettore', 'viewer', [cid])
        users = self.admin.ok('GET', '/api/users')['users']
        target = next(u for u in users if u['username'] == 'lettore')
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', f'/api/users/{target["id"]}', {'name': 'Lettore', 'role': 'manager', 'centers': [cid],
                                                           'active': True, 'version': target['version']})
        self.assertStatus(viewer.get('/api/me'), 401)
        manager = self.portal.login('lettore')
        self.assertEqual(manager.ok('GET', '/api/me')['user']['role'], 'manager')

    def test_last_admin_cannot_be_removed(self):
        me = next(u for u in self.admin.ok('GET', '/api/users')['users'] if u['username'] == 'admin')
        self.portal.step_up(self.admin)
        response = self.admin.put(f'/api/users/{me["id"]}', {'name': 'Amministratore', 'role': 'hr', 'centers': [],
                                                             'active': True, 'version': me['version']})
        self.assertStatus(response, 400, 'almeno un amministratore')

    def test_reset_access_gives_new_activation(self):
        cid = self.portal.center()
        self.portal.user('mario', 'operator', [cid])
        target = next(u for u in self.admin.ok('GET', '/api/users')['users'] if u['username'] == 'mario')
        self.portal.step_up(self.admin)
        reset = self.admin.ok('POST', f'/api/users/{target["id"]}/activation', {'reason': 'Telefono smarrito dal dipendente'})
        c = self.portal.client()
        c.ok('GET', '/api/session')
        self.assertStatus(c.post('/api/session/login', {'username': 'mario', 'password': PASSWORD}), 403, 'non ancora attivato')
        self.portal.activate('mario', reset['activation_code'], password='Nuova-password-sicura')
        self.portal.login('mario', password='Nuova-password-sicura')

    def test_non_admin_cannot_manage_users(self):
        cid = self.portal.center()
        hr = self.portal.user('hrcentrale', 'hr')
        self.assertStatus(hr.get('/api/users'), 403)
        manager = self.portal.user('responsabile', 'manager', [cid])
        self.assertStatus(manager.post('/api/users', {'username': 'x123', 'name': 'X', 'role': 'admin', 'centers': []}), 403)


class OwnSecurity(PortalCase):
    def test_change_password_and_regenerate_codes(self):
        self.admin.ok('POST', '/api/security/password', {'current': PASSWORD, 'password': 'Un-altra-password-2026'})
        self.portal.login('admin', password='Un-altra-password-2026')
        self.portal.step_up(self.admin, password='Un-altra-password-2026')
        codes = self.admin.ok('POST', '/api/security/recovery-codes')['recovery_codes']
        self.assertEqual(len(codes), 10)
        self.assertNotEqual(codes, self.admin.recovery)

    def test_rotate_authenticator(self):
        self.portal.step_up(self.admin)
        setup = self.admin.ok('POST', '/api/security/authenticator/start')
        self.portal.clock.advance(31)
        code = security.totp_code(setup['secret'], int(self.portal.clock() // 30))
        self.admin.ok('POST', '/api/security/authenticator/confirm', {'code': code})
        self.portal.secrets['admin'] = setup['secret']
        self.portal.login('admin')


if __name__ == '__main__':
    unittest.main()
