import os
import unittest
from unittest.mock import patch
from production_policy import check_configuration, require_registration_consent, backup_policy_ready


class ProductionPolicyTests(unittest.TestCase):
    def test_startup_rejects_missing_or_unsafe_configuration(self):
        valid = dict(DALJAM_ENV='production', DALJAM_DEMO_ONLY='0',
                     DALJAM_PUBLIC_ORIGIN='https://daljam.onrender.com',
                     DALJAM_BACKUP_POLICY='render-pitr-3d-v1')
        check_configuration(valid)
        for key in valid:
            with self.assertRaises(ValueError):
                check_configuration({k: v for k, v in valid.items() if k != key})
        for value in ('http://daljam.onrender.com', 'https://user:password@example.com', 'https://example.com/?x=1'):
            with self.assertRaises(ValueError):
                check_configuration(valid | {'DALJAM_PUBLIC_ORIGIN': value})

        for policy in ('render-pitr-7d-v1', 'render-pitr-3d', '', 'unknown'):
            with self.assertRaises(ValueError):
                check_configuration(valid | {'DALJAM_BACKUP_POLICY': policy})

    def test_backup_notice_distinguishes_pitr_from_exports_and_rejects_stale_policy(self):
        from backup_policy import maintain_backups
        with patch('app_database.uses_postgres', return_value=True):
            with patch.dict(os.environ, {'DALJAM_BACKUP_POLICY': 'render-pitr-3d-v1'}):
                self.assertTrue(backup_policy_ready())
                status = maintain_backups()
                self.assertEqual(status['pitr_retention_days'], 3)
                self.assertEqual(status['managed_export_retention_days'], 7)
                self.assertEqual(status['retention_days'], 7)
                self.assertFalse(status['pending'])
            with patch.dict(os.environ, {'DALJAM_BACKUP_POLICY': 'render-pitr-7d-v1'}):
                self.assertFalse(backup_policy_ready())
                self.assertTrue(maintain_backups()['pending'])

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
