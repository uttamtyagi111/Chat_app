from wish_bot.db import get_room_collection,get_agent_notes_collection
from wish_bot.db import get_chat_collection
from datetime import datetime, timedelta
from utils.redis_client import redis_client
from django.shortcuts import render
from utils.random_id import generate_id 
import logging
import uuid
from rest_framework.permissions import AllowAny
import boto3
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes,authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.conf import settings


logger = logging.getLogger(__name__)

# WebSocket documentation for Swagger UI
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

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
#     room_id = generate_id()
#     room_collection = get_room_collection()

#     existing_room = room_collection.find_one({'room_id': room_id})
    
#     while existing_room:
#         room_id = generate_id()
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
        operation_description="Create a new chat room from client side and return the room ID",
        responses={200: openapi.Response('Room ID created or user connected with new room', schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'room_id': openapi.Schema(type=openapi.TYPE_STRING, description='Generated Room ID')
            }
        ))}
    )
    def post(self, request):
        room_id = generate_id()
        room_collection = get_room_collection()

        existing_room = room_collection.find_one({'room_id': room_id})
        
        while existing_room:
            room_id = generate_id()
            existing_room = room_collection.find_one({'room_id': room_id})

        room_collection.insert_one({
            'room_id': room_id,
            'is_active': True,
            'created_at': datetime.now(),
            'assigned_agent': None,
        })

        return Response({'room_id': room_id}, status=status.HTTP_201_CREATED)


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
    
    note_id = generate_id()
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