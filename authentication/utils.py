import uuid
import hashlib, jwt, datetime
from django.conf import settings

def hash_password(password):
    # Use a secure password hashing algorithm in real app
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(raw, hashed):
    return hash_password(raw) == hashed

def generate_reset_code():
    return str(uuid.uuid4())[:6]

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def generate_access_token(payload):
    payload.update({
        'type': 'access',
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

def generate_refresh_token(payload):
    payload.update({
        'type': 'refresh',
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

def decode_token(token):
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None 
    
    
from functools import wraps
from django.http import JsonResponse
from .utils import decode_token

def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return JsonResponse({"error": "Authorization header missing"}, status=401)

        token = auth.split(' ')[1]
        payload = decode_token(token)
        if not payload:
            return JsonResponse({"error": "Invalid or expired token"}, status=401)

        request.user = payload  # Inject the decoded token into request
        return view_func(request, *args, **kwargs)
    return _wrapped_view
