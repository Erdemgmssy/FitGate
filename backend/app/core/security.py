import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
import jwt
from app.core.config import settings
from app.core import time as timezone

hasher = PasswordHasher()

def hash_password(value): return hasher.hash(value)

def check_password(value, encoded):
    try:
        if encoded.startswith('argon2$'):
            encoded='$'+encoded.split('$',1)[1]
        if encoded.startswith('$argon2'):
            return hasher.verify(encoded,value)
        if encoded.startswith('pbkdf2_sha256$'):
            _,iterations,salt,expected=encoded.split('$',3)
            actual=base64.b64encode(hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),int(iterations))).decode()
            return hmac.compare_digest(actual,expected)
    except (ValueError,VerificationError,InvalidHashError): pass
    return False

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def access_token(user, session):
    if len(settings.secret_key)<48: raise RuntimeError('Configure SECRET_KEY with at least 48 random characters')
    now=timezone.now()
    return jwt.encode({'sub':str(user.id),'sid':str(session.id),'type':'access','iat':now,'exp':now+timedelta(minutes=settings.access_minutes),'iss':'fitgate','aud':'fitgate-ui'},settings.secret_key,algorithm='HS256')

def decode_access(token):
    return jwt.decode(token,settings.secret_key,algorithms=['HS256'],issuer='fitgate',audience='fitgate-ui',options={'require':['exp','iat','sub','sid']})

def random_token(): return secrets.token_urlsafe(48)
