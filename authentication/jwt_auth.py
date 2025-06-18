from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from authentication.utils import decode_token

class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None  # Let DRF continue checking other auth classes or reject

        token = auth_header.split(" ")[1]
        payload = decode_token(token)
        if not payload:
            raise AuthenticationFailed("Invalid or expired token")

        return (payload, None)  # DRF sets request.user = payload
