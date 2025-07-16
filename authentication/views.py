from utils.email_sender import send_otp_email
import logging
from datetime import datetime, timedelta
from django.conf import settings
from duo_client import Auth
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timedelta
from django.views.decorators.csrf import csrf_exempt
import json, uuid, datetime
from wish_bot.db import get_admin_collection, get_blacklist_collection
from .utils import (
    hash_password, verify_password,
    generate_access_token, generate_refresh_token, decode_token,
    generate_reset_code, hash_token,jwt_required, validate_email_format
)
from .utils import decode_token
logger = logging.getLogger(__name__)


# ✅ Health Check: simple endpoint to verify server is running
@require_http_methods(["GET"])
def health_check(request):
    """
    Health Check Endpoint
    This endpoint is used to verify that the server is running and responsive.
    Returns a JSON response with a success message.
    """
    logger.info("Health check endpoint accessed")
    # You can add more checks here if needed, like database connectivity
    return JsonResponse({"message":  "Server is UP"}, status=200)




# ✅ Register superadmin (once only)
@csrf_exempt
def register_superadmin(request):
    admin_collection = get_admin_collection()
    if admin_collection.find_one({'role': 'superadmin'}):
        return JsonResponse({"error": "Superadmin already exists"}, status=403)

    if request.method == 'POST':
        data = json.loads(request.body)
        data['name'] = data.get('name', '').strip()
        if not data.get('name'):    
            return JsonResponse({"error": "Username is required"}, status=400)
        if len(data['name']) < 3:
            return JsonResponse({"error": "Username must be at least 3 characters long"}, status=400)
        data['email'] = data.get('email', '').lower()
        if not data.get('email') or not data.get('password'):
            return JsonResponse({"error": "Email and password are required"}, status=400)
        if not validate_email_format(data["email"]):
            return JsonResponse({"error": "Invalid email format"}, status=400)
        data['role'] = 'superadmin'
        data['admin_id'] = str(uuid.uuid4())
        data['password'] = hash_password(data['password'])
        data['created_at'] = datetime.datetime.utcnow()
        admin_collection.insert_one(data)
        return JsonResponse({"message": "Superadmin created successfully"}, status=201)
    return JsonResponse({"error": "Invalid request method"}, status=405)


# ✅ Login: return manually signed access and refresh tokens
@csrf_exempt
def login(request):
    data = json.loads(request.body)
    email = data.get('email')
    password = data.get('password')

    user = get_admin_collection().find_one({'email': email})
    if not validate_email_format(email):
            return JsonResponse({"error": "Invalid email format"}, status=400)
    if not user or not verify_password(password, user['password']):
        return JsonResponse({"error": "Invalid credentials"}, status=401)
    
    
    try:
        duo = Auth(
            ikey=settings.DUO_IKEY,
            skey=settings.DUO_SKEY,
            host=settings.DUO_API_HOSTNAME
        )
        username = user.get("duo_username") or user["email"]

        auth_response = duo.auth(
            username=username,     # Must match a Duo user
            factor='push',
            device='auto'
        )

        if auth_response.get("result") != "allow":
            return JsonResponse({
        "error": "Duo authentication failed",
        "duo_result": auth_response.get("result"),
        "status_msg": auth_response.get("status_msg"),
    }, status=401)

    except Exception as e:
        return JsonResponse({"error": f"Duo error: {str(e)}"}, status=500)


    payload = {
        'admin_id': user['admin_id'],
        'email': user['email'],
        'role': user['role'],
    }
    # if user['role'] == 'agent':
    #     widgets = user.get('assigned_widgets', [])
    #     # Ensure it's a list
    #     if isinstance(widgets, str):
    #         widgets = [widgets]
    #     payload['assigned_widgets'] = widgets
        
    print("Payload for token generation:", payload)  # Debugging line to check payload structure

    access_token = generate_access_token(payload)
    refresh_token = generate_refresh_token(payload)

    return JsonResponse({
        'access': access_token,
        'refresh': refresh_token,
        'role': user['role'],
        'admin_id': user['admin_id'],
        'email': user['email'],
    })


