"""Explicit public-service policy; desktop and synthetic tests remain opt-in."""
import os

POLICY_VERSION = '2026-11-12-v1'
BACKUP_POLICY = 'render-pitr-7d-v1'


def is_production():
    return os.getenv('DALJAM_ENV') == 'production'


def backup_policy_ready():
    return os.getenv('DALJAM_BACKUP_POLICY') == BACKUP_POLICY


def require_registration_consent(privacy, health, version, overseas=False, adult=False):
    if is_production() and (privacy is not True or health is not True or overseas is not True
                            or adult is not True or version != POLICY_VERSION):
        raise ValueError('개인정보와 건강정보 수집 안내를 각각 확인하고 동의해 주세요.')


def check_configuration(env):
    """Fail closed before starting either web server; never print values."""
    from urllib.parse import urlsplit
    origin = urlsplit(env.get('DALJAM_PUBLIC_ORIGIN', ''))
    if (env.get('DALJAM_ENV') != 'production' or env.get('DALJAM_DEMO_ONLY') != '0'
            or env.get('DALJAM_BACKUP_POLICY') != BACKUP_POLICY
            or origin.scheme != 'https' or not origin.hostname or origin.username
            or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment):
        raise ValueError('Check production mode, public HTTPS origin and backup policy.')
