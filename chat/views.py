from wish_bot.db import get_room_collection,get_agent_notes_collection
from wish_bot.db import get_widget_collection,insert_with_timestamps
from wish_bot.db import get_chat_collection
from datetime import datetime, timedelta
from utils.redis_client import redis_client
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from utils.random_id import generate_room_id,generate_widget_id 
import logging
import uuid
import json
import boto3
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes,authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.conf import settings
# WebSocket documentation for Swagger UI
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


logger = logging.getLogger(__name__)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
import json
from bson import ObjectId  # If using MongoDB ObjectId (optional, depending on your setup)

# Assuming these helper functions exist in your codebase
# from your_module import get_widget_collection, generate_widget_id, generate_widget_code, insert_with_timestamps

@require_GET
def get_widget(request, widget_id=None):
    try:
        widget_collection = get_widget_collection()
        
        # If widget_id is provided, retrieve a single widget
        if widget_id:
            widget = widget_collection.find_one({"widget_id": widget_id})
            if not widget:
                return JsonResponse({"error": "Widget not found"}, status=404)
            
            # Convert MongoDB document to JSON-serializable format
            widget_response = {
                "widget_id": widget["widget_id"],
                "widget_type": widget["widget_type"],
                "name": widget["name"],
                "color": widget["color"],
                "language": widget["language"],
                "is_active": widget["is_active"],
                "created_at": str(widget.get("created_at", "")),
                "updated_at": str(widget.get("updated_at", "")),
            }
            
            # Generate the direct chat link
            base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
            widget_response["direct_chat_link"] = f"{base_domain}/direct-chat/{widget['widget_id']}"
            
            return JsonResponse(widget_response, status=200)
        
        # If no widget_id, return a list of all widgets
        widgets = widget_collection.find()
        widget_list = []
        for widget in widgets:
            widget_response = {
                "widget_id": widget["widget_id"],
                "widget_type": widget["widget_type"],
                "name": widget["name"],
                "color": widget["color"],
                "language": widget["language"],
                "is_active": widget["is_active"],
                "created_at": str(widget.get("created_at", "")),
                "updated_at": str(widget.get("updated_at", "")),
            }
            base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
            widget_response["direct_chat_link"] = f"{base_domain}/direct-chat/{widget['widget_id']}"
            widget_list.append(widget_response)
        
        return JsonResponse({"widgets": widget_list}, status=200)
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["PUT"])
def update_widget(request, widget_id):
    try:
        widget_collection = get_widget_collection()
        widget = widget_collection.find_one({"widget_id": widget_id})
        
        if not widget:
            return JsonResponse({"error": "Widget not found"}, status=404)
        
        # Parse the request body
        data = json.loads(request.body)
        widget_type = data.get("widget_type", widget["widget_type"])
        name = data.get("name", widget["name"])
        color = data.get("color", widget["color"])
        language = data.get("language", widget["language"])
        is_active = data.get("is_active", widget.get("is_active", False))
        
        # Validate required fields
        if not all([widget_type, name, color]):
            return JsonResponse({"error": "Missing required fields"}, status=400)
        
        # Update the widget
        updated_widget = {
            "widget_id": widget_id,
            "widget_type": widget_type,
            "name": name,
            "color": color,
            "language": language,
            "is_active": is_active,
            "created_at": widget["created_at"],  # Preserve the original created_at
            "updated_at": datetime.utcnow()  # Update the timestamp
        }
        
        widget_collection.update_one(
            {"widget_id": widget_id},
            {"$set": updated_widget}
        )
        
        # Generate the direct chat link
        base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
        direct_chat_link = f"{base_domain}/direct-chat/{widget_id}"
        
        return JsonResponse({
            "widget_id": widget_id,
            "widget_type": widget_type,
            "name": name,
            "color": color,
            "language": language,
            "is_active": is_active,
            "updated_at": updated_widget["updated_at"].isoformat(), 
            "direct_chat_link": direct_chat_link,
            "widget_code": generate_widget_code(widget_id, request),
        }, status=200)
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
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

@csrf_exempt
@require_POST
def create_widget(request):
    try:
        data = json.loads(request.body)
        widget_type = data.get("widget_type")
        name = data.get("name")
        color = data.get("color")
        language = data.get("language", "en")
        is_active = data.get("is_active", False)

        if not all([widget_type, name, color]):
            return JsonResponse({"error": "Missing required fields"}, status=400)
        widget_id = generate_widget_id()

        # Check for uniqueness
        widget_collection = get_widget_collection()
        while widget_collection.find_one({"widget_id": widget_id}):
            widget_id = generate_widget_id()
        # Create a new widget
        widget = {
            "widget_id": widget_id,
            "widget_type": widget_type,
            "name": name,
            "color": color,
            "language": language,
            "is_active": is_active,
        }
        insert_with_timestamps(widget_collection, widget)

        # Generate the direct chat link (only widget_id)
        base_domain = "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003"
        direct_chat_link = f"{base_domain}/direct-chat/{widget['widget_id']}"

        return JsonResponse({
            "widget_id": widget["widget_id"],
            "widget_type": widget["widget_type"],
            "name": widget["name"],
            "color": widget["color"],
            "language": widget["language"],
            "is_active": widget["is_active"],
            "direct_chat_link": direct_chat_link,
            "widget_code": generate_widget_code(widget["widget_id"],request),
        }, status=201)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# Helper function to generate widget code