# ✅ Token Refresh: issue new access token only if refresh token is valid & not blacklisted
@csrf_exempt
def refresh_token_view(request):
    data = json.loads(request.body)
    token = data.get("refresh")
    if not token:
        return JsonResponse({"error": "Refresh token is required"}, status=400)

    hashed = hash_token(token)
    if get_blacklist_collection().find_one({"token": hashed}):
        return JsonResponse({"error": "Token has been blacklisted"}, status=401)

    payload = decode_token(token)
    if not payload or payload.get('type') != 'refresh':
        return JsonResponse({"error": "Invalid or expired refresh token"}, status=401)

    new_access = generate_access_token({
        'admin_id': payload['admin_id'],
        'email': payload['email'],
        'role': payload['role'],
        'assigned_widgets': payload['assigned_widgets', []]
    })

    return JsonResponse({'access': new_access})



# ✅ Logout: hash & store refresh token in blacklist with TTL
@require_http_methods(["POST"])
@jwt_required
def logout(request):
    logger.info("Logout attempt initiated")
    
    try:
        # Parse JSON body from Django request
        try:
            body = json.loads(request.body.decode('utf-8'))
            refresh_token = body.get("refresh")
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Logout failed - Invalid JSON in request body")
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
        if not refresh_token:
            logger.warning("Logout failed - Missing refresh token")
            return JsonResponse({"error": "Refresh token required"}, status=400)

        # Log token processing (without logging the actual token for security)
        logger.info("Processing logout - Hashing refresh token")
        
        hashed = hash_token(refresh_token)
        expiry = datetime.now() + timedelta(days=7)

        # Log blacklist operation
        logger.info(f"Adding token to blacklist - Expiry: {expiry}")
        
        try:
            get_blacklist_collection().insert_one({
                "token": hashed,
                "expiresAt": expiry,
                "created_at": datetime.now()
            })
            logger.info(f"Logout successful - Token blacklisted until: {expiry}")
        except DuplicateKeyError:
            logger.info("Logout successful - Token was already blacklisted")

        return JsonResponse({"message": "Logged out successfully"})
        
    except Exception as e:
        logger.error(
            f"Logout failed - Error: {str(e)}", 
            exc_info=True  # This includes the full stack trace
        )
        return JsonResponse({"error": "Invalid refresh token"}, status=400)

# # ✅ Create Agent: Only for superadmin (manual role check)
# @csrf_exempt
# @jwt_required
# def create_agent(request):
#     user = request.user
#     if user.get('role') != 'superadmin':
#         return JsonResponse({"error": "Unauthorized"}, status=403)

#     data = json.loads(request.body)
#     data['email'] = data.get('email', '').lower()
#     data['role'] = 'agent'
#     data['admin_id'] = str(uuid.uuid4())
#     data['password'] = hash_password(data['password'])
#     data['created_at'] = datetime.datetime.utcnow()
#     if not data.get('email') or not data.get('password'):
#         return JsonResponse({"error": "Email and password are required"}, status=400)
#     if not validate_email_format(data['email']):
#             return JsonResponse({"error": "Invalid email format"}, status=400)
#     get_admin_collection().insert_one(data)

#     return JsonResponse({"message": "Agent created successfully"})



