"""Run after provisioning: python -m beta_v1.check_auth. Never prints secrets."""
from __future__ import annotations

import os
import secrets
from urllib.parse import urlparse

REQUIRED = ('BB_V1_CLIENT_ID', 'BB_V1_CLIENT_SECRET', 'BB_V1_REDIRECT_URI',
            'BB_V1_REDIS_URL', 'BB_V1_TOKEN_ENCRYPTION_KEY')
CALLBACK = 'https://box-score-analysis.vercel.app/beta/oauth/callback'


def main() -> int:
    missing = [key for key in REQUIRED if not os.environ.get(key)]
    if missing:
        print('Missing settings: ' + ', '.join(missing))
        return 1
    if os.environ['BB_V1_REDIRECT_URI'] != CALLBACK:
        print('Production callback must be: ' + CALLBACK)
        return 1
    if urlparse(os.environ['BB_V1_REDIS_URL']).scheme != 'rediss':
        print('Production session storage requires a TLS Redis URL (rediss://).')
        return 1
    from cryptography.fernet import Fernet
    import redis
    try:
        cipher = Fernet(os.environ['BB_V1_TOKEN_ENCRYPTION_KEY'].encode('ascii'))
    except (ValueError, UnicodeError):
        print('BB_V1_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.')
        return 1
    key = 'bb-v1:setup-check:' + secrets.token_hex(16)
    try:
        client = redis.Redis.from_url(os.environ['BB_V1_REDIS_URL'], socket_connect_timeout=5, socket_timeout=5)
        test_value = cipher.encrypt(b'NIKA setup check')
        client.set(key, test_value, ex=60)
        if cipher.decrypt(client.get(key)) != b'NIKA setup check':
            raise ValueError('round-trip failed')
        client.delete(key)
    except Exception:
        print('Encrypted Redis round-trip failed. Check the Redis URL, network and credentials.')
        return 1
    print('Configuration and encrypted Redis round-trip passed. OAuth consent still needs a browser test.')
    print('An unapproved BuzzerBeater application works only for its owner; request staff review for public access.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
