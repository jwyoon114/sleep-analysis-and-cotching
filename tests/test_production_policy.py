import os
import unittest
from unittest.mock import patch
from production_policy import check_configuration, require_registration_consent


class ProductionPolicyTests(unittest.TestCase):
    def test_startup_rejects_missing_or_unsafe_configuration(self):
        valid = dict(DALJAM_ENV='production', DALJAM_DEMO_ONLY='0',
                     DALJAM_PUBLIC_ORIGIN='https://daljam.onrender.com',
                     DALJAM_BACKUP_POLICY='render-pitr-7d-v1')
        check_configuration(valid)
        for key in valid:
            with self.assertRaises(ValueError):
                check_configuration({k: v for k, v in valid.items() if k != key})
        for value in ('http://daljam.onrender.com', 'https://user:password@example.com', 'https://example.com/?x=1'):
            with self.assertRaises(ValueError):
                check_configuration(valid | {'DALJAM_PUBLIC_ORIGIN': value})

    def test_consent_requires_two_explicit_choices_and_current_version(self):
        with patch.dict(os.environ, {'DALJAM_ENV': 'production'}):
            require_registration_consent(True, True, '2026-11-12-v1', True, True)
            for consent in ((False, True, '2026-11-12-v1'), (True, False, '2026-11-12-v1'), (True, True, 'old')):
                with self.assertRaises(ValueError):
                    require_registration_consent(*consent, True, True)
            with self.assertRaises(ValueError):
                require_registration_consent(True, True, '2026-11-12-v1', False, True)
            with self.assertRaises(ValueError):
                require_registration_consent(True, True, '2026-11-12-v1', True, False)