# ✅ Request password reset via code
@csrf_exempt
@require_http_methods(["POST"])
def request_password_reset(request):
    try:
        # Parse request data
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        
        # Validate email format
        if not email:
            return JsonResponse({"error": "Email is required"}, status=400)
        
        if not validate_email_format(email):
            return JsonResponse({"error": "Invalid email format"}, status=400)
        
        # Check if user exists
        user = get_admin_collection().find_one({"email": email})
        if not user:
            # For security, don't reveal whether email exists or not
            return JsonResponse({
                "message": "If this email is registered, you will receive a reset code shortly."
            })
        
        # Check for recent reset requests (rate limiting)
        recent_reset = get_admin_collection().find_one({
            "email": email,
            "reset_code_created": {"$gte": datetime.datetime.utcnow() - timedelta(minutes=1)}
        })
        
        if recent_reset:
            return JsonResponse({
                "error": "Please wait at least 1 minute before requesting another reset code"
            }, status=429)
        
        # Generate reset code with expiration
        reset_code = generate_reset_code()
        reset_code_expires = datetime.datetime.utcnow() + timedelta(minutes=15)  # 15 minutes expiry

        # Update user with reset code and timestamp
        get_admin_collection().update_one(
            {'_id': user['_id']}, 
            {
                '$set': {
                    'reset_code': reset_code,
                    'reset_code_created': datetime.datetime.utcnow(),
                    'reset_code_expires': reset_code_expires
                }
            }
        )
        
        result = send_otp_email(email, reset_code, purpose="password_reset")
       
        if result['success']:
            logger.info(f"Password reset code sent successfully to {email}")
            return JsonResponse({
                "message": "Password reset code sent to your email",
                "expires_in_minutes": 15
            })
        else:
            # Log the error for debugging but don't expose internal details
            logger.error(f"Email sending failed for {email}: {result['error']}")
            
            # Remove reset code if email failed
            get_admin_collection().update_one(
                {'_id': user['_id']},
                {'$unset': {'reset_code': "", 'reset_code_created': "", 'reset_code_expires': ""}}
            )
            
            return JsonResponse({
                "error": "Failed to send reset code. Please try again later."
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in password reset request: {str(e)}")
        return JsonResponse({
            "error": "An unexpected error occurred. Please try again later."
        }, status=500)


# ✅ Reset password with code
@csrf_exempt
@require_http_methods(["POST"])
def reset_password(request):
    try:
        # Parse request data
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip()
        new_password = data.get('new_password', '')
        
        # Validate inputs
        if not all([email, code, new_password]):
            return JsonResponse({
                "error": "Email, code, and new password are required"
            }, status=400)
        
        if not validate_email_format(email):
            return JsonResponse({"error": "Invalid email format"}, status=400)
        
        # Validate password strength
        if len(new_password) < 8:
            return JsonResponse({
                "error": "Password must be at least 8 characters long"
            }, status=400)
        
        # Find user with valid reset code
        user = get_admin_collection().find_one({
            'email': email, 
            'reset_code': code,
            'reset_code_expires': {'$gte': datetime.datetime.utcnow()}
        })
        
        if not user:
            # Check if code exists but expired
            expired_user = get_admin_collection().find_one({
                'email': email,
                'reset_code': code
            })
            
            if expired_user:
                return JsonResponse({
                    "error": "Reset code has expired. Please request a new one."
                }, status=400)
            else:
                return JsonResponse({
                    "error": "Invalid reset code or email"
                }, status=400)
        
        # Hash new password
        hashed_password = hash_password(new_password)
        
        # Update password and remove reset code
        get_admin_collection().update_one(
            {'_id': user['_id']},
            {
                '$set': {'password': hashed_password, 'password_updated_at': datetime.datetime.utcnow()},
                '$unset': {
                    'reset_code': "", 
                    'reset_code_created': "", 
                    'reset_code_expires': ""
                }
            }
        )
        
        # Send confirmation email (optional)
        from utils.email_sender import send_password_reset_confirmation
        name = user.get('name') or user.get('name')
        send_password_reset_confirmation(email, name)
        
        logger.info(f"Password reset successful for {email}")
        return JsonResponse({"message": "Password updated successfully"})
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in password reset: {str(e)}")
        return JsonResponse({
            "error": "An unexpected error occurred. Please try again later."
        }, status=500)


# ✅ Verify reset code (optional - for frontend validation)
@csrf_exempt
@require_http_methods(["POST"])
def verify_reset_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip()
        
        if not email or not code:
            return JsonResponse({"error": "Email and code are required"}, status=400)
        
        # Check if code is valid and not expired
        user = get_admin_collection().find_one({
            'email': email,
            'reset_code': code,
            'reset_code_expires': {'$gte': datetime.datetime.utcnow()}
        })
        
        if user:
            time_left = user['reset_code_expires'] - datetime.datetime.utcnow()
            return JsonResponse({
                "valid": True,
                "minutes_left": int(time_left.total_seconds() / 60)
            })
        else:
            return JsonResponse({"valid": False}, status=400)
            
    except Exception as e:
        logger.error(f"Error verifying reset code: {str(e)}")
        return JsonResponse({"error": "Verification failed"}, status=500)