def generate_widget_code(widget_id,request):
    base_domain = "http://localhost:8000" if "localhost" in request.get_host() else "http://208.87.134.149:8003"
    script_url = f"{base_domain}/static/widget.js?widget_id={widget_id}"
    return f"""
<!-- Start of Chat Widget Script -->
<script type="text/javascript">
var ChatWidget_API = ChatWidget_API || [], ChatWidget_LoadStart = new Date();
(function() {{
    var s1 = document.createElement("script"), s0 = document.getElementsByTagName("script")[0];
    s1.async = true;
    s1.src = "{script_url}";
    s1.charset = "UTF-8";
    s0.parentNode.insertBefore(s1, s0);
}})();
</script>
<!-- End of Chat Widget Script -->
"""
def direct_chat(request, widget_id):
    widget_collection = get_widget_collection()
    widget = widget_collection.find_one({"widget_id": widget_id})
    if not widget:
        return JsonResponse({"error": "Widget not found"}, status=404)

    context = {
        "widget_id": widget_id,
        "base_domain": "http://localhost:8000" if request.get_host().startswith("localhost") else "http://208.87.134.149:8003",
    }
    return render(request, "chat/direct_chat.html", context)

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

class UserChatAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Create a new chat room for a given widget ID and return the room ID and widget details",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID to associate the room with'),
            },
            required=['widget_id']
        ),
        responses={
            201: openapi.Response('Room created successfully', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'room_id': openapi.Schema(type=openapi.TYPE_STRING, description='Generated Room ID'),
                    'widget': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'widget_id': openapi.Schema(type=openapi.TYPE_STRING, description='Widget ID'),
                            'widget_type': openapi.Schema(type=openapi.TYPE_STRING, description='Type of the widget'),
                            'name': openapi.Schema(type=openapi.TYPE_STRING, description='Name of the widget'),
                            'color': openapi.Schema(type=openapi.TYPE_STRING, description='Color of the widget'),
                            'language': openapi.Schema(type=openapi.TYPE_STRING, description='Language of the widget'),
                        }
                    )
                }
            )),
            400: openapi.Response('Bad Request', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'error': openapi.Schema(type=openapi.TYPE_STRING, description='Error message')
                }
            )),
            404: openapi.Response('Widget Not Found', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'error': openapi.Schema(type=openapi.TYPE_STRING, description='Error message')
                }
            ))
        }
    )
    def post(self, request):
        widget_id = request.data.get("widget_id")
        print("Received widget_id:", widget_id)

        # Validate widget_id
        if not widget_id:
            print("No widget_id provided")
            return Response({"error": "Widget ID is required"}, status=status.HTTP_400_BAD_REQUEST)


        # Fetch widget collection
        widget_collection = get_widget_collection()
        room_collection = get_room_collection()

        # Validate widget existence
        widget = widget_collection.find_one({"widget_id": widget_id})
        if not widget:
            return Response({"error": "Widget not found"}, status=status.HTTP_404_NOT_FOUND)

        # Generate a unique room_id
        room_id = generate_room_id()
        existing_room = room_collection.find_one({'room_id': room_id})
        
        while existing_room:
            room_id = generate_room_id()
            existing_room = room_collection.find_one({'room_id': room_id})

        # Create a new room associated with the widget_id
        room_document=({
            'room_id': room_id,
            'widget_id': widget_id,  # Associate the room with the widget
            'is_active': True,
            'created_at': datetime.now(),
            'assigned_agent': None,
        })
        
        insert_with_timestamps(room_collection, room_document)
        # Prepare widget details to return
        widget_details = {
            "widget_id": widget["widget_id"],
            "widget_type": widget.get("widget_type"),
            "name": widget.get("name"),
            "color": widget.get("color"),
            "language": widget.get("language", "en"),
        }

        return Response({
            "room_id": room_id,
            "widget": widget_details
        }, status=status.HTTP_201_CREATED)


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

class AgentChatAPIView(APIView):
    @swagger_auto_schema(
        operation_description="Assign an agent to an existing chat room based on room_id",
        manual_parameters=[
            openapi.Parameter('room_id', openapi.IN_PATH, description="Room ID so that agent can connect to", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Agent assigned successfully', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'room_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'assigned_agent': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            404: "Room not found"
        }
    )
    def post(self, request, room_id):
        room_collection = get_room_collection()
        room = room_collection.find_one({'room_id': room_id})

        if room:
            room_collection.update_one(
                {'room_id': room_id},
                {'$set': {'assigned_agent': 'Agent 007'}}  # Replace with dynamic agent assignment if needed
            )
            return Response({
                'message': 'Agent assigned successfully.',
                'room_id': room_id,
                'assigned_agent': 'Agent 007',
            }, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        
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


class RoomDetailAPIView(APIView):
    def get(self, request, room_id):
        try:
            room_collection = get_room_collection()
            widget_collection = get_widget_collection()

            room = room_collection.find_one({"room_id": room_id})

            if not room:
                return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

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

            # Format response
            room.pop("_id", None)
            room.pop("widget_id", None)
            room["widget"] = widget_data

            return Response(room, status=status.HTTP_200_OK)

        except Exception as e:
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


from django.shortcuts import render

def test_widget_view(request):
    return render(request, 'chat/test_widget.html')

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