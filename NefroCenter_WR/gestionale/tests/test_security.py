import unittest

from support import PRODUCTION_ITERATIONS
from wr import security
from wr.errors import Invalid


class SecurityPrimitives(unittest.TestCase):
    def test_totp_matches_rfc_6238_vector(self):
        # RFC 6238, appendice B: segreto ASCII "12345678901234567890", t=59 s → 94287082 (8 cifre) → 287082.
        secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
        self.assertEqual(security.totp_code(secret, 59 // 30), '287082')
        self.assertEqual(security.totp_code(secret, 1111111109 // 30), '081804')

    def test_totp_window_and_replay(self):
        secret = security.new_totp_secret()
        now = 1_800_000_000
        step = int(now // 30)
        code = security.totp_code(secret, step)
        self.assertEqual(security.totp_match(secret, code, now), step)
        self.assertEqual(security.totp_match(secret, security.totp_code(secret, step - 1), now), step - 1)
        self.assertIsNone(security.totp_match(secret, security.totp_code(secret, step - 2), now))
        self.assertIsNone(security.totp_match(secret, code, now, last_step=step), 'un codice già usato non vale di nuovo')
        self.assertIsNone(security.totp_match(secret, '12345', now))
        self.assertIsNone(security.totp_match(secret, None, now))

    def test_password_policy_and_hash(self):
        self.assertEqual(PRODUCTION_ITERATIONS, 600_000)
        for bad in ('corta', 'a' * 257, 'aaaaaaaaaaaaaaaa', 'mario.rossi12'):
            with self.assertRaises(Invalid):
                security.hash_password(bad, 'mario.rossi12')
        stored = security.hash_password('Una frase lunga e sicura', 'mario')
        self.assertTrue(security.verify_password('Una frase lunga e sicura', stored))
        self.assertFalse(security.verify_password('Una frase lunga e sicurA', stored))
        self.assertFalse(security.verify_password('x', 'non json'))

    def test_recovery_codes(self):
        codes, hashes = security.new_recovery_codes()
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        normalized = security.normalize_recovery(codes[0].lower().replace('-', ' '))
        self.assertEqual(security.digest(normalized), hashes[0])
        self.assertIsNone(security.normalize_recovery('XXXX-1234'))

    def test_provisioning_uri_and_qr(self):
        uri = security.provisioning_uri('ABCDEF', 'mario')
        self.assertTrue(uri.startswith('otpauth://totp/NefroCenter%20WR%3Amario?secret=ABCDEF'))
        self.assertTrue(security.qr_svg_data_uri(uri).startswith('data:image/svg+xml'))


if __name__ == '__main__':
    unittest.main()
