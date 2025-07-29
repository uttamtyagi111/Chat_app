from rest_framework import status, parsers
from django.utils.timezone import now
from gc import enable
from authentication.utils import jwt_required,superadmin_required
from wish_bot.db import get_admin_collection, get_room_collection,get_agent_notes_collection,get_contact_collection
from wish_bot.db import get_widget_collection,insert_with_timestamps,get_chat_collection,get_tag_collection
from datetime import datetime, timedelta
from utils.redis_client import redis_client
from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.views import APIView
from authentication.jwt_auth import JWTAuthentication
from authentication.permissions import IsAgentOrSuperAdmin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from utils.random_id import generate_room_id,generate_widget_id,generate_contact_id
import logging
import uuid
import json
import boto3
import requests
from user_agents import parse
from botocore.exceptions import ClientError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes,authentication_classes
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from drf_spectacular.utils import extend_schema, OpenApiResponse
from pymongo.errors import PyMongoError
from drf_yasg import openapi
from django.views.decorators.http import require_GET, require_http_methods


logger = logging.getLogger(__name__)


from django.views.decorators.http import require_GET

@require_GET
@csrf_exempt
def public_widget_settings(request, widget_id):
    try:
        widget_collection = get_widget_collection()
        widget = widget_collection.find_one({"widget_id": widget_id})
        if not widget:
            return JsonResponse({"error": "Widget not found"}, status=404)
        
        settings = widget.get("settings", {})
        settings["is_active"] = widget.get("is_active", False)

        # Return only settings + public info (avoid internal IDs)
        return JsonResponse({
            "widget_id": widget["widget_id"],
            "settings": settings,
        }, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



@require_GET
@csrf_exempt
@jwt_required
def get_widget(request, widget_id=None):
    try:
        user = request.jwt_user  
        role = user.get("role")
        admin_id = user.get("admin_id")

        widget_collection = get_widget_collection()
        base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"

        def format_widget(widget):
            # Generate widget code if not stored in DB (for backward compatibility)
            widget_code = widget.get("widget_code")
            if not widget_code:
                widget_code = generate_widget_code(
                    widget_id=widget["widget_id"],
                    request=request,
                    theme_color=widget.get("settings", {}).get("primaryColor", "#10B981"),
                    logo_url=widget.get("settings", {}).get("logo", ""),
                    position=widget.get("settings", {}).get("position", "right")
                )
            
            return {
                "widget_id": widget["widget_id"],
                "widget_type": widget["widget_type"],
                "domain": widget.get("domain", "http://localhost:9000"),
                "name": widget["name"],
                "is_active": widget.get("is_active", False),
                "created_at": str(widget.get("created_at", "")),
                "updated_at": str(widget.get("updated_at", "")),
                "settings": widget.get("settings", {
                    "position": "position",
                    "logo": "logo",
                    "primaryColor": "#10B981",
                    "enableAttentionGrabber": "enable_attention_grabber",
                    "attentionGrabber": "attention_grabber",
                    "welcomeMessage": "",
                    "offlineMessage": "",
                    "soundEnabled": True
                }),
                "direct_chat_link": widget.get("direct_chat_link", f"{base_domain}/chat/direct-chat/{widget['widget_id']}"),
                "widget_code": widget_code
            }

        if widget_id:
            widget = widget_collection.find_one({"widget_id": widget_id})
            if not widget:
                return JsonResponse({"error": "Widget not found"}, status=404)

            if role == "agent":
                agent = get_admin_collection().find_one({"admin_id": admin_id})
                assigned_widgets = agent.get("assigned_widgets", [])
                if widget_id not in assigned_widgets:
                    return JsonResponse({"error": "Access denied to this widget"}, status=403)

            return JsonResponse(format_widget(widget), status=200)

        # Get all widgets based on role
        if role == "superadmin":
            widgets = widget_collection.find()
        elif role == "agent":
            agent = get_admin_collection().find_one({"admin_id": admin_id})
            assigned_widgets = agent.get("assigned_widgets", [])
            widgets = widget_collection.find({"widget_id": {"$in": assigned_widgets}})
        else:
            return JsonResponse({"error": "Unauthorized role"}, status=403)

        return JsonResponse({"widgets": [format_widget(w) for w in widgets]}, status=200)
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


logger = logging.getLogger(__name__)

class UpdateWidgetAPIView(APIView):
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, widget_id):
        try:
            logger.info(f"[UpdateWidgetAPIView] PATCH update request for widget_id: {widget_id}")
            logger.info(f"Request data: {request.data}")
            logger.info(f"Files: {request.FILES}")

            # Get user info from token
            user = request.user
            role = user.get("role")
            admin_id = user.get("admin_id")
            logger.info(f"Authenticated user role: {role}, admin_id: {admin_id}")

            widget_collection = get_widget_collection()
            widget = widget_collection.find_one({"widget_id": widget_id})
            if not widget:
                return Response({"error": "Widget not found"}, status=404)

            # Check permissions
            if role == "agent":
                admin = get_admin_collection().find_one({"admin_id": admin_id})
                if not admin or widget_id not in admin.get("assigned_widgets", []):
                    logger.warning("Agent is not authorized to update this widget")
                    return Response({"error": "You are not authorized to update this widget"}, status=403)

            settings_data = widget.get("settings", {})
            incoming = request.data

            # Handle file uploads
            def upload_to_s3(file_obj, folder, max_size_mb, allowed_types):
                if file_obj.size > max_size_mb * 1024 * 1024:
                    raise ValueError(f"File too large (max {max_size_mb}MB)")
                if file_obj.content_type not in allowed_types:
                    raise ValueError("Invalid file type")

                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME,
                )
                file_name = f"{folder}/{uuid.uuid4()}/{file_obj.name}"
                s3_client.upload_fileobj(
                    file_obj,
                    settings.AWS_STORAGE_BUCKET_NAME,
                    file_name,
                    ExtraArgs={'ContentType': file_obj.content_type}
                )
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{file_name}"

            # Upload logo
            logo_url = settings_data.get("logo", "")
            if "logo" in request.FILES:
                try:
                    logo_url = upload_to_s3(
                        request.FILES["logo"],
                        "chat_logos",
                        max_size_mb=5,
                        allowed_types=["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"]
                    )
                except ValueError as ve:
                    return Response({"error": str(ve)}, status=400)

            # Upload attention grabber
            grabber_url = settings_data.get("attentionGrabber", "")
            if "attentionGrabber" in request.FILES:
                try:
                    grabber_url = upload_to_s3(
                        request.FILES["attentionGrabber"],
                        "attentionGrabbers",
                        max_size_mb=10,
                        allowed_types=["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "video/mp4", "video/webm"]
                    )
                except ValueError as ve:
                    return Response({"error": str(ve)}, status=400)

            # Update settings
            updated_settings = {
                "position": incoming.get("position", settings_data.get("position", "right")),
                "primaryColor": incoming.get("primaryColor", settings_data.get("primaryColor", "#10B981")),
                "logo": logo_url,
                "enableAttentionGrabber": incoming.get("enableAttentionGrabber", settings_data.get("enableAttentionGrabber", False)) in [True, "true", "True"],
                "attentionGrabber": grabber_url,
                "welcomeMessage": incoming.get("welcomeMessage", settings_data.get("welcomeMessage", "")),
                "offlineMessage": incoming.get("offlineMessage", settings_data.get("offlineMessage", "")),
                "soundEnabled": incoming.get("soundEnabled", settings_data.get("soundEnabled", True)) in [True, "true", "True"],
            }

            # Update main widget fields
            updated_fields = {
                "updated_at": now(),
                "settings": updated_settings
            }

            if role == "superadmin":
                updated_fields.update({
                    "name": incoming.get("name", widget.get("name")),
                    "widget_type": incoming.get("widget_type", widget.get("widget_type")),
                    "domain": incoming.get("domain", widget.get("domain")),
                    "is_active": incoming.get("is_active", widget.get("is_active")) in [True, "true", "True"]
                })

            widget_collection.update_one({"widget_id": widget_id}, {"$set": updated_fields})
            logger.info(f"[UpdateWidgetAPIView] Widget {widget_id} updated successfully")

            return Response({
                "message": "Widget updated successfully",
                "widget_id": widget_id,
                "settings": updated_settings
            }, status=200)

        except ClientError as e:
            logger.error(f"[S3 Upload] ClientError: {str(e)}", exc_info=True)
            return Response({"error": "S3 upload failed", "details": str(e)}, status=500)

        except Exception as e:
            logger.error(f"[UpdateWidgetAPIView] Unexpected error: {str(e)}", exc_info=True)
            return Response({"error": "Unexpected server error", "details": str(e)}, status=500)


    
@csrf_exempt
@jwt_required
@superadmin_required
@require_http_methods(["DELETE"])
def delete_widget(request, widget_id):
    try:
        widget_collection = get_widget_collection()
        widget = widget_collection.find_one({"widget_id": widget_id})
        
        if not widget:
            return JsonResponse({"error": "Widget not found"}, status=404)
        
        # Delete the widget
        widget_collection.delete_one({"widget_id": widget_id})
        
        return JsonResponse({"message": f"Widget {widget_id} deleted successfully"}, status=200)
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
@jwt_required
@superadmin_required
def create_widget(request):
    try:
        data = request.POST.dict()

        # Required fields
        widget_type = data.get("widget_type")
        name = data.get("name")
        if not widget_type or not name:
            return JsonResponse({"error": "Missing required fields"}, status=400)

        # Optional fields
        domain = data.get("domain", "http://localhost:8000")
        is_active = data.get("is_active", "false").lower() == "true"

        position = data.get("position", "right")
        primary_color = data.get("primaryColor", "#10B981")
        welcome_message = data.get("welcomeMessage", "Hello! How can we help you?")
        offline_message = data.get("offlineMessage", "We're currently offline.")
        sound_enabled = data.get("soundEnabled", "true").lower() == "true"
        enable_attention_grabber = data.get("enableAttentionGrabber", "false").lower() == "true"

        # Handle logo upload to S3
        logo_url = ""
        logo_file = request.FILES.get("logo")
        if logo_file:
            try:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                file_name = f"chat_logos/{uuid.uuid4()}/{logo_file.name}"

                s3_client.upload_fileobj(
                    logo_file,
                    bucket_name,
                    file_name,
                    ExtraArgs={'ContentType': logo_file.content_type}
                )
                logo_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
            except Exception as e:
                logger.error(f"Logo upload failed: {str(e)}", exc_info=True)
                return JsonResponse({'error': f'Failed to upload logo: {str(e)}'}, status=500)

        # Handle attention grabber (upload or URL)
        attention_grabber_file = request.FILES.get("attentionGrabber")
        attention_grabber_url = data.get("attentionGrabber", "").strip()

        if attention_grabber_file:
            try:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                file_name = f"attentionGrabbers/{uuid.uuid4()}/{attention_grabber_file.name}"

                s3_client.upload_fileobj(
                    attention_grabber_file,
                    bucket_name,
                    file_name,
                    ExtraArgs={'ContentType': attention_grabber_file.content_type}
                )
                attention_grabber_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
            except Exception as e:
                logger.error(f"Attention grabber upload failed: {str(e)}", exc_info=True)
                return JsonResponse({'error': f'Failed to upload attention grabber: {str(e)}'}, status=500)

        # Check for duplicates
        widget_collection = get_widget_collection()
        if widget_collection.find_one({"widget_type": widget_type, "name": name}):
            return JsonResponse({"error": "A widget with this type and name already exists."}, status=400)

        # Generate unique widget_id
        while True:
            widget_id = generate_widget_id()
            if not widget_collection.find_one({"widget_id": widget_id}):
                break

        # Generate widget code early (before saving to DB)
        widget_code = generate_widget_code(
            widget_id=widget_id,
            request=request,
            theme_color=primary_color,
            logo_url=logo_url,
            position=position
        )

        # Determine base domain for embed code
        base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
        direct_chat_link = f"{base_domain}/chat/direct-chat/{widget_id}/"

        # Final widget document (now includes widget_code)
        widget = {
            "widget_id": widget_id,
            "widget_type": widget_type,
            "name": name,
            "domain": domain,
            "is_active": is_active,
            "widget_code": widget_code,  # Save widget code to database
            "direct_chat_link": direct_chat_link,  # Also save direct chat link
            "settings": {
                "position": position,
                "primaryColor": primary_color,
                "logo": logo_url,
                "attentionGrabber": attention_grabber_url,
                "enableAttentionGrabber": enable_attention_grabber,
                "welcomeMessage": welcome_message,
                "offlineMessage": offline_message,
                "soundEnabled": sound_enabled,
            }
        }

        insert_with_timestamps(widget_collection, widget)

        return JsonResponse({
            "widget_id": widget_id,
            "widget_type": widget_type,
            "domain": domain,
            "name": name,
            "is_active": is_active,
            "settings": widget["settings"],
            "direct_chat_link": direct_chat_link,
            "widget_code": widget_code,  # Return the generated widget code
        }, status=201)

    except Exception as e:
        logger.exception("Error in create_widget")
        return JsonResponse({"error": str(e)}, status=500)

# Helper function to generate the widget embed code
def generate_widget_code(widget_id, request, theme_color="#ff6600", logo_url=None, position="right"):
    # Determine base domain dynamically
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    base_domain = f"{scheme}://{host}"

    # Script source - hosted JS file
    script_url = f"{base_domain}/static/js/chat_widget2.js"

    # Logo fallback
    if not logo_url:
        logo_url = f"{base_domain}/static/images/default_logo.png"
        
    return f"""
<!-- Start of Chat Widget Script -->
<script
   src="{script_url}?widget_id={widget_id}"></script>
<!-- End of Chat Widget Script -->
"""

# @csrf_exempt
# @require_POST
# @jwt_required
# @superadmin_required
# def create_widget(request):
#     try:
#         data = request.POST.dict()

#         # Required fields
#         widget_type = data.get("widget_type")
#         name = data.get("name")
#         if not widget_type or not name:
#             return JsonResponse({"error": "Missing required fields"}, status=400)

#         # Optional fields
#         domain = data.get("domain", "http://localhost:8000")
#         is_active = data.get("is_active", "false").lower() == "true"

#         position = data.get("position", "right")
#         primary_color = data.get("primaryColor", "#10B981")
#         welcome_message = data.get("welcomeMessage", "Hello! How can we help you?")
#         offline_message = data.get("offlineMessage", "We're currently offline.")
#         sound_enabled = data.get("soundEnabled", "true").lower() == "true"
#         enable_attention_grabber = data.get("enableAttentionGrabber", "false").lower() == "true"

#         # Handle logo upload to S3
#         logo_url = ""
#         logo_file = request.FILES.get("logo")
#         if logo_file:
#             try:
#                 s3_client = boto3.client(
#                     's3',
#                     aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#                     aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#                     region_name=settings.AWS_S3_REGION_NAME
#                 )
#                 bucket_name = settings.AWS_STORAGE_BUCKET_NAME
#                 file_name = f"chat_logos/{uuid.uuid4()}/{logo_file.name}"

#                 s3_client.upload_fileobj(
#                     logo_file,
#                     bucket_name,
#                     file_name,
#                     ExtraArgs={'ContentType': logo_file.content_type}
#                 )
#                 logo_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
#             except Exception as e:
#                 logger.error(f"Logo upload failed: {str(e)}", exc_info=True)
#                 return JsonResponse({'error': f'Failed to upload logo: {str(e)}'}, status=500)

#         # Handle attention grabber (upload or URL)
#         attention_grabber_file = request.FILES.get("attentionGrabberFile")
#         attention_grabber_url = data.get("attentionGrabber", "").strip()

#         if attention_grabber_file:
#             try:
#                 s3_client = boto3.client(
#                     's3',
#                     aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#                     aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#                     region_name=settings.AWS_S3_REGION_NAME
#                 )
#                 bucket_name = settings.AWS_STORAGE_BUCKET_NAME
#                 file_name = f"attentionGrabbers/{uuid.uuid4()}/{attention_grabber_file.name}"

#                 s3_client.upload_fileobj(
#                     attention_grabber_file,
#                     bucket_name,
#                     file_name,
#                     ExtraArgs={'ContentType': attention_grabber_file.content_type}
#                 )
#                 attention_grabber_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
#             except Exception as e:
#                 logger.error(f"Attention grabber upload failed: {str(e)}", exc_info=True)
#                 return JsonResponse({'error': f'Failed to upload attention grabber: {str(e)}'}, status=500)

#         # Check for duplicates
#         widget_collection = get_widget_collection()
#         if widget_collection.find_one({"widget_type": widget_type, "name": name}):
#             return JsonResponse({"error": "A widget with this type and name already exists."}, status=400)

#         # Generate unique widget_id
#         while True:
#             widget_id = generate_widget_id()
#             if not widget_collection.find_one({"widget_id": widget_id}):
#                 break

#         # Final widget document
#         widget = {
#             "widget_id": widget_id,
#             "widget_type": widget_type,
#             "name": name,
#             "domain": domain,
#             "is_active": is_active,
#             "settings": {
#                 "position": position,
#                 "primaryColor": primary_color,
#                 "logo": logo_url,
#                 "attentionGrabber": attention_grabber_url,
#                 "enableAttentionGrabber": enable_attention_grabber,
#                 "welcomeMessage": welcome_message,
#                 "offlineMessage": offline_message,
#                 "soundEnabled": sound_enabled,
#             }
#         }

#         insert_with_timestamps(widget_collection, widget)

#         # Determine base domain for embed code
#         base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
#         direct_chat_link = f"{base_domain}/chat/direct-chat/{widget_id}/"

#         return JsonResponse({
#             "widget_id": widget_id,
#             "widget_type": widget_type,
#             "domain": domain,
#             "name": name,
#             "is_active": is_active,
#             "settings": widget["settings"],
#             "direct_chat_link": direct_chat_link,
#             "widget_code": generate_widget_code(
#                 widget_id=widget_id,
#                 request=request,
#                 theme_color=primary_color,
#                 # attention_grabber=attention_grabber_url,
#                 # enable_attention_grabber=enable_attention_grabber,
#                 logo_url=logo_url,
#                 position=position
#             ),
#         }, status=201)

#     except Exception as e:
#         logger.exception("Error in create_widget")
#         return JsonResponse({"error": str(e)}, status=500)



# # Helper function to generate the widget embed code
# def generate_widget_code(widget_id, request, theme_color="#ff6600", logo_url=None, position="right"):
#     # Determine base domain dynamically
#     host = request.get_host()
#     scheme = "https" if request.is_secure() else "http"
#     base_domain = f"{scheme}://{host}"

#     # Script source - hosted JS file
#     script_url = f"{base_domain}/static/js/chat_widget.js"

#     # Logo fallback
#     if not logo_url:
#         logo_url = f"{base_domain}/static/images/default_logo.png"
        
#     return f"""
# <!-- Start of Chat Widget Script -->
# <script
#    src="{script_url}?widget_id={widget_id}"></script>
# <!-- End of Chat Widget Script -->
"""
# # <script type="text/javascript">
# # var ChatWidget_API = ChatWidget_API || {{}}, ChatWidget_LoadStart = new Date();
# # (function() {{
# #     var s1 = document.createElement("script"), s0 = document.getElementsByTagName("script")[0];
# #     s1.async = true;
# #     s1.src = "{script_url}?widget_id={widget_id}";
# #     s1.charset = "UTF-8";
# #     s1.setAttribute("crossorigin", "anonymous");
# #     s0.parentNode.insertBefore(s1, s0);
# # }})();
# # </script>
# # <!-- End of Chat Widget Script -->
# """
import logging
from django.http import JsonResponse
from django.shortcuts import render
from datetime import datetime

logger = logging.getLogger(__name__)  # Use Django's logger

def direct_chat(request, widget_id):
    widget_collection = get_widget_collection()
    widget = widget_collection.find_one({"widget_id": widget_id})

    if not widget:
        logger.warning(f"[{datetime.now()}] Direct chat access failed — Widget not found: {widget_id}")
        return JsonResponse({"error": "Widget not found"}, status=404)

    # Log access
    logger.info(f"[{datetime.now()}] Direct chat accessed — Widget ID: {widget_id}, "
                f"IP: {get_client_ip(request)}, User-Agent: {request.META.get('HTTP_USER_AGENT', '')}")

    context = {
        "widget_id": widget_id,
        "base_domain": "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003",
    }
    return render(request, "chat/direct_chat.html", context)

# Utility function to get client IP
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


@swagger_auto_schema(
    method='get',
    operation_description="""
    **WebSocket Endpoints for Chat Application**

    **1. User Chat WebSocket:**
    - URL: `ws://127.0.0.1:8000/ws/chat/user_chat/`
    - Connect as a User to start chatting.
    - **Send message format:**
      ```json
      {
        "message": "Hello from user"
      }
      ```
    - **Receive message format:**
      ```json
      {
        "message": "Agent's reply"
      }
      ```

    **2. Agent Chat WebSocket:**
    - URL: `ws://127.0.0.1:8000/ws/chat/agent_chat/{room_id}/`
    - Connect as an Agent to join a user room.
    - **Send message format:**
      ```json
      {
        "message": "Hello from agent"
      }
      ```
    - **Receive message format:**
      ```json
      {
        "message": "User's message"
      }
      ```

    ---
    **Note:** 
    - Use a WebSocket client like Postman, Hoppscotch, or WebSocket King Client to connect and send/receive messages.
    - Make sure to replace `{room_id}` with your actual room ID.
    """,
    responses={200: openapi.Response('WebSocket Information')}
)
@api_view(['GET'])
def websocket_documentation(request):
    """
    Dummy view to show WebSocket documentation in Swagger UI
    """
    return Response({"message": "Refer to the description for WebSocket usage."})


class UploadFileAPIView(APIView):
    """
    API view to handle file uploads to AWS S3.  
    """
    permission_classes = []  
    authentication_classes = []
    
    @swagger_auto_schema(
        operation_description="Upload a file to AWS S3.",
        responses={
            201: openapi.Response(
                description="File uploaded successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'file_url': openapi.Schema(type=openapi.TYPE_STRING, description="URL of the uploaded file"),
                        'file_name': openapi.Schema(type=openapi.TYPE_STRING, description="Name of the uploaded file")
                    }
                )
            ),
            400: openapi.Response(description="No file provided"),
            500: openapi.Response(description="S3 client initialization failed or upload failed")
        },
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'file': openapi.Schema(type=openapi.TYPE_FILE, description="The file to upload to AWS S3.")
            },
            required=['file']
        )
    ) 
    
    def post(self, request, *args, **kwargs):
        logger.info("Received POST request to upload file")
        print(f"DEBUG: AWS_STORAGE_BUCKET_NAME = {settings.AWS_STORAGE_BUCKET_NAME}")
        file_obj = request.FILES.get('file')
        if not file_obj:
            logger.warning("No file provided in the request")
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"File received: {file_obj.name}, size: {file_obj.size} bytes")

        # Initialize S3 client
        try:
            logger.debug("Initializing AWS S3 client")
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            print("Bucket name:", bucket_name) 
            logger.info(f"Using bucket: {bucket_name}")
            if not bucket_name:
                logger.error("AWS_STORAGE_BUCKET_NAME is not defined in settings")
                return Response({'error': 'AWS_STORAGE_BUCKET_NAME is not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            file_name = f"chat_files/{uuid.uuid4()}/{file_obj.name}"
            logger.info(f"Generated S3 file path: {file_name}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
            return Response({'error': f'S3 client initialization failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Upload to S3
        try:
            logger.info(f"Starting upload to S3 bucket: {bucket_name}")
            s3_client.upload_fileobj(
                file_obj,
                bucket_name,
                file_name,
                ExtraArgs={'ContentType': file_obj.content_type}
            )
            file_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
            logger.info(f"File uploaded successfully. URL: {file_url}")
            return Response({
                'file_url': file_url,
                'file_name': file_obj.name
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Failed to upload file to S3: {str(e)}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def index(request):
    return render(request, 'chat/index.html') 


def chat_view(request):
    if not request.session.get('room_id'):
        request.session['room_id'] = str(uuid.uuid4())
        print("🎯 New Room ID assigned:", request.session['room_id'])
    else:
        print("ℹ️ Existing Room ID:", request.session['room_id'])

    room_id = request.session['room_id']
    return render(request, 'chat/chatroom.html', {'room_id': room_id})

chat_rooms = {}

"""
for testing with frontend template 
"""
# def user_chat(request):
#     room_id = generate_room_id()
#     room_collection = get_room_collection()

#     existing_room = room_collection.find_one({'room_id': room_id})
    
#     while existing_room:
#         room_id = generate_room_id()
#         existing_room = room_collection.find_one({'room_id': room_id})

#     room_collection.insert_one({
#         'room_id': room_id,
#         'is_active': True,
#         'created_at': datetime.now(),
#         'assigned_agent': None,
        
#     })
    
#     return render(request, 'chat/user_chat.html', {'room_id': room_id})
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import requests
from datetime import datetime
from user_agents import parse

class UserChatAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Initialize chat: create/reuse room, return widget settings, room ID, and user location",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID to associate the room with'),
                'ip': openapi.Schema(type=openapi.TYPE_STRING, description='IP address of the user (sent from frontend)'),
                'user_agent': openapi.Schema(type=openapi.TYPE_STRING, description='User agent string of the browser'),
            },
            required=['widget_id', 'ip', 'user_agent']
        ),
        responses={
            200: openapi.Response('Room initialized successfully'),
            400: openapi.Response('Bad Request'),
            404: openapi.Response('Widget Not Found')
        }
    )
    def get_client_ip(self, request):
        return request.data.get("ip")

    def get_ip_geolocation(self, ip_address):
        if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
            return {
                'country': 'Local',
                'city': 'Local',
                'region': 'Local',
                'country_code': '',
                'timezone': '',
                'flag': None
            }

        try:
            api_url = f'https://ipwhois.pro/{ip_address}?key=8HaX4qcer2Ml9Hfc'
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success', True):
                    country_code = data.get('country_code', '').upper()
                    flag = {
                        'emoji': ''.join(chr(ord(c) + 127397) for c in country_code),
                        'url': f"https://flagcdn.com/32x24/{country_code.lower()}.png",
                        'country_code': country_code
                    } if country_code and len(country_code) == 2 else None

                    return {
                        'country': data.get('country', 'Unknown'),
                        'city': data.get('city', 'Unknown'),
                        'region': data.get('region', ''),
                        'country_code': country_code,
                        'timezone': data.get('timezone', ''),
                        'flag': flag
                    }

        except Exception as e:
            print(f"[Geolocation Error] {str(e)}")

        return {
            'country': 'Unknown',
            'city': 'Unknown',
            'region': '',
            'country_code': '',
            'timezone': '',
            'flag': None
        }

    def post(self, request):
        widget_id = request.data.get("widget_id")
        client_ip = self.get_client_ip(request)
        user_agent_string = request.data.get("user_agent", "")

        if not widget_id:
            return Response({"error": "Widget ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not client_ip:
            return Response({"error": "IP address is required from frontend"}, status=status.HTTP_400_BAD_REQUEST)

        print(f"[UserChatAPIView] Received POST - Widget ID: {widget_id}, IP: {client_ip}")

        user_agent = parse(user_agent_string)
        os_info = f"{user_agent.os.family} {user_agent.os.version_string}" if user_agent.os.family else "Unknown OS"
        browser_info = f"{user_agent.browser.family} {user_agent.browser.version_string}" if user_agent.browser.family else "Unknown Browser"

        ip_info = self.get_ip_geolocation(client_ip) or {}
        flag_info = ip_info.get('flag') or {}

        widget_collection = get_widget_collection()
        room_collection = get_room_collection()
        contact_collection = get_contact_collection()

        widget = widget_collection.find_one({"widget_id": widget_id})
        if not widget:
            return Response({"error": "Widget not found"}, status=status.HTTP_404_NOT_FOUND)

        room = room_collection.find_one({"ip": client_ip, "widget_id": widget_id})
        if room:
            room_id = room.get("room_id")
            contact_id = room.get("contact_id")
            print(f"[UserChatAPIView] Reusing existing room ID: {room_id}")
        else:
            room_id = generate_room_id()
            while room_collection.find_one({'room_id': room_id}):
                room_id = generate_room_id()

            contact_id = generate_contact_id()
            while contact_collection.find_one({'contact_id': contact_id}):
                contact_id = generate_contact_id()

            room_document = {
                'room_id': room_id,
                'widget_id': widget_id,
                'ip': client_ip,
                'is_active': True,
                'contact_id': contact_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'assigned_agent': None,
                'user_location': {
                    'user_ip': client_ip,
                    'country': ip_info.get('country', 'Unknown'),
                    'city': ip_info.get('city', 'Unknown'),
                    'region': ip_info.get('region', ''),
                    'country_code': ip_info.get('country_code', ''),
                    'timezone': ip_info.get('timezone', ''),
                    'flag_emoji': flag_info.get('emoji', ''),
                    'flag_url': flag_info.get('url', ''),
                    'os': os_info,
                    'browser': browser_info,
                }
            }
            insert_with_timestamps(room_collection, room_document)
            print(f"[UserChatAPIView] New room created with ID: {room_id}")

        response_data = {
            "room_id": room_id,
            "widget": {
                "widget_id": widget["widget_id"],
                "widget_type": widget.get("widget_type"),
                "name": widget.get("name"),
                "settings": widget.get("settings", {}),
            },
            "user_location": {
                "ip": client_ip,
                "country": ip_info.get('country', 'Unknown'),
                "city": ip_info.get('city', 'Unknown'),
                "region": ip_info.get('region', ''),
                "timezone": ip_info.get('timezone', ''),
                "flag": flag_info,
                "os": os_info,
                "browser": browser_info,
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

# class UserChatAPIView(APIView):
#     @swagger_auto_schema(
#         operation_description="Initialize chat: create/reuse room, return widget settings, room ID, and user location",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID to associate the room with'),
#                 'ip': openapi.Schema(type=openapi.TYPE_STRING, description='IP address of the user (sent from frontend)'),
#                 'user_agent': openapi.Schema(type=openapi.TYPE_STRING, description='User agent string of the browser'),
#             },
#             required=['widget_id', 'ip', 'user_agent']
#         ),
#         responses={
#             200: openapi.Response('Room initialized successfully'),
#             400: openapi.Response('Bad Request'),
#             404: openapi.Response('Widget Not Found')
#         }
#     )
#     def get_client_ip(self, request):
#         return request.data.get("ip")

#     def get_ip_geolocation(self, ip_address):
#         if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
#             return {
#                 'country': 'Local',
#                 'city': 'Local',
#                 'region': 'Local',
#                 'country_code': '',
#                 'timezone': '',
#                 'flag': None
#             }

#         try:
#             api_url = f'https://ipwhois.pro/{ip_address}?key=8HaX4qcer2Ml9Hfc'
#             response = requests.get(api_url, timeout=10)
#             if response.status_code == 200:
#                 data = response.json()
#                 if data.get('success', True):
#                     country_code = data.get('country_code', '').upper()
#                     flag = {
#                         'emoji': ''.join(chr(ord(c) + 127397) for c in country_code),
#                         'url': f"https://flagcdn.com/32x24/{country_code.lower()}.png",
#                         'country_code': country_code
#                     } if country_code and len(country_code) == 2 else None

#                     return {
#                         'country': data.get('country', 'Unknown'),
#                         'city': data.get('city', 'Unknown'),
#                         'region': data.get('region', ''),
#                         'country_code': country_code,
#                         'timezone': data.get('timezone', ''),
#                         'flag': flag
#                     }

#         except Exception as e:
#             print(f"[Geolocation Error] {str(e)}")

#         return {
#             'country': 'Unknown',
#             'city': 'Unknown',
#             'region': '',
#             'country_code': '',
#             'timezone': '',
#             'flag': None
#         }
        
#     def post(self, request):
#         widget_id = request.data.get("widget_id")
#         client_ip = self.get_client_ip(request)
#         user_agent_string = request.data.get("user_agent", "")

#         if not widget_id:
#             return Response({"error": "Widget ID is required"}, status=status.HTTP_400_BAD_REQUEST)
#         if not client_ip:
#             return Response({"error": "IP address is required from frontend"}, status=status.HTTP_400_BAD_REQUEST)

#         print(f"[UserChatAPIView] Received POST - Widget ID: {widget_id}, IP: {client_ip}")

#         # Parse user agent
#         user_agent = parse(user_agent_string)
#         os_info = f"{user_agent.os.family} {user_agent.os.version_string}" if user_agent.os.family else "Unknown OS"
#         browser_info = f"{user_agent.browser.family} {user_agent.browser.version_string}" if user_agent.browser.family else "Unknown Browser"

#         # Fetch IP geolocation
#         ip_info = self.get_ip_geolocation(client_ip)

#         widget_collection = get_widget_collection()
#         room_collection = get_room_collection()
#         contact_collection = get_contact_collection()

#         widget = widget_collection.find_one({"widget_id": widget_id})
#         if not widget:
#             return Response({"error": "Widget not found"}, status=status.HTTP_404_NOT_FOUND)

#         # Check for existing room
#         room = room_collection.find_one({"ip": client_ip, "widget_id": widget_id})
#         if room:
#             room_id = room.get("room_id")
#             contact_id = room.get("contact_id")
#             print(f"[UserChatAPIView] Reusing existing room ID: {room_id}")
#         else:
#             # Create new room
#             room_id = generate_room_id()
#             while room_collection.find_one({'room_id': room_id}):
#                 room_id = generate_room_id()

#             contact_id = generate_contact_id()
#             while contact_collection.find_one({'contact_id': contact_id}):
#                 contact_id = generate_contact_id()

#             room_document = {
#                 'room_id': room_id,
#                 'widget_id': widget_id,
#                 'ip': client_ip,
#                 'is_active': True,
#                 'contact_id': contact_id,
#                 'created_at': datetime.utcnow(),
#                 'updated_at': datetime.utcnow(),
#                 'assigned_agent': None,
#                 'user_location': {
#                     'user_ip': client_ip,
#                     'country': ip_info.get('country', 'Unknown'),
#                     'city': ip_info.get('city', 'Unknown'),
#                     'region': ip_info.get('region', ''),
#                     'country_code': ip_info.get('country_code', ''),
#                     'timezone': ip_info.get('timezone', ''),
#                     'flag_emoji': ip_info.get('flag', {}).get('emoji', ''),
#                     'flag_url': ip_info.get('flag', {}).get('url', ''),
#                     'os': os_info,
#                     'browser': browser_info,
#                 }
#             }
#             insert_with_timestamps(room_collection, room_document)
#             print(f"[UserChatAPIView] New room created with ID: {room_id}")

#         response_data = {
#             "room_id": room_id,
#             "widget": {
#                 "widget_id": widget["widget_id"],
#                 "widget_type": widget.get("widget_type"),
#                 "name": widget.get("name"),
#                 "settings": widget.get("settings", {}),
#             },
#             "user_location": {
#                 "ip": client_ip,
#                 "country": ip_info.get('country', 'Unknown'),
#                 "city": ip_info.get('city', 'Unknown'),
#                 "region": ip_info.get('region', ''),
#                 "timezone": ip_info.get('timezone', ''),
#                 "flag": ip_info.get('flag', {}),
#                 "os": os_info,
#                 "browser": browser_info,
#             }
#         }
#         return Response(response_data, status=status.HTTP_200_OK)


  # Install this with pip install pyyaml ua-parser user-agents


@csrf_exempt
@require_GET
def test_ip_geolocation(request):
    ip_address = request.GET.get('ip', '')

    # Get browser & OS info from User-Agent
    user_agent_str = request.META.get('HTTP_USER_AGENT', '')
    user_agent = parse(user_agent_str)

    browser = f"{user_agent.browser.family} {user_agent.browser.version_string}"
    os = f"{user_agent.os.family} {user_agent.os.version_string}"
    device = user_agent.device.family

    # Handle local IPs
    if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
        return JsonResponse({
            'country': 'Local',
            'city': 'Local',
            'region': 'Local',
            'country_code': '',
            'timezone': '',
            'flag': None,
            'browser': browser,
            'os': os,
            'device': device
        })

    # IPWHOIS lookup
    try:
        api_url = f'https://ipwhois.pro/{ip_address}?key=8HaX4qcer2Ml9Hfc'
        response = requests.get(api_url, timeout=10)
        data = response.json() if response.status_code == 200 else {}

        return JsonResponse({
            'ip_data': data,
            'browser': browser,
            'os': os,
            'device': device
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# import requests
# import json
# from datetime import datetime
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from drf_yasg.utils import swagger_auto_schema
# from drf_yasg import openapi

# class UserChatAPIView(APIView):
#     @swagger_auto_schema(
#         operation_description="Create a new chat room for a given widget ID and return the room ID, widget details, and user's IP geolocation",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID to associate the room with'),
#             },
#             required=['widget_id']
#         ),
#         responses={
#             201: openapi.Response('Room created successfully', schema=openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 properties={
#                     'room_id': openapi.Schema(type=openapi.TYPE_STRING, description='Generated Room ID'),
#                     'widget': openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         properties={
#                             'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID'),
#                             'widget_type': openapi.Schema(type=openapi.TYPE_STRING, description='Type of the widget'),
#                             'name': openapi.Schema(type=openapi.TYPE_STRING, description='Name of the widget'), 
#                             'color': openapi.Schema(type=openapi.TYPE_STRING, description='Color of the widget'),
#                             'language': openapi.Schema(type=openapi.TYPE_STRING, description='Language of the widget'),
#                         }
#                     ),
#                     'user_location': openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         properties={
#                             'ip': openapi.Schema(type=openapi.TYPE_STRING, description='User IP address'),
#                             'country': openapi.Schema(type=openapi.TYPE_STRING, description='User country'),
#                             'city': openapi.Schema(type=openapi.TYPE_STRING, description='User city'),
#                             'flag': openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={
#                                     'emoji': openapi.Schema(type=openapi.TYPE_STRING, description='Country flag emoji'),
#                                     'url': openapi.Schema(type=openapi.TYPE_STRING, description='Country flag image URL'),
#                                     'country_code': openapi.Schema(type=openapi.TYPE_STRING, description='ISO country code'),
#                                 }
#                             ),
#                             'region': openapi.Schema(type=openapi.TYPE_STRING, description='User region/state'),
#                             'timezone': openapi.Schema(type=openapi.TYPE_STRING, description='User timezone'),
#                             # 'isp': openapi.Schema(type=openapi.TYPE_STRING, description='Internet Service Provider'),
#                         }
#                     )
#                 }
#             )),
#             400: openapi.Response('Bad Request', schema=openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 properties={
#                     'error': openapi.Schema(type=openapi.TYPE_STRING, description='Error message')
#                 }
#             )),
#             404: openapi.Response('Widget Not Found', schema=openapi.Schema(
#                 type=openapi.TYPE_OBJECT,
#                 properties={
#                     'error': openapi.Schema(type=openapi.TYPE_STRING, description='Error message')
#                 }
#             ))
#         }
#     )
#     def post(self, request):
#         widget_id = request.data.get("widget_id")
#         print("Received widget_id:", widget_id)

#         # Validate widget_id
#         if not widget_id:
#             print("No widget_id provided")
#             return Response({"error": "Widget ID is required"}, status=status.HTTP_400_BAD_REQUEST)

#         # Get client's IP address
#         client_ip = self.get_client_ip(request)
#         print(f"Client IP: {client_ip}")

#         # Fetch IP geolocation information
#         ip_info = self.get_ip_geolocation(client_ip)
        
#         # Fetch widget collection
#         widget_collection = get_widget_collection()
#         room_collection = get_room_collection()

#         # Validate widget existence
#         widget = widget_collection.find_one({"widget_id": widget_id})
#         if not widget:
#             return Response({"error": "Widget not found"}, status=status.HTTP_404_NOT_FOUND)

#         # Generate a unique room_id
#         room_id = generate_room_id()
#         existing_room = room_collection.find_one({'room_id': room_id})
        
#         while existing_room:
#             room_id = generate_room_id()
#             existing_room = room_collection.find_one({'room_id': room_id})

#         # Create a new room associated with the widget_id and include IP info
#         room_document = {
#             'room_id': room_id,
#             'widget_id': widget_id,
#             'is_active': True,
#             'created_at': datetime.now(),
#             'assigned_agent': None,
#             # IP and location information
#             'user_location': {
#                 'user_ip': client_ip,
#                 'country': ip_info.get('country', 'Unknown'),
#                 'city': ip_info.get('city', 'Unknown'),
#                 'region': ip_info.get('region', ''),
#                 'country_code': ip_info.get('country_code', ''),
#                 'timezone': ip_info.get('timezone', ''),
#                 # 'isp': ip_info.get('isp', ''),
#                 # 'flag_emoji': ip_info.get('flag', {}).get('emoji', ''),
#                 # 'flag_url': ip_info.get('flag', {}).get('url', ''),
#             }
#         }
        
#         insert_with_timestamps(room_collection, room_document)
        
#         # Prepare widget details to return
#         widget_details = {
#             "widget_id": widget["widget_id"],
#             "widget_type": widget.get("widget_type"),
#             "name": widget.get("name"),
#             "color": widget.get("color"),
#             "language": widget.get("language", "en"),
#         }

#         # Prepare response data
#         response_data = {
#             "room_id": room_id,
#             "widget": widget_details,
#             "user_location": {
#                 "ip": client_ip,
#                 "country": ip_info.get('country', 'Unknown'),
#                 "city": ip_info.get('city', 'Unknown'),
#                 "region": ip_info.get('region', ''),
#                 "timezone": ip_info.get('timezone', ''),
#                 # 'flag_emoji': ip_info.get('flag', {}).get('emoji', ''),
#                 # 'flag_url': ip_info.get('flag', {}).get('url', ''),
#                 # # "isp": ip_info.get('isp', ''),
#             }
#         }
        
#         # # Add flag information if available
#         # if ip_info.get('flag'):
#         #     response_data["user_location"]["flag"] = ip_info['flag']

#         return Response(response_data, status=status.HTTP_201_CREATED)

#     def get_client_ip(self, request):
#         """
#         Get the client's real IP address from request headers
#         """
#         x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#         if x_forwarded_for:
#             ip = x_forwarded_for.split(',')[0].strip()
#         else:
#             ip = request.META.get('REMOTE_ADDR')
#         return ip

#     def get_ip_geolocation(self, ip_address):
#         """
#         Get geolocation information for the given IP address
#         """
#         if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1']:
#             return {
#                 'country': 'Local',
#                 'city': 'Local',
#                 'region': 'Local',
#                 'country_code': '',
#                 'timezone': '',
#                 # 'isp': 'Local',
#                 'flag': None
#             }

#         try:
#             # Using ipwhois.pro API - replace with your API key
#             api_url = f'https://ipwhois.pro/{ip_address}?key=8HaX4qcer2Ml9Hfc'
#             print(f"DEBUG: Fetching geolocation from: {api_url}")
            
#             response = requests.get(api_url, timeout=10)
#             print(f"DEBUG: Geolocation API response status: {response.status_code}")
            
#             if response.status_code == 200:
#                 data = response.json()
#                 print(f"DEBUG: Geolocation data: {data}")
                
#                 # Check if API returned success
#                 if data.get('success', True):
#                     result = {
#                         'country': data.get('country', 'Unknown'),
#                         'city': data.get('city', 'Unknown'),
#                         'region': data.get('region', ''),
#                         'country_code': data.get('country_code', ''),
#                         'timezone': data.get('timezone', ''),
#                         # 'isp': data.get('isp', ''),
#                     }
                    
#                     # Handle flag generation
#                     country_code = data.get('country_code', '').upper()
#                     if country_code and len(country_code) == 2:
#                         result['flag'] = {
#                             'emoji': ''.join(chr(ord(c) + 127397) for c in country_code),
#                             'url': f"https://flagcdn.com/32x24/{country_code.lower()}.png",
#                             'country_code': country_code
#                         }
                    
#                     return result
#                 else:
#                     print(f"DEBUG: API returned error: {data.get('message', 'Unknown error')}")
                    
#             else:
#                 print(f"DEBUG: API request failed with status: {response.status_code}")
                
#         except requests.exceptions.Timeout:
#             print("DEBUG: IP geolocation request timed out")
#         except requests.exceptions.RequestException as e:
#             print(f"DEBUG: Network error during IP geolocation: {str(e)}")
#         except json.JSONDecodeError:
#             print("DEBUG: Invalid JSON response from IP geolocation API")
#         except Exception as e:
#             print(f"DEBUG: Unexpected error during IP geolocation: {str(e)}")
        
#         # Return default values if geolocation fails
#         return {
#             'country': 'Unknown',
#             'city': 'Unknown',
#             'region': '',
#             'country_code': '',
#             'timezone': '',
#             # 'isp': '',
#             'flag': None
#         }
 # Assuming this exists



@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
def edit_room_tags(request, room_id):
    try:
        user = request.jwt_user
        role = user.get("role")
        admin_id = user.get("admin_id")

        data = json.loads(request.body.decode("utf-8"))
        new_tags = data.get("tags", None)

        if not isinstance(new_tags, list):
            return JsonResponse({"error": "Invalid or missing 'tags' field"}, status=400)

        tag_collection = get_tag_collection()
        room_collection = get_room_collection()
        admin_collection = get_admin_collection()

        # ✅ Get room document
        room = room_collection.find_one({"room_id": room_id})
        if not room:
            return JsonResponse({"error": "Room not found"}, status=404)

        widget_id = room.get("widget_id")
        if not widget_id:
            return JsonResponse({"error": "Widget ID not found in room"}, status=400)

        # 🔐 Access control for agents
        if role != "superadmin":
            agent_doc = admin_collection.find_one({"admin_id": admin_id})
            if not agent_doc:
                return JsonResponse({"error": "Agent not found"}, status=404)

            assigned_widgets = agent_doc.get("assigned_widgets", [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]

            if widget_id not in assigned_widgets:
                return JsonResponse({"error": "You are not authorized to edit this room"}, status=403)

        # ✅ Fetch tag documents (with widget_id filtering)
        tag_cursor = tag_collection.find(
            {"name": {"$in": new_tags}, "widget_id": widget_id},
            {"_id": 0, "name": 1, "color": 1}
        )
        found_tags = list(tag_cursor)
        valid_tag_names = [tag["name"] for tag in found_tags]

        # ❌ Detect and return invalid/mismatched tags
        invalid_tags = list(set(new_tags) - set(valid_tag_names))
        if invalid_tags:
            return JsonResponse({
                "error": "Some tags are invalid or belong to a different widget",
                "invalid_tags": invalid_tags
            }, status=400)

        # ✅ Update room with valid tag objects
        room_collection.update_one(
            {"room_id": room_id},
            {"$set": {
                "tags": found_tags,
                "updated_at": datetime.utcnow()
            }}
        )

        return JsonResponse({
            "message": "Room tags updated successfully",
            "updated_tags": found_tags
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



class ActiveRoomsAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Retrieve a list of active rooms",
        responses={
            200: openapi.Response(
                description="List of active rooms",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'active_rooms': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    '_id': openapi.Schema(type=openapi.TYPE_STRING),
                                    'room_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN)
                                }
                            )
                        )
                    }
                )
            ),
            500: openapi.Response(
                description="Internal Server Error"
            ),
        }
    )
    def get(self, request):
        collection = get_room_collection()
        try:
            active_rooms = list(collection.find({'is_active': True}))
            for room in active_rooms:
                room['_id'] = str(room['_id'])  # Convert ObjectId to string for JSON serialization
            return Response({'active_rooms': active_rooms}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


"""
agent_view for testing with frontend template
"""

# def agent_chat(request, room_id):
#     room_collection = get_room_collection()
#     room = room_collection.find_one({'room_id': room_id})
#     if room:
#         room_collection.update_one(
#             {'room_id': room_id},
#             {'$set': {'assigned_agent': 'Agent 007'}}  # Replace with actual agent logic
#         )
#     return render(request, 'chat/agent_chat.html', {'room_id': room_id})


logger = logging.getLogger(__name__)

class AgentChatAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAgentOrSuperAdmin]

    @extend_schema(
        operation_id="assignAgentToRoom",
        summary="Assign an agent or superadmin to a room",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Admin ID of the agent to assign (optional for superadmin to assign self)"},
                },
                "example": {
                    "agent_id": "admin_123456"
                }
            }
        },
        responses={
            200: OpenApiResponse(response={"message": "Agent assigned successfully"}),
            400: OpenApiResponse(description="Bad Request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Room or Agent not found"),
            500: OpenApiResponse(description="Internal Server Error")
        }
    )
    def post(self, request, room_id):
        try:
            user = request.user
            role = user.get("role")
            requester_id = user.get("admin_id")

            room_collection = get_room_collection()
            admin_collection = get_admin_collection()

            # Fetch the room
            room = room_collection.find_one({"room_id": room_id})
            if not room:
                return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

            if room.get("assigned_agent"):
                return Response({"error": "Room already has an assigned agent"}, status=status.HTTP_400_BAD_REQUEST)

            room_widget_id = room.get("widget_id")
            agent_doc = None
            agent_id_to_assign = None

            if role == "agent":
                agent_id_to_assign = requester_id
                agent_doc = admin_collection.find_one({"admin_id": agent_id_to_assign, "role": "agent"})
                if not agent_doc:
                    return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

                if room_widget_id not in agent_doc.get("assigned_widgets", []):
                    return Response({"error": "You are not assigned to this widget"}, status=status.HTTP_403_FORBIDDEN)

            elif role == "superadmin":
                agent_id_to_assign = request.data.get("admin_id") or requester_id  # Use self if not provided
                agent_doc = admin_collection.find_one({"admin_id": agent_id_to_assign})
                if not agent_doc:
                    return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

                if agent_doc.get("role") == "agent" or agent_id_to_assign == requester_id:
                    if room_widget_id not in agent_doc.get("assigned_widgets", []):
                        return Response({"error": "Agent is not assigned to this widget"}, status=status.HTTP_403_FORBIDDEN)
                else:
                    return Response({"error": "Only agents or the superadmin themselves can be assigned"}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({"error": "Unauthorized role"}, status=status.HTTP_403_FORBIDDEN)

            agent_name = agent_doc.get("name", "Agent")

            # Assign agent to room: both ID and name
            room_collection.update_one(
                {"room_id": room_id},
                {
                    "$set": {
                        "assigned_agent": agent_id_to_assign,
                        "assigned_agent_name": agent_name
                    }
                }
            )

            return Response({
                "message": f"Agent '{agent_name}' assigned to room '{room_id}'",
                "room_id": room_id,
                "assigned_agent": agent_id_to_assign,
                "assigned_agent_name": agent_name
            }, status=status.HTTP_200_OK)

        except PyMongoError as e:
            logger.error(f"MongoDB Error: {str(e)}")
            return Response({"error": f"Database error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.error(f"Unexpected Error: {str(e)}")
            return Response({"error": f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




logger = logging.getLogger(__name__)

class TestAgentAssignView(APIView):
    permission_classes = []  # No auth
    authentication_classes = []

    @extend_schema(
        summary="Assign agent to room for testing and render chat UI",
        responses={
            200: OpenApiResponse(response={"message": "Agent assigned successfully"}),
            404: OpenApiResponse(description="Room not found"),
            500: OpenApiResponse(description="Internal server error")
        }
    )
    def post(self, request, room_id):
        try:
            room_collection = get_room_collection()

            room = room_collection.find_one({'room_id': room_id})
            if not room:
                return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

            assigned_agent = room.get("assigned_agent")
            if assigned_agent:
                agent_info = f"Already assigned to: {assigned_agent}"
            else:
                # Assign test agent
                assigned_agent = "test_agent"
                room_collection.update_one(
                    {'room_id': room_id},
                    {'$set': {'assigned_agent': assigned_agent}}
                )
                agent_info = f"Assigned test agent to room {room_id}"

            return render(request, 'chat/agent_chat.html', {
                'room_id': room_id,
                'agent_info': agent_info,
                'agent_name': 'Test Agent'
            })

        except PyMongoError as e:
            logger.error(f"MongoDB error: {str(e)}")
            return Response({"error": "Database error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return Response({"error": "Unexpected server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from authentication.permissions import IsAgentOrSuperAdmin
# from authentication.jwt_auth import JWTAuthentication
# from drf_spectacular.utils import extend_schema, OpenApiResponse
# from wish_bot.db import get_room_collection, get_admin_collection
# from pymongo.errors import PyMongoError
# import logging

# logger = logging.getLogger(__name__)

# class AgentChatAPIView(APIView):
#     authentication_classes = [JWTAuthentication]
#     permission_classes = [IsAgentOrSuperAdmin]

#     @extend_schema(
#         operation_id="assignAgentToRoom",
#         summary="Assign an agent to a room (agent assigns self or superadmin assigns another agent)",
#         request={
#             "application/json": {
#                 "type": "object",
#                 "properties": {
#                     "agent_id": {"type": "string", "description": "Admin ID of the agent to assign (optional for agents)"},
#                 },
#                 "example": {
#                     "agent_id": "admin_123456"
#                 }
#             }
#         },
#         responses={
#             200: OpenApiResponse(response={"message": "Agent assigned successfully"}),
#             400: OpenApiResponse(description="Bad Request"),
#             403: OpenApiResponse(description="Forbidden"),
#             404: OpenApiResponse(description="Room or Agent not found"),
#             500: OpenApiResponse(description="Internal Server Error")
#         }
#     )
#     def post(self, request, room_id):
#         try:
#             user = request.user
#             role = user.get("role")
#             requester_id = user.get("admin_id")

#             room_collection = get_room_collection()
#             admin_collection = get_admin_collection()

#             room = room_collection.find_one({"room_id": room_id})
#             if not room:
#                 return Response(
#                     {"error": "Room not found"},
#                     status=status.HTTP_404_NOT_FOUND
#                 )

#             # Prevent multiple agents from being assigned
#             if room.get("assigned_agent"):
#                 return Response(
#                     {"error": "Room already has an assigned agent"},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             room_widget_id = room.get("widget_id")

#             if role == "agent":
#                 # Agent can only assign themselves
#                 agent_doc = admin_collection.find_one({"admin_id": requester_id, "role": "agent"})
#                 if not agent_doc:
#                     return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

#                 if room_widget_id not in agent_doc.get("assigned_widgets", []):
#                     return Response({"error": "You are not assigned to this widget"}, status=status.HTTP_403_FORBIDDEN)

#                 agent_id = requester_id

#             elif role == "superadmin":
#                 agent_id = request.data.get("agent_id")
#                 if not agent_id:
#                     return Response({"error": "agent_id is required for superadmin"}, status=status.HTTP_400_BAD_REQUEST)

#                 agent_doc = admin_collection.find_one({"admin_id": agent_id, "role": "agent"})
#                 if not agent_doc:
#                     return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

#                 if room_widget_id not in agent_doc.get("assigned_widgets", []):
#                     return Response({"error": "Agent is not assigned to this widget"}, status=status.HTTP_403_FORBIDDEN)

#             else:
#                 return Response({"error": "Unauthorized role"}, status=status.HTTP_403_FORBIDDEN)

#             # Assign the agent to the room
#             room_collection.update_one(
#                 {"room_id": room_id},
#                 {"$set": {"assigned_agent": agent_id}}
#             )
            
#             # 🆕 NEW: Notify WebSocket clients about agent assignment
#             agent_name = agent_doc.get('name', 'Agent')
            
#             # Import necessary modules for WebSocket notification
#             from channels.layers import get_channel_layer
#             from asgiref.sync import async_to_sync
            
#             # Send notification to the chat room
#             channel_layer = get_channel_layer()
#             room_group_name = f'chat_{room_id}'
            
#             # Notify all clients in the room about the agent assignment
#             async_to_sync(channel_layer.group_send)(
#                 room_group_name,
#                 {
#                     'type': 'agent_assigned',
#                     'agent_name': agent_name,
#                     'agent_id': agent_id,
#                     'message': f"{agent_name} has joined the chat"
#                 }
#             )


#             return Response({
#                 "message": f"Agent '{agent_doc.get('name')}' assigned to room '{room_id}'",
#                 "room_id": room_id,
#                 "assigned_agent": agent_id,
#                 "agent_name": agent_name
#             }, status=status.HTTP_200_OK)

#         except PyMongoError as e:
#             logger.error(f"MongoDB Error: {str(e)}")
#             return Response(
#                 {"error": f"Database error: {str(e)}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
#         except Exception as e:
#             logger.error(f"Unexpected Error: {str(e)}")
#             return Response(
#                 {"error": f"Unexpected error: {str(e)}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


        
        
def agent_dashboard(request):
    rooms = []
    for key in redis_client.scan_iter("room:*"):
        room_id = key.split(":")[1]
        data = redis_client.hgetall(key)
        rooms.append({
            "room_id": room_id,
            "assigned_agent": data.get("assigned_agent", None),
            "last_message": data.get("last_message", ""),
            "last_timestamp": data.get("last_timestamp", ""),
        })
    return render(request, 'chat/agent_dashboard.html', {'rooms': rooms})

class RoomListAPIView(APIView):
    def get(self, request):
        try:
            room_collection = get_room_collection()
            widget_collection = get_widget_collection()

            rooms_cursor = room_collection.find({})
            rooms = []

            for room in rooms_cursor:
                widget_id = room.get("widget_id")
                widget_data = {}

                if widget_id:
                    widget = widget_collection.find_one(
                        {"widget_id": widget_id},
                        {"_id": 0, "widget_id": 1, "name": 1}
                    )
                    if widget:
                        widget_data = {
                            "widget_id": widget.get("widget_id"),
                            "name": widget.get("name")
                        }

                # Inject widget info and remove raw widget_id
                room["widget"] = widget_data
                room.pop("_id", None)
                room.pop("widget_id", None)

                rooms.append(room)

            return Response(rooms, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




logger = logging.getLogger(__name__)

class RoomDetailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAgentOrSuperAdmin]

    def get(self, request, room_id):
        try:
            room_collection = get_room_collection()
            widget_collection = get_widget_collection()

            # Retrieve the room
            room = room_collection.find_one({"room_id": room_id})
            if not room:
                return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

            # Check object-level permissions
            for permission in self.permission_classes:
                if not permission().has_object_permission(request, self, room):
                    return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

            # Prepare widget info
            widget_id = room.get("widget_id")
            widget_data = {}
            if widget_id:
                widget = widget_collection.find_one(
                    {"widget_id": widget_id},
                    {"_id": 0, "widget_id": 1, "name": 1}
                )
                if widget:
                    widget_data = {
                        "widget_id": widget.get("widget_id"),
                        "name": widget.get("name")
                    }

            # Prepare response
            room.pop("_id", None)
            room.pop("widget_id", None)
            room["widget"] = widget_data

            return Response(room, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error retrieving room details")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class ChatMessagesByDateAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Retrieve chat messages by room_id and date.",
        manual_parameters=[
            openapi.Parameter(
                'room_id', openapi.IN_QUERY, description="The ID of the chat room", type=openapi.TYPE_STRING, required=True
            ),
            openapi.Parameter(
                'date', openapi.IN_QUERY, description="The date for which messages are to be retrieved (format: YYYY-MM-DD)", 
                type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description="List of messages for the specified date",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'messages': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    '_id': openapi.Schema(type=openapi.TYPE_STRING),
                                    'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                                    'timestamp': openapi.Schema(type=openapi.TYPE_STRING),
                                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                                    # Include other fields in the message object if applicable
                                }
                            )
                        )
                    }
                )
            ),
            400: openapi.Response(description="Bad request (missing parameters or invalid date format)"),
        }
    )
    def get(self, request):
        """
        Retrieves messages from a specified chat room on a given date.
        """
        room_id = request.GET.get('room_id')
        date_str = request.GET.get('date')  # format: YYYY-MM-DD

        if not room_id or not date_str:
            return Response({'error': 'room_id and date are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
            start_of_day = datetime(date.year, date.month, date.day)
            end_of_day = start_of_day + timedelta(days=1)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        # Assuming this function retrieves the MongoDB collection for chat messages
        collection = get_chat_collection()

        # Query to get messages from the specified room and date
        query = {
            'room_id': room_id,
            'timestamp': {'$gte': start_of_day, '$lt': end_of_day}
        }

        # Fetch messages
        messages = list(collection.find(query).sort('timestamp', 1))

        # Format the messages
        for msg in messages:
            msg['_id'] = str(msg['_id'])  # Convert ObjectId to string
            msg['timestamp'] = msg['timestamp'].isoformat()  # Format timestamp to ISO string

        # Return the messages as a response
        return Response({'messages': messages}, status=status.HTTP_200_OK)






@csrf_exempt  # Add this if you're having CSRF issues
@require_http_methods(["GET", "POST"])  # Allow both GET and POST
def test_widget_view(request):
    """
    View that integrates IP geolocation API to get IP information including flag, country, city
    """
    # Get client's IP address
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    # FIXED: Handle IP address from different sources
    client_ip = None
    
    if request.method == 'POST':
        try:
            # Parse JSON body for POST requests
            body = json.loads(request.body.decode('utf-8'))
            client_ip = body.get('ip_address')
            widget_id = body.get('widget_id')  # Get widget_id if needed
            
            # If no IP in body, try to get from headers
            if not client_ip:
                client_ip = get_client_ip(request)
                
        except json.JSONDecodeError:
            # Handle form data or invalid JSON
            client_ip = request.POST.get('ip_address') or get_client_ip(request)
    else:
        # GET request - get IP from query params or headers
        client_ip = request.GET.get('ip', get_client_ip(request))
    
    # FIXED: Better error handling for missing IP
    if not client_ip:
        error_response = {
            'error': 'IP address is required from frontend',
            'message': 'Please ensure your widget is sending the IP address'
        }
        return JsonResponse(error_response, status=400)
    
    # For testing purposes, you can also override with a test IP
    test_ip = request.GET.get('test_ip', client_ip)
    
    ip_info = None
    error_message = None
    
    # Handle local/localhost IPs
    if not test_ip or test_ip in ['127.0.0.1', 'localhost', '::1']:
        ip_info = {
            'ip': test_ip,
            'country': 'Local',
            'city': 'Local',
            'flag_emoji': '',
            'flag_url': '',
            'country_code': '',
            'region': 'Local',
            'timezone': '',
            'isp': 'Local',
        }
    else:
        try:
            # FIXED: Correct API URL construction with IP parameter
            api_url = f'https://ipwhois.pro/{test_ip}?key=8HaX4qcer2Ml9Hfc'
            print(f"DEBUG: API URL: {api_url}")
            
            response = requests.get(api_url, timeout=10)
            print("DEBUG: Response status:", response.status_code)
            print("DEBUG: Response from ipwhois.pro API:", response.text)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if API call was successful
                if data.get('success', True):  # Some APIs return success field
                    country_code = data.get('country_code', '').upper()
                    
                    # Construct flag data similar to your working class method
                    flag_data = None
                    if country_code and len(country_code) == 2:
                        flag_data = {
                            'emoji': ''.join(chr(ord(c) + 127397) for c in country_code),
                            'url': f"https://flagcdn.com/32x24/{country_code.lower()}.png",
                            'country_code': country_code
                        }
                    
                    # Extract the required information
                    ip_info = {
                        'ip': data.get('ip', test_ip),
                        'country': data.get('country', 'Unknown'),
                        'city': data.get('city', 'Unknown'),
                        'country_code': country_code,
                        'region': data.get('region', ''),
                        'timezone': data.get('timezone', ''),
                        'isp': data.get('isp', ''),
                        'flag_emoji': flag_data['emoji'] if flag_data else '',
                        'flag_url': flag_data['url'] if flag_data else '',
                        'flag': flag_data  # Complete flag object
                    }
                else:
                    error_message = f"API returned error: {data.get('message', 'Unknown error')}"
            else:
                error_message = f"API request failed with status code: {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            error_message = f"Error fetching IP information: {str(e)}"
        except json.JSONDecodeError:
            error_message = "Invalid JSON response from API"
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
    
    # FIXED: Handle both chat room creation and IP info requests
    if request.method == 'POST' and 'widget_id' in (json.loads(request.body.decode('utf-8')) if request.body else {}):
        # This is a chat room creation request
        # Generate a room ID (you should implement your room creation logic here)
        import uuid
        room_id = str(uuid.uuid4())
        
        # You might want to save this room to your database
        # Room.objects.create(room_id=room_id, widget_id=widget_id, ip_address=client_ip)
        
        response_data = {
            'room_id': room_id,
            'ip_info': ip_info,
            'status': 'success'
        }
        
        if error_message:
            response_data['ip_error'] = error_message
            
        return JsonResponse(response_data)
    
    # Prepare context for template (for GET requests or non-chat POST requests)
    context = {
        'ip_address': test_ip,
        'ip_info': ip_info,
        'error_message': error_message,
    }
    
    # Return JSON response for AJAX requests
    if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(context)
    
    # Return HTML template for regular requests
    return render(request, 'chat/test_widget.html', context)

class ChatMessagesAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Retrieve all chat messages for a specific room.",
        manual_parameters=[
            openapi.Parameter(
                'room_id', openapi.IN_PATH, description="The ID of the chat room", 
                type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description="List of chat messages",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'messages': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    '_id': openapi.Schema(type=openapi.TYPE_STRING),
                                    'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                                    'timestamp': openapi.Schema(type=openapi.TYPE_STRING),
                                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                                }
                            )
                        )
                    }
                )
            ),
            400: openapi.Response(description="Bad request, room_id is required"),
        }
    )
    def get(self, request, room_id):
        """Retrieve all chat messages for a specific room"""
        
        if not room_id:
            return Response({'error': 'room_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        collection = get_chat_collection()
        messages = list(collection.find({'room_id': room_id}).sort('timestamp', 1))
        
        for msg in messages:
            msg['_id'] = str(msg['_id'])
            msg['timestamp'] = msg['timestamp'].isoformat() if isinstance(msg['timestamp'], datetime) else msg['timestamp']
            # Ensure timestamp is in ISO format 
            if isinstance(msg['timestamp'], str):
                try:
                    msg['timestamp'] = datetime.fromisoformat(msg['timestamp']).isoformat()
                except ValueError:
                    pass
            # Convert timestamp to ISO format if it's a datetime object
            elif isinstance(msg['timestamp'], datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()

        return Response({'messages': messages}, status=status.HTTP_200_OK)



@api_view(['GET'])
@swagger_auto_schema(
    operation_description="Get all agent notes for a specific room.",
    manual_parameters=[
        openapi.Parameter(
            'agent', openapi.IN_QUERY, description="Specify whether the user is an agent ('true' or 'false')", 
            type=openapi.TYPE_STRING, required=True, enum=['true', 'false']
        ),
        openapi.Parameter(
            'room_id', openapi.IN_PATH, description="The ID of the room", 
            type=openapi.TYPE_STRING, required=True
        ),
    ],
    responses={
        200: openapi.Response(
            description="List of agent notes for the specified room",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'note_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                        'created_at': openapi.Schema(type=openapi.TYPE_STRING),
                        'updated_at': openapi.Schema(type=openapi.TYPE_STRING),
                        'note': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            )
        ),
        403: openapi.Response(description="Forbidden, only agents can access notes"),
    }
)
def get_agent_notes(request, room_id):
    """Get all agent notes for a specific room"""
    
    is_agent = request.GET.get('agent', 'false').lower() == 'true'
    
    if not is_agent:
        return Response({"error": "Only agents can access notes"}, status=status.HTTP_403_FORBIDDEN)
    
    notes_collection = get_agent_notes_collection()
    notes = list(notes_collection.find(
        {'room_id': room_id},
        {'_id': 0}  
    ).sort('created_at', 1))  
    
    for note in notes:
        if isinstance(note.get('created_at'), datetime):
            note['created_at'] = note['created_at'].isoformat()
        if isinstance(note.get('updated_at'), datetime):
            note['updated_at'] = note['updated_at'].isoformat()
    
    return Response(notes)



@api_view(['GET'])
@swagger_auto_schema(
    operation_description="Retrieve a specific note by its note_id within a specific room.",
    manual_parameters=[
        openapi.Parameter(
            'room_id', openapi.IN_PATH, description="The ID of the chat room", 
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'note_id', openapi.IN_PATH, description="The ID of the note to retrieve",
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'agent', openapi.IN_QUERY, description="Indicates if the requester is an agent (true/false)",
            type=openapi.TYPE_STRING, required=True, enum=['true', 'false']
        ),
    ],
    responses={
        200: openapi.Response(
            description="The specific note with its details",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    '_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'note_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'created_at': openapi.Schema(type=openapi.TYPE_STRING, description="Timestamp when the note was created"),
                    'updated_at': openapi.Schema(type=openapi.TYPE_STRING, description="Timestamp when the note was last updated"),
                    'note': openapi.Schema(type=openapi.TYPE_STRING, description="The content of the note"),
                }
            )
        ),
        403: openapi.Response(description="Forbidden, only agents can access notes"),
        404: openapi.Response(description="Note not found"),
    }
)
def get_note_by_id(request, room_id, note_id):
    """Retrieve a specific note by its note_id within a specific room"""
    is_agent = request.GET.get('agent', 'false').lower() == 'true'
    
    if not is_agent:
        return Response({"error": "Only agents can access notes"}, status=status.HTTP_403_FORBIDDEN)
    
    notes_collection = get_agent_notes_collection()
    
    note = notes_collection.find_one({"note_id": note_id, "room_id": room_id})
    
    if not note:
        return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)
    
    note['_id'] = str(note['_id'])
    
    if 'created_at' in note and isinstance(note['created_at'], datetime):
        note['created_at'] = note['created_at'].isoformat()
    
    if 'updated_at' in note and isinstance(note['updated_at'], datetime):
        note['updated_at'] = note['updated_at'].isoformat()
    
    return Response(note, status=status.HTTP_200_OK)



logger = logging.getLogger(__name__)
@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@swagger_auto_schema(
    operation_description="Create a new agent note",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'content': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="The content of the agent's note"
            )
        },
        required=['content']  # Correct usage: required as a list of fields
    ),
    responses={
        201: openapi.Response(description="Note created successfully"),
        400: openapi.Response(description="Bad request"),
        403: openapi.Response(description="Forbidden"),
        500: openapi.Response(description="Internal server error")
    }
)
def create_agent_note(request, room_id):
    """Create a new agent note for a specific room"""
    is_agent = request.GET.get('agent', 'false').lower() == 'true'
    
    if not is_agent:
        return Response({"error": "Only agents can create notes"}, status=status.HTTP_403_FORBIDDEN)
    
    note_content = request.data.get('content')
    if not note_content:
        return Response({"error": "Note content is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    note_id = generate_room_id()
    timestamp = datetime.utcnow()
    
    doc = {
        'note_id': note_id,
        'room_id': room_id,
        'sender': 'Agent',  # Simply use 'Agent' as the sender
        'content': note_content,
        'created_at': timestamp,
        'updated_at': timestamp
    }
    notes_collection = get_agent_notes_collection()
    result = notes_collection.insert_one(doc)
    
    if result.inserted_id:
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        if '_id' in doc:
            doc['_id'] = str(doc['_id'])
        logger.info(f"Returning created note: note_id={note_id}, room_id={room_id}")
        return Response(doc, status=status.HTTP_201_CREATED)
    else:
        return Response({"error": "Failed to create note"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['PUT'])
@swagger_auto_schema(
    operation_description="Update an existing agent note for a specific room.",
    manual_parameters=[
        openapi.Parameter(
            'room_id', openapi.IN_PATH, description="The ID of the chat room", 
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'note_id', openapi.IN_PATH, description="The ID of the note to be updated",
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'agent', openapi.IN_QUERY, description="Indicates if the requester is an agent (true/false)",
            type=openapi.TYPE_STRING, required=True, enum=['true', 'false']
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'content': openapi.Schema(type=openapi.TYPE_STRING, description="Updated content of the agent's note")
        },
        required=['content']
    ),
    responses={
        200: openapi.Response(
            description="Note updated successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'note_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'sender': openapi.Schema(type=openapi.TYPE_STRING),
                    'content': openapi.Schema(type=openapi.TYPE_STRING),
                    'created_at': openapi.Schema(type=openapi.TYPE_STRING),
                    'updated_at': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        ),
        400: openapi.Response(description="Bad request, note content is required"),
        403: openapi.Response(description="Forbidden, only agents can update notes"),
        404: openapi.Response(description="Note not found"),
    }
)
def update_agent_note(request, room_id, note_id):
    """Update an existing agent note"""
    is_agent = request.GET.get('agent', 'false').lower() == 'true'
    
    if not is_agent:
        return Response({"error": "Only agents can update notes"}, status=status.HTTP_403_FORBIDDEN)
    
    note_content = request.data.get('content')
    if not note_content:
        return Response({"error": "Note content is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    timestamp = datetime.utcnow()
    
    notes_collection = get_agent_notes_collection()
    result = notes_collection.update_one(
        {'note_id': note_id, 'room_id': room_id},
        {'$set': {
            'content': note_content,
            'updated_at': timestamp
        }}
    )
    
    if result.matched_count > 0:
        updated_note = notes_collection.find_one({'note_id': note_id}, {'_id': 0})
        
        if isinstance(updated_note.get('created_at'), datetime):
            updated_note['created_at'] = updated_note['created_at'].isoformat()
        if isinstance(updated_note.get('updated_at'), datetime):
            updated_note['updated_at'] = updated_note['updated_at'].isoformat()
            
        return Response(updated_note)
    else:
        return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)
    
    

@api_view(['DELETE'])
@swagger_auto_schema(
    operation_description="Delete an existing agent note for a specific room.",
    manual_parameters=[
        openapi.Parameter(
            'room_id', openapi.IN_PATH, description="The ID of the chat room", 
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'note_id', openapi.IN_PATH, description="The ID of the note to be deleted",
            type=openapi.TYPE_STRING, required=True
        ),
        openapi.Parameter(
            'agent', openapi.IN_QUERY, description="Indicates if the requester is an agent (true/false)",
            type=openapi.TYPE_STRING, required=True, enum=['true', 'false']
        ),
    ],
    responses={
        200: openapi.Response(
            description="Note deleted successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING)
                }
            )
        ),
        403: openapi.Response(description="Forbidden, only agents can delete notes"),
        404: openapi.Response(description="Note not found"),
    }
)
def delete_agent_note(request, room_id, note_id):
    """Delete an agent note"""
    is_agent = request.GET.get('agent', 'false').lower() == 'true'
    
    if not is_agent:
        return Response({"error": "Only agents can delete notes"}, status=status.HTTP_403_FORBIDDEN)
    
    notes_collection = get_agent_notes_collection()
    result = notes_collection.delete_one({
        'note_id': note_id,
        'room_id': room_id
    })
    
    if result.deleted_count > 0:
        return Response({"message": "Note deleted successfully"})
    else:
        return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)
    
    
import logging

logger = logging.getLogger(__name__)

# class AgentListAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):
#         try:
#             logger.info("Fetching agent list for superadmin")
            
#             agents = list(get_admin_collection().find(
#                 {"role": "agent"},
#                 {"_id": 0, "admin_id": 1, "email": 1, "created_at": 1}
#             ))

#             logger.debug(f"Found {len(agents)} agents")
#             return Response({"agents": agents}, status=200)

#         except Exception as e:
#             logger.error(f"Error fetching agent list: {str(e)}")
#             return Response({"error": "Internal server error"}, status=500)

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.conf import settings
import json
from functools import wraps
from wish_bot.db import get_room_collection, get_chat_collection

def rate_limit(max_requests=5, period=60):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not settings.DEBUG:  # Don't rate limit in development
                ip = request.META.get('REMOTE_ADDR')
                cache_key = f'rate_limit:{ip}:{request.path}'
                count = cache.get(cache_key, 0)
                
                if count >= max_requests:
                    return JsonResponse({
                        'error': 'Too many requests',
                        'retry_after': period
                    }, status=429)
                
                cache.set(cache_key, count + 1, period)
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator

@csrf_exempt
@require_http_methods(["POST"])
@rate_limit(max_requests=10, period=60)  # 10 requests per minute
def chat_history(request):
    try:
        # Verify Content-Type
        if request.content_type != 'application/json':
            return JsonResponse({
                'error': 'Content-Type must be application/json'
            }, status=415)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON payload'
            }, status=400)
        
        # Validate required fields
        required_fields = ['room_id', 'widget_id']
        if not all(field in data for field in required_fields):
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(required_fields)}'
            }, status=400)
        
        room_id = data['room_id']
        widget_id = data['widget_id']
        limit = int(data.get('limit', 0))  # Default to 0 (no limit)
        
        # Validate limit
        if limit < 0:
            return JsonResponse({
                'error': 'Limit must be a positive integer'
            }, status=400)
        
        # Verify room belongs to this widget
        room_collection = get_room_collection()
        room = room_collection.find_one({
            'room_id': room_id,
            'widget_id': widget_id
        })
        
        if not room:
            return JsonResponse({
                'error': 'Room not found or access denied'
            }, status=404)
        
        # Get messages
        chat_collection = get_chat_collection()
        query = {'room_id': room_id}
        
        # Get total count for reference
        total_count = chat_collection.count_documents(query)
        
        # Get messages sorted by timestamp (newest first)
        cursor = chat_collection.find(
            query,
            {
                '_id': 0,
                'room_id': 0,
                'form_data': 0  # Exclude sensitive form data
            }
        ).sort('timestamp', -1)  # Most recent first
        
        # Apply limit if specified
        if limit > 0:
            cursor = cursor.limit(limit)
        
        messages = list(cursor)
        
        # Convert ObjectId and datetime to strings
        # for message in messages:
        #     if 'timestamp' in message:
        #         message['timestamp'] = message['timestamp'].isoformat()
        for msg in messages:
            ts = msg.get('timestamp')
            if isinstance(ts, datetime):
                msg['timestamp'] = ts.isoformat()
            elif isinstance(ts, str):
                msg['timestamp'] = ts  # assume already serialized
            else:
                msg['timestamp'] = None
        
        # Reverse to get chronological order (oldest first)
        messages.reverse()
        
        return JsonResponse({
            'status': 'success',
            'room_id': room_id,
            'total_messages': total_count,
            'returned_messages': len(messages),
            'limit_applied': limit if limit > 0 else None,
            'messages': messages
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)