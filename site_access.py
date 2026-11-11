"""Optional server-enforced, signed-cookie site password gate."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, make_response, redirect, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

access_bp = Blueprint('site_access', __name__)
COOKIE = 'nika_site_access'
CSRF_COOKIE = 'nika_access_csrf'
MAX_AGE = 12 * 60 * 60


def _password():
    return os.environ.get('NIKA_SITE_PASSWORD', '')


def _signer():
    key = hashlib.sha256(('nika-site-access-v1:' + _password()).encode()).digest()
    return URLSafeTimedSerializer(key, salt='nika-site-access', signer_kwargs={'digest_method':hashlib.sha256})


def _secure():
    return bool(os.environ.get('VERCEL')) or request.headers.get('X-Forwarded-Proto', request.scheme).split(',')[0].strip() == 'https'


def _next(value):
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(c) < 32 for c in value):
        return '/'
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path in {'/access'}:
        return '/'
    return value


def _unlocked():
    token = request.cookies.get(COOKIE, '')
    try:
        return _signer().loads(token, max_age=MAX_AGE) == 'allowed'
    except (BadSignature, SignatureExpired):
        return False


def _page(error='', status=401, destination=None):
    existing = request.cookies.get(CSRF_COOKIE, '')
    nonce = existing if re.fullmatch(r'[A-Za-z0-9_-]{43}', existing) else secrets.token_urlsafe(32)
    next_path = _next(destination or (request.full_path.rstrip('?') if request.method in {'GET','HEAD'} else '/'))
    g.site_access_page = True
    response = make_response(render_template('access.html', error=error, csrf=nonce, destination=next_path), status)
    response.set_cookie(CSRF_COOKIE, nonce, max_age=600, path='/', httponly=True, secure=_secure(), samesite='Strict')
    response.delete_cookie(CSRF_COOKIE, path='/access')
    return response


def protect_site():
    """Runs before page/API handlers, so CSS blur is never the access control."""
    if not _password() or request.endpoint in {'static', 'site_access.unlock'}:
        return None
    if _unlocked():
        return None
    if request.is_json or '/api/' in request.path or request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
        return jsonify(error='SiteAccessRequired', message='Enter the site password to continue.', loginUrl='/access'), 401
    return _page()


@access_bp.route('/access', methods=['GET', 'POST'])
def unlock():
    if not _password():
        return redirect('/')
    destination = _next(request.values.get('next', '/'))
    if request.method == 'GET':
        if _unlocked():
            return redirect(destination)
        return _page(destination=destination)
    csrf = request.form.get('csrf', '')
    cookie = request.cookies.get(CSRF_COOKIE, '')
    if not csrf or not cookie or not hmac.compare_digest(csrf.encode(), cookie.encode()):
        return _page('Your access form expired. Please try again.', 403, destination)
    submitted = request.form.get('password', '')
    if len(submitted) > 4096 or not hmac.compare_digest(submitted.encode(), _password().encode()):
        return _page('Incorrect password. Try again.', 401, destination)
    response = make_response(redirect(destination, code=303))
    response.set_cookie(COOKIE, _signer().dumps('allowed'), max_age=MAX_AGE, path='/', httponly=True, secure=_secure(), samesite='Lax')
    response.delete_cookie(CSRF_COOKIE, path='/')
    response.delete_cookie(CSRF_COOKIE, path='/access')
    return response


def private_responses(response):
    if _password() and request.endpoint != 'static':
        response.headers['Cache-Control'] = 'private, no-store'
        response.vary.add('Cookie')
    if getattr(g, 'site_access_page', False):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def init_site_access(app):
    app.register_blueprint(access_bp)
    app.before_request(protect_site)
    app.after_request(private_responses)
