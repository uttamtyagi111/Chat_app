import uuid, hashlib, random
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from wish_bot.db import get_user_collection


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hash_password(password) == hashed

def generate_token(user_id):
    refresh = RefreshToken.for_user(user_id)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class SignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if get_user_collection.find_one({"email": email}):
            return Response({"error": "Email already exists"}, status=400)

        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "email": email,
            "password": hash_password(password),
            "created_at": datetime.utcnow()
        }
        get_user_collection.insert_one(user)
        return Response({"message": "Signup successful"}, status=201)

class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = get_user_collection.find_one({"email": email})
        if not user or not check_password(password, user["password"]):
            return Response({"error": "Invalid credentials"}, status=400)

        token = generate_token(user["user_id"])
        return Response({"token": token}, status=200)

class ResetPasswordRequestAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        user = get_user_collection.find_one({"email": email})
        if not user:
            return Response({"error": "Email not found"}, status=404)

        otp = str(random.randint(100000, 999999))
        get_user_collection.update_one(
            {"email": email},
            {"$set": {
                "reset_otp": otp,
                "otp_expiry": datetime.utcnow() + timedelta(minutes=10)
            }}
        )
        # Replace with your email function
        print(f"OTP for {email} is {otp}")  # or send_mail(...)
        return Response({"message": "OTP sent to your email"}, status=200)

class ResetPasswordConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("new_password")

        user = get_user_collection.find_one({"email": email})
        if not user or user.get("reset_otp") != otp:
            return Response({"error": "Invalid OTP"}, status=400)

        if datetime.utcnow() > user.get("otp_expiry", datetime.utcnow()):
            return Response({"error": "OTP expired"}, status=400)

        get_user_collection.update_one(
            {"email": email},
            {"$set": {"password": hash_password(new_password)},
             "$unset": {"reset_otp": "", "otp_expiry": ""}}
        )
        return Response({"message": "Password reset successful"}, status=200)
