from ast import Is
from ctypes.wintypes import tagSIZE
import token
import traceback
from venv import logger
from django.http import JsonResponse
from django.test import tag
from pymongo.errors import DuplicateKeyError
from utils.random_id import generate_contact_id  # Import the contact ID generator
from wish_bot.db import  get_admin_collection, get_contact_collection, get_shortcut_collection, get_tag_collection, get_widget_collection # Import the contacts collection
import csv,io,json,uuid
from datetime import datetime
from pymongo.errors import PyMongoError  # Assuming PyMongo for MongoDB
from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
from django.core.serializers.json import DjangoJSONEncoder
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from authentication.utils import decode_token
from rest_framework.authentication import get_authorization_header
from wish_bot.db import get_room_collection,get_chat_collection 
from wish_bot.db import  get_mongo_client
from authentication.utils import (
    hash_password,jwt_required, validate_email_format,superadmin_required)
from drf_spectacular.utils import extend_schema,OpenApiResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from pymongo import ASCENDING, DESCENDING
from collections import defaultdict
from rest_framework.decorators import api_view
from  authentication.permissions import  IsSuperAdmin,IsAgentOrSuperAdmin

# Optional helper to get conversations collection
def get_conversations_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    return db['conversations']




@jwt_required# ✅ ensure user is authenticated
@superadmin_required
def agent_list(request):
    try:
        agents_collection = get_admin_collection()
        organization = request.GET.get('organization')  # Get query param

        query = {'role': 'agent'}
        if organization:
            query['organization'] = organization

        # Fetch only users with role 'agent'
        agents = list(agents_collection.find(query, {
            '_id': 0,  # exclude MongoDB internal ID
            'admin_id': 1,
            'name': 1,
            'email': 1,
            'role': 1,
            'organization': 1,
            'assigned_widgets': 1,
            'created_at': 1
        }))

        return JsonResponse({'agents': agents, 'total': len(agents)}, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch agents: {str(e)}'}, status=500)


from authentication.jwt_auth import JWTAuthentication
class AddAgentView(APIView):  
    authentication_classes = [JWTAuthentication]    
    permission_classes = [IsSuperAdmin]      

    @extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'example': 'John Doe'},
                    'email': {'type': 'string', 'format': 'email', 'example': 'john@example.com'},
                    'password': {'type': 'string', 'example': 'StrongPass@123'},
                    'assigned_widgets': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'example': ['widget_123', 'widget_456']
                    }
                },
                'required': ['name', 'email', 'password']
            }
        },
        responses={
            201: OpenApiResponse(response={"message": "Agent created successfully."}),
            400: OpenApiResponse(response={"message": "Agent already exists or invalid input."}),
            403: OpenApiResponse(response={"error": "Unauthorized"}),
            500: OpenApiResponse(description="Internal Server Error")
        },
        description="Only superadmin can add an agent. Requires name, email, and password."
    )
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return Response({"message": "Invalid JSON format"}, status=400)

        name = data.get('name', '').strip()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        assigned_widgets = data.get('assigned_widgets', [])
        organization = data.get('organization', None)

        if not isinstance(assigned_widgets, list):
            return Response({"message": "assigned_widgets must be a list"}, status=400)

        if not name or not email or not password:
            return Response({"message": "Name, Email and Password are required"}, status=400)

        if not validate_email_format(email):
            return Response({"message": "Invalid email format"}, status=400)

        try:
            agents_collection = get_admin_collection()
            
            # 🔒 Check for unique email
            if agents_collection.find_one({"email": email}):
                return Response({"message": "Agent with this email already exists."}, status=400)
            
            # 🔒 Check for unique name
            if agents_collection.find_one({"name": name}):
                return Response({"message": "Agent with this name already exists."}, status=400)

        except Exception as e:
            return Response({"message": "Database error while checking for existing agent"}, status=500)

        agent_data = {
            'name': name,
            'email': email,
            'role': 'agent',
            'admin_id': str(uuid.uuid4()),
            'password': hash_password(password),
            'assigned_widgets': assigned_widgets,
            'organization': organization,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_online': False,
            'last_active': None
        }

        try:
            result = agents_collection.insert_one(agent_data)
            if result.inserted_id:
                return Response({"message": f"Agent {name} created successfully"}, status=201)
            else:
                return Response({"message": "Failed to create agent"}, status=500)
        except Exception as e:
            return Response({"message": f"Error creating agent: {str(e)}"}, status=500)



class EditAgentAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []

    @extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'example': 'Jane Doe'},
                    'email': {'type': 'string', 'example': 'jane@example.com'},
                    'assigned_widgets': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'example': ['widget1', 'widget2']
                    },
                    'organization': {'type': 'string', 'example': 'Acme Inc.'}
                }
            }
        },
        responses={
            200: OpenApiResponse(response={'message': 'Agent updated successfully.'}),
            400: OpenApiResponse(description='Invalid input'),
            403: OpenApiResponse(description='Permission denied'),
            404: OpenApiResponse(description='Agent not found'),
            500: OpenApiResponse(description='Server error')
        },
        description="PATCH: Agent can edit name & email. Superadmin can also update assigned_widgets and organization."
    )
    def patch(self, request, agent_id):
        user = request.user
        role = user.get("role")
        token_admin_id = user.get("admin_id")

        agents_collection = get_admin_collection()

        try:
            agent = agents_collection.find_one({'admin_id': agent_id})
            if not agent:
                return Response({'detail': 'Agent not found'}, status=404)

            if role == "agent" and agent_id != token_admin_id:
                return Response({'detail': 'You can only edit your own profile'}, status=403)

            update_fields = {}
            name = request.data.get('name')
            email = request.data.get('email')
            assigned_widgets = request.data.get('assigned_widgets')
            organization = request.data.get('organization')

            # ✅ Common updates (for agent and superadmin)
            if name:
                update_fields['name'] = name

            if email:
                email = email.lower().strip()
                if not validate_email_format(email):
                    return Response({"message": "Invalid email format"}, status=400)

                duplicate = agents_collection.find_one({
                    'admin_id': {'$ne': agent_id},
                    'email': email
                })
                if duplicate:
                    return Response({'detail': 'Another agent with this email already exists.'}, status=400)

                update_fields['email'] = email

            # ✅ Superadmin-only updates
            if assigned_widgets is not None or organization is not None:
                if role != "superadmin":
                    return Response({'detail': 'Only superadmin can update widgets or organization'}, status=403)

                if assigned_widgets is not None:
                    update_fields['assigned_widgets'] = assigned_widgets

                if organization is not None:
                    update_fields['organization'] = organization

            if not update_fields:
                return Response({'message': 'No valid fields to update'}, status=400)

            update_fields['updated_at'] = datetime.utcnow()
            result = agents_collection.update_one({'admin_id': agent_id}, {'$set': update_fields})

            if result.modified_count == 0:
                return Response({'message': 'No changes made.'}, status=200)

            return Response({'message': 'Agent updated successfully.'}, status=200)

        except PyMongoError as e:
            return Response({'detail': f'Database error: {str(e)}'}, status=500)
        except Exception as e:
            return Response({'detail': f'Unexpected error: {str(e)}'}, status=500)


class DeleteAgentAPIView(APIView):
    authentication_classes = [JWTAuthentication]  # We are using custom auth
    permission_classes = [IsSuperAdmin]      # No DRF permission checks

    @extend_schema(
        responses={
            204: OpenApiResponse(description='Agent deleted successfully.'),
            403: OpenApiResponse(description='Unauthorized access'),
            404: OpenApiResponse(description='Agent not found.'),
            500: OpenApiResponse(description='Server error')
        },
        description="🗑️ Delete an agent by `agent_id`. Superadmin access only."
    )
    def delete(self, request, agent_id):
        try:
            agents_collection = get_admin_collection()
            agent = agents_collection.find_one({'admin_id': agent_id})
            if not agent:
                return Response({'detail': 'Agent not found.'}, status=404)

            agents_collection.delete_one({'admin_id': agent_id})
            logger.info(f"🗑️ Agent {agent_id} deleted successfully by {request.user.get('email', 'unknown user')}"      )
            return Response({'message': f"Agent {agent_id} deleted successfully by {request.user.get('email')}"}, status=200)
        except PyMongoError as e:
            return Response({'detail': f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return Response({'detail': f"Unexpected error: {str(e)}"}, status=500)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from authentication.jwt_auth import JWTAuthentication
from wish_bot.db import get_admin_collection
from drf_spectacular.utils import extend_schema, OpenApiResponse
import traceback

class AgentDetailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []  # Role-based access handled manually

    @extend_schema(
        summary="Get agent or superadmin details",
        description="Superadmin can view anyone. Agents can view their own profile only.",
        responses={
            200: OpenApiResponse(response={
                'type': 'object',
                'properties': {
                    'agent': {'type': 'object'}
                }
            }),
            403: OpenApiResponse(description="Unauthorized access"),
            404: OpenApiResponse(description="Agent not found"),
            500: OpenApiResponse(description="Internal server error")
        }
    )
    def get(self, request, agent_id=None):
        try:
            user = request.user
            role = user.get("role")
            token_admin_id = user.get("admin_id")

            print("🔐 JWT User Payload:", user)
            print("👤 Role:", role)
            print("🔎 agent_id from URL:", agent_id)

            # Determine whose profile to fetch
            if not agent_id:
                agent_id = token_admin_id  # Fallback to own profile

            if role == "agent" and agent_id != token_admin_id:
                print("❌ Agent trying to access another profile")
                return Response({'error': 'Forbidden'}, status=403)

            agents_collection = get_admin_collection()

            # Superadmin can access any profile (no role restriction)
            query = {'admin_id': agent_id}
            if role == "agent":
                query['role'] = 'agent'  # Enforce only agent records for agents

            agent = agents_collection.find_one(query)
            if not agent:
                print("❌ Agent not found in DB")
                return Response({'error': 'Agent not found'}, status=404)

            print("✅ Agent found:", agent.get("name", "No Name"))
            agent['_id'] = str(agent['_id'])  # MongoDB ObjectId -> str
            agent['is_self'] = (agent_id == token_admin_id)

            return Response({'agent': agent}, status=200)

        except Exception as e:
            print("🔥 Exception in AgentDetailAPIView:", str(e))
            traceback.print_exc()
            return Response({'error': f"Internal error: {str(e)}"}, status=500)


import logging
logger = logging.getLogger(__name__)



# @jwt_required
# def conversation_list(request):
#     try:
#         user = request.user
#         role = user.get('role')
#         admin_id = user.get('admin_id')  # You still have this in the JWT payload

#         assigned_widgets = []
#         if role == 'agent':
#             # 🔍 Fetch latest assigned widgets from the database
#             user_record = get_admin_collection().find_one({'admin_id': admin_id})
#             if user_record:
#                 assigned_widgets = user_record.get('assigned_widgets', [])
#                 if isinstance(assigned_widgets, str):
#                     assigned_widgets = [assigned_widgets]

#         room_collection = get_room_collection()

#         pipeline = []

#         # 🔐 Role-based filter
#         if role == 'agent':
#             pipeline.append({
#                 "$match": {
#                     "widget_id": {"$in": assigned_widgets}
#                 }
#             })

#         pipeline += [
#             {"$sort": {"created_at": DESCENDING}},

#             # 🔗 Join widget info
#             {
#                 "$lookup": {
#                     "from": "widgets",
#                     "localField": "widget_id",
#                     "foreignField": "widget_id",
#                     "as": "widget"
#                 }
#             },
#             {"$unwind": {"path": "$widget", "preserveNullAndEmptyArrays": True}},

#             # 🧮 Get last message, last timestamp, total messages from messages array
#             {
#                 "$addFields": {
#                     "total_messages": { "$size": { "$ifNull": ["$messages", []] } },
#                     "last_message_obj": {
#                         "$arrayElemAt": [
#                             { "$slice": ["$messages", -1] },
#                             0
#                         ]
#                     }
#                 }
#             },

#             # 🔗 Lookup agent details from admin collection
#             {
#                 "$lookup": {
#                     "from": "admins",
#                     "localField": "assigned_agent",
#                     "foreignField": "admin_id",
#                     "as": "agent"
#                 }
#             },
#             {"$unwind": {"path": "$agent", "preserveNullAndEmptyArrays": True}},

#             {
#                 "$project": {
#                     "_id": 0,
#                     "room_id": 1,
#                     "contact_id": 1,
#                     "assigned_agent": 1,
#                     "tags": 1,
#                     "ip": "$user_location.user_ip",
#                     "widget_id": 1,
#                     "is_active": 1,
#                     "created_at": 1,
#                     "updated_at": 1,
#                     "user_location": 1,
#                     "total_messages": 1,

#                     "last_message": "$last_message_obj.message",
#                     "last_timestamp": "$last_message_obj.timestamp",

#                     "widget": {
#                         "widget_id": "$widget.widget_id",
#                         "name": "$widget.name",
#                         "is_active": "$widget.is_active",
#                         "created_at": "$widget.created_at"
#                     },

#                     "agent": {
#                         "admin_id": "$agent.admin_id",
#                         "name": "$agent.name",
#                         "email": "$agent.email",
#                         "role": "$agent.role",
#                         "is_online": "$agent.is_online",
#                         "organization": "$agent.organization"
#                     }
#                 }
#             },

#             { "$sort": { "last_timestamp": DESCENDING } }
#         ]

#         results = list(room_collection.aggregate(pipeline))

#         # 🧽 Format datetime fields
#         for room in results:
#             for key in ['created_at', 'updated_at', 'last_timestamp']:
#                 if key in room and isinstance(room[key], datetime):
#                     room[key] = room[key].isoformat()

#             if room.get("widget") and isinstance(room["widget"].get("created_at"), datetime):
#                 room["widget"]["created_at"] = room["widget"]["created_at"].isoformat()

#         return JsonResponse({
#             "rooms": results,
#             "total_count": len(results)
#         }, status=200)

#     except Exception as e:
#         return JsonResponse({
#             "error": f"Error fetching rooms: {str(e)}",
#             "rooms": [],
#             "total_count": 0
#         }, status=500)



# @jwt_required
# def chat_room_view(request, room_id):
#     try:
#         user = request.jwt_user
#         role = user.get("role")
#         admin_id = user.get("admin_id")

#         chat_collection = get_chat_collection()
#         rooms_collection = get_room_collection()
#         # widgets_collection = get_widget_collection()
#         agents_collection = get_admin_collection()

#         # Fetch the room to get widget_id
#         room = rooms_collection.find_one({"room_id": room_id})
#         if not room:
#             return JsonResponse({
#                 'success': False,
#                 'error': 'Room not found',
#                 'messages': [],
#                 'room_id': room_id
#             }, status=404)

#         widget_id = room.get("widget_id")
#         assigned_agent = room.get("assigned_agent")
#         tags = room.get("tags", [])

#         # Agent access check
#         if role == "agent":
#             agent = agents_collection.find_one({"admin_id": admin_id})
#             assigned_widgets = agent.get("assigned_widgets", []) if agent else []

#             if widget_id not in assigned_widgets:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Access denied. You are not allowed to access this room.',
#                     'messages': [],
#                     'room_id': room_id
#                 }, status=403)

#         # Fetch messages for the room
#         messages = list(chat_collection.find({'room_id': room_id}).sort('timestamp', ASCENDING))

#         for msg in messages:
#             msg['_id'] = str(msg['_id'])
#             if isinstance(msg['timestamp'], datetime):
#                 msg['timestamp'] = msg['timestamp'].isoformat()

#         return JsonResponse({
#             'success': True,
#             'messages': messages,
#             'room_id': room_id,
#             'tags': tags,
#             'assigned_agent': assigned_agent,
#             'widget_id': widget_id,
#         })

#     except Exception as e:
#         return JsonResponse({
#             'success': False,
#             'error': f"Failed to load chat messages: {str(e)}",
#             'messages': [],
#             'room_id': room_id
#         }, status=500)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from datetime import datetime
from pymongo import ASCENDING, DESCENDING
import json
from wish_bot.db import (
    get_room_collection,
    get_chat_collection,
    get_contact_collection,
    get_admin_collection,
    get_trigger_collection,
    get_widget_collection
)
from utils.redis_client import redis_client
  # Assuming you have this decorator


@jwt_required
def conversation_list(request):  # Changed from enhanced_conversation_list
    """Enhanced version of your conversation_list with additional WebSocket-like data"""
    try:
        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        assigned_widgets = []
        if role == 'agent':
            user_record = get_admin_collection().find_one({'admin_id': admin_id})
            if user_record:
                assigned_widgets = user_record.get('assigned_widgets', [])
                if isinstance(assigned_widgets, str):
                    assigned_widgets = [assigned_widgets]

        room_collection = get_room_collection()
        contact_collection = get_contact_collection()

        pipeline = []

        # Role-based filter
        if role == 'agent':
            pipeline.append({
                "$match": {
                    "widget_id": {"$in": assigned_widgets}
                }
            })

        pipeline += [
            {"$sort": {"created_at": DESCENDING}},

            # Join widget info
            {
                "$lookup": {
                    "from": "widgets",
                    "localField": "widget_id",
                    "foreignField": "widget_id",
                    "as": "widget"
                }
            },
            {"$unwind": {"path": "$widget", "preserveNullAndEmptyArrays": True}},

            # Join contact info
            {
                "$lookup": {
                    "from": "contacts",
                    "localField": "contact_id",
                    "foreignField": "contact_id",
                    "as": "contact"
                }
            },
            {"$unwind": {"path": "$contact", "preserveNullAndEmptyArrays": True}},

            # Get last message, last timestamp, total messages from messages array
            {
                "$addFields": {
                    "total_messages": { "$size": { "$ifNull": ["$messages", []] } },
                    "last_message_obj": {
                        "$arrayElemAt": [
                            { "$slice": ["$messages", -1] },
                            0
                        ]
                    }
                }
            },

            # Lookup agent details from admin collection
            {
                "$lookup": {
                    "from": "admins",
                    "localField": "assigned_agent",
                    "foreignField": "admin_id",
                    "as": "agent"
                }
            },
            {"$unwind": {"path": "$agent", "preserveNullAndEmptyArrays": True}},

            {
                "$project": {
                    "_id": 0,
                    "room_id": 1,
                    "contact_id": 1,
                    "assigned_agent": 1,
                    "tags": 1,
                    "ip": "$user_location.user_ip",
                    "widget_id": 1,
                    "is_active": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "user_location": 1,
                    "total_messages": 1,

                    "last_message": "$last_message_obj.message",
                    "last_timestamp": "$last_message_obj.timestamp",

                    "widget": {
                        "widget_id": "$widget.widget_id",
                        "name": "$widget.name",
                        "is_active": "$widget.is_active",
                        "created_at": "$widget.created_at"
                    },

                    "agent": {
                        "admin_id": "$agent.admin_id",
                        "name": "$agent.name",
                        "email": "$agent.email",
                        "role": "$agent.role",
                        "is_online": "$agent.is_online",
                        "organization": "$agent.organization"
                    },

                    # Contact information
                    "contact": {
                        "contact_id": "$contact.contact_id",
                        "name": "$contact.name",
                        "email": "$contact.email",
                        "phone": "$contact.phone"
                    }
                }
            },

            { "$sort": { "last_timestamp": DESCENDING } }
        ]

        results = list(room_collection.aggregate(pipeline))

        # Add unread counts from Redis (like WebSocket does)
        for room in results:
            room_id = room['room_id']
            unread_key = f'unread:{room_id}'
            room['unread_count'] = int(redis_client.get(unread_key) or 0)
            
            # Add typing status from Redis
            typing_key = f'typing:{room_id}:*'
            typing_users = []
            for key in redis_client.scan_iter(match=typing_key):
                typing_content = redis_client.get(key)
                if typing_content:
                    user_id = key.split(':')[-1]
                    typing_users.append({
                        'user_id': user_id,
                        'content': typing_content
                    })
            room['typing_users'] = typing_users

            # Format datetime fields
            for key in ['created_at', 'updated_at', 'last_timestamp']:
                if key in room and isinstance(room[key], datetime):
                    room[key] = room[key].isoformat()

            if room.get("widget") and isinstance(room["widget"].get("created_at"), datetime):
                room["widget"]["created_at"] = room["widget"]["created_at"].isoformat()

        return JsonResponse({
            "rooms": results,
            "total_count": len(results)
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "error": f"Error fetching rooms: {str(e)}",
            "rooms": [],
            "total_count": 0
        }, status=500)


@jwt_required
def chat_room_view(request, room_id):  # Changed from enhanced_chat_room_view
    """Enhanced version of your chat_room_view with additional WebSocket-like data"""
    try:
        user = request.jwt_user
        role = user.get("role")
        admin_id = user.get("admin_id")

        chat_collection = get_chat_collection()
        rooms_collection = get_room_collection()
        agents_collection = get_admin_collection()
        contact_collection = get_contact_collection()

        # Fetch the room to get widget_id
        room = rooms_collection.find_one({"room_id": room_id})
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found',
                'messages': [],
                'room_id': room_id
            }, status=404)

        widget_id = room.get("widget_id")
        assigned_agent = room.get("assigned_agent")
        tags = room.get("tags", [])
        contact_id = room.get("contact_id")

        # Agent access check
        if role == "agent":
            agent = agents_collection.find_one({"admin_id": admin_id})
            assigned_widgets = agent.get("assigned_widgets", []) if agent else []

            if widget_id not in assigned_widgets:
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. You are not allowed to access this room.',
                    'messages': [],
                    'room_id': room_id
                }, status=403)

        # Fetch messages for the room
        messages = list(chat_collection.find({'room_id': room_id}).sort('timestamp', ASCENDING))

        for msg in messages:
            msg['_id'] = str(msg['_id'])
            if isinstance(msg['timestamp'], datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()

        # Get contact information
        contact_info = {}
        if contact_id:
            contact = contact_collection.find_one({'contact_id': contact_id})
            if contact:
                contact_info = {
                    'contact_id': contact.get('contact_id'),
                    'name': contact.get('name', ''),
                    'email': contact.get('email', ''),
                    'phone': contact.get('phone', '')
                }

        # Get unread count and reset it if agent is viewing
        unread_key = f'unread:{room_id}'
        unread_count = int(redis_client.get(unread_key) or 0)
        
        # Reset unread count when agent views the room
        if role == 'agent':
            redis_client.delete(unread_key)

        # Get typing status
        typing_key = f'typing:{room_id}:*'
        typing_users = []
        for key in redis_client.scan_iter(match=typing_key):
            typing_content = redis_client.get(key)
            if typing_content:
                user_id = key.split(':')[-1]
                typing_users.append({
                    'user_id': user_id,
                    'content': typing_content
                })

        # Get agent info if assigned
        agent_info = {}
        if assigned_agent:
            agent = agents_collection.find_one({'admin_id': assigned_agent})
            if agent:
                agent_info = {
                    'admin_id': agent.get('admin_id'),
                    'name': agent.get('name'),
                    'email': agent.get('email'),
                    'is_online': agent.get('is_online', False)
                }

        return JsonResponse({
            'success': True,
            'messages': messages,
            'room_id': room_id,
            'tags': tags,
            'assigned_agent': assigned_agent,
            'widget_id': widget_id,
            'contact': contact_info,
            'agent': agent_info,
            'unread_count': unread_count,
            'typing_users': typing_users,
            'total_messages': len(messages),
            'is_active': room.get('is_active', False)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Failed to load chat messages: {str(e)}",
            'messages': [],
            'room_id': room_id
        }, status=500)



@jwt_required
def get_last_message(request, room_id):
    """API to get the last message with timestamp and sender information for a specific room"""
    try:
        user = request.jwt_user
        role = user.get("role")
        admin_id = user.get("admin_id")

        chat_collection = get_chat_collection()
        rooms_collection = get_room_collection()
        agents_collection = get_admin_collection()
        contact_collection = get_contact_collection()

        # Fetch the room to verify it exists and get widget_id
        room = rooms_collection.find_one({"room_id": room_id})
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found',
                'room_id': room_id
            }, status=404)

        widget_id = room.get("widget_id")

        # Access control based on role
        if role == "agent":
            # Agent access check - only assigned widgets
            agent = agents_collection.find_one({"admin_id": admin_id})
            if not agent:
                return JsonResponse({
                    'success': False,
                    'error': 'Agent not found',
                    'room_id': room_id
                }, status=403)
                
            assigned_widgets = agent.get("assigned_widgets", [])
            if widget_id not in assigned_widgets:
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. You are not allowed to access this room.',
                    'room_id': room_id
                }, status=403)
                
        elif role == "superadmin":
            # Superadmin has access to all rooms (no restrictions)
            pass
        else:
            # Unknown role
            return JsonResponse({
                'success': False,
                'error': 'Invalid role. Only agent and superadmin roles are supported.',
                'room_id': room_id
            }, status=403)

        # Fetch the last message for the room
        last_message = chat_collection.find_one(
            {'room_id': room_id}, 
            sort=[('timestamp', -1)]  # Sort by timestamp descending to get the latest
        )

        if not last_message:
            return JsonResponse({
                'success': True,
                'message': 'No messages found in this room',
                'room_id': room_id,
                'last_message': None
            })

        # Convert ObjectId to string
        last_message['_id'] = str(last_message['_id'])
        
        # Handle timestamp conversion
        timestamp = last_message.get('timestamp')
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Get sender information based on your message format
        sender = last_message.get('sender', 'Unknown')
        contact_id = last_message.get('contact_id')
        
        # Determine sender info based on the sender field and contact_id
        sender_info = {}
        
        if sender == 'User' and contact_id:
            # This is a message from a contact/user
            contact = contact_collection.find_one({'contact_id': contact_id})
            if contact:
                sender_info = {
                    'type': 'contact',
                    'id': contact_id,
                    'name': contact.get('name', 'Unknown Contact'),
                    'email': contact.get('email', ''),
                    'phone': contact.get('phone', '')
                }
            else:
                sender_info = {
                    'type': 'contact',
                    'id': contact_id,
                    'name': 'Unknown Contact'
                }
        elif sender != 'User':
            # This might be an agent message
            # Try to find agent by name or other identifier
            agent = agents_collection.find_one({'name': sender})
            if agent:
                sender_info = {
                    'type': 'agent',
                    'id': agent.get('admin_id'),
                    'name': agent.get('name', sender),
                    'email': agent.get('email', ''),
                    'is_online': agent.get('is_online', False)
                }
            else:
                sender_info = {
                    'type': 'agent',
                    'id': None,
                    'name': sender
                }
        else:
            # Default case
            sender_info = {
                'type': 'unknown',
                'id': contact_id,
                'name': sender
            }

        # Prepare the response with last message details matching your format
        response_data = {
            'success': True,
            'room_id': room_id,
            'last_message': {
                'message_id': last_message.get('message_id', str(last_message['_id'])),
                'content': last_message.get('message', ''),
                'timestamp': timestamp,
                'sender': sender_info,
                'delivered': last_message.get('delivered', False),
                'seen': last_message.get('seen', False),
                'seen_at': last_message.get('seen_at'),
                'file_url': last_message.get('file_url', ''),
                'file_name': last_message.get('file_name', ''),
                'is_shortcut': last_message.get('is_shortcut', False),
                'shortcut_id': last_message.get('shortcut_id'),
                'suggested_replies': last_message.get('suggested_replies', []),
                'created_at': last_message.get('created_at'),
                'updated_at': last_message.get('updated_at')
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Failed to get last message: {str(e)}",
            'room_id': room_id
        }, status=500)


@jwt_required
def contact_list_api(request):
    """API to fetch contacts with filtering"""
    try:
        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # Get query parameters
        widget_id = request.GET.get('widget_id')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))

        contact_collection = get_contact_collection()
        
        # Build query filter
        contact_filter = {}
        
        # Role-based access control
        if role == 'agent':
            agent = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = agent.get('assigned_widgets', []) if agent else []
            
            if widget_id:
                if widget_id not in assigned_widgets:
                    return JsonResponse({
                        'success': False,
                        'error': 'Access denied for this widget'
                    }, status=403)
                contact_filter['widget_id'] = widget_id
            else:
                contact_filter['widget_id'] = {'$in': assigned_widgets}
        elif widget_id:
            contact_filter['widget_id'] = widget_id

        # Get total count
        total_count = contact_collection.count_documents(contact_filter)

        # Fetch contacts with pagination
        contacts = list(contact_collection.find(
            contact_filter,
            {'_id': 0}
        ).sort('created_at', DESCENDING).skip(offset).limit(limit))

        # Format datetime fields
        for contact in contacts:
            for key in ['timestamp', 'created_at', 'updated_at']:
                if key in contact and isinstance(contact[key], datetime):
                    contact[key] = contact[key].isoformat()

        return JsonResponse({
            'success': True,
            'contacts': contacts,
            'total_count': total_count,
            'returned_count': len(contacts),
            'offset': offset,
            'limit': limit
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Error fetching contacts: {str(e)}"
        }, status=500)


@jwt_required
def room_stats_api(request):
    """API to fetch room statistics with role-based access"""
    try:
        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        room_collection = get_room_collection()
        chat_collection = get_chat_collection()
        contact_collection = get_contact_collection()

        # Build base filter for role-based access
        base_filter = {}
        if role == 'agent':
            agent = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = agent.get('assigned_widgets', []) if agent else []
            base_filter['widget_id'] = {'$in': assigned_widgets}

        # Get basic counts
        total_rooms = room_collection.count_documents(base_filter)
        active_rooms = room_collection.count_documents({**base_filter, 'is_active': True})
        
        # Get contacts count
        contact_filter = {}
        if role == 'agent':
            contact_filter['widget_id'] = {'$in': assigned_widgets}
        total_contacts = contact_collection.count_documents(contact_filter)

        # Get messages count
        room_ids = [room['room_id'] for room in room_collection.find(base_filter, {'room_id': 1})]
        total_messages = chat_collection.count_documents({'room_id': {'$in': room_ids}})

        # Get total unread count across accessible rooms
        total_unread = 0
        for room in room_collection.find({**base_filter, 'is_active': True}):
            unread_key = f'unread:{room["room_id"]}'
            total_unread += int(redis_client.get(unread_key) or 0)

        # Get agent assignment stats
        assigned_rooms = room_collection.count_documents({
            **base_filter,
            'assigned_agent': {'$exists': True, '$ne': None}
        })

        stats = {
            'total_rooms': total_rooms,
            'active_rooms': active_rooms,
            'total_contacts': total_contacts,
            'total_messages': total_messages,
            'total_unread': total_unread,
            'assigned_rooms': assigned_rooms,
            'unassigned_rooms': active_rooms - assigned_rooms,
            'accessible_widgets': len(assigned_widgets) if role == 'agent' else 'all'
        }

        return JsonResponse({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Error fetching stats: {str(e)}"
        }, status=500)


@jwt_required
def mark_messages_seen_api(request, room_id):
    """API to mark messages as seen"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # Role-based access check
        if role == 'agent':
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': room_id})
            if not room:
                return JsonResponse({'error': 'Room not found'}, status=404)

            agent = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = agent.get('assigned_widgets', []) if agent else []
            
            if room.get('widget_id') not in assigned_widgets:
                return JsonResponse({'error': 'Access denied'}, status=403)

        # Mark messages as seen
        chat_collection = get_chat_collection()
        result = chat_collection.update_many(
            {'room_id': room_id, 'seen': False},
            {'$set': {'seen': True, 'seen_at': datetime.utcnow()}}
        )

        # Reset unread count
        unread_key = f'unread:{room_id}'
        redis_client.delete(unread_key)

        return JsonResponse({
            'success': True,
            'messages_marked': result.modified_count
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Error marking messages as seen: {str(e)}"
        }, status=500)
        




###############ended#######



@jwt_required
def widget_conversations(request, widget_id):
    try:
        user = request.user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # 🔍 Dynamically fetch assigned widgets for agents
        if role == 'agent':
            user_record = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = user_record.get('assigned_widgets', []) if user_record else []
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]

            if widget_id not in assigned_widgets:
                return JsonResponse({"error": "Access denied for this widget"}, status=403)


        collection = get_chat_collection()

        pipeline = [
            {"$sort": {"timestamp": DESCENDING}},
            {
                "$group": {
                    "_id": "$room_id",
                    "last_message": {"$first": "$message"},
                    "last_timestamp": {"$first": "$timestamp"},
                    "total_messages": {"$sum": 1},
                }
            },
            {
                "$lookup": {
                    "from": "rooms",
                    "localField": "_id",
                    "foreignField": "room_id",
                    "as": "room"
                }
            },
            {"$unwind": {"path": "$room", "preserveNullAndEmptyArrays": True}},
            {"$match": {"room.widget_id": widget_id}},
            {
                "$lookup": {
                    "from": "widgets",
                    "localField": "room.widget_id",
                    "foreignField": "widget_id",
                    "as": "widget"
                }
            },
            {"$unwind": {"path": "$widget", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "room_id": "$_id",
                    "last_message": 1,
                    "last_timestamp": 1,
                    "total_messages": 1,
                    "widget": {
                        "widget_id": "$widget.widget_id",
                        "name": "$widget.name",
                        "is_active": "$widget.is_active",
                        "created_at": "$widget.created_at"
                    }
                }
            },
            {"$sort": {"last_timestamp": DESCENDING}}
        ]

        conversations = list(collection.aggregate(pipeline))

        for convo in conversations:
            if isinstance(convo.get('last_timestamp'), datetime):
                convo['last_timestamp'] = convo['last_timestamp'].isoformat()
            if not convo.get('widget'):
                convo['widget'] = {
                    'widget_id': '',
                    'name': 'No Widget',
                    'is_active': False,
                    'created_at': ''
                }
            elif isinstance(convo['widget'].get('created_at'), datetime):
                convo['widget']['created_at'] = convo['widget']['created_at'].isoformat()

        return JsonResponse({
            "conversations": conversations,
            "total_count": len(conversations),
            "widget_id": widget_id
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "error": f"Error fetching conversations for widget {widget_id}: {str(e)}",
            "conversations": [],
            "total_count": 0
        }, status=500)




@jwt_required
def get_shortcuts_by_widget(request, widget_id):
    try:
        user = request.user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # Access control for agents
        if role == 'agent':
            user_record = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = user_record.get('assigned_widgets', []) if user_record else []
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({"error": "Access denied for this widget"}, status=403)

        shortcuts = list(get_shortcut_collection().find({"widget_id": widget_id}, {"_id": 0}))
        return JsonResponse({"shortcuts": shortcuts}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@jwt_required
def get_tags_by_widget(request, widget_id):
    try:
        user = request.user
        role = user.get('role')
        admin_id = user.get('admin_id')

        if role == 'agent':
            user_record = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = user_record.get('assigned_widgets', []) if user_record else []
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({"error": "Access denied for this widget"}, status=403)

        tags = list(get_tag_collection().find({"widget_id": widget_id}, {"_id": 0}))
        return JsonResponse({"tags": tags}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)





@jwt_required
def get_triggers_by_widget(request, widget_id):
    try:
        user = request.user
        role = user.get('role')
        admin_id = user.get('admin_id')

        if role == 'agent':
            user_record = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = user_record.get('assigned_widgets', []) if user_record else []
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({"error": "Access denied for this widget"}, status=403)

        triggers = list(get_trigger_collection().find({"widget_id": widget_id}, {"_id": 0}))
        return JsonResponse({"triggers": triggers}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



class ContactListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []
    # @jwt_required
    def get(self, request):
        user = request.user
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        role = user.get("role")
        token_admin_id = user.get("admin_id")

        widget_id = request.query_params.get('widget_id')
        contact_id = request.query_params.get('contact_id')
        search = request.query_params.get('search')
        agent_id = request.query_params.get('agent_id') if role == 'superadmin' else token_admin_id

        query = {}

        if contact_id:
            query['contact_id'] = contact_id

        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'phone': {'$regex': search, '$options': 'i'}},
                {'secondary_email': {'$regex': search, '$options': 'i'}},
            ]

        if role == 'agent':
            agent = get_admin_collection().find_one({'admin_id': token_admin_id})
            allowed_widgets = agent.get('assigned_widgets', [])
            if widget_id:
                if widget_id not in allowed_widgets:
                    return Response({'error': 'Access denied to this widget'}, status=403)
                query['widget_id'] = widget_id
            else:
                query['widget_id'] = {'$in': allowed_widgets}

        elif role == 'superadmin':
            if agent_id:
                query['agent_id'] = agent_id
            if widget_id:
                query['widget_id'] = widget_id

        contacts = list(get_contact_collection().find(query))

        for c in contacts:
            c['_id'] = str(c['_id'])

            # Fetch agent data (only needed fields)
            agent = get_admin_collection().find_one({'admin_id': c.get('agent_id')}, {'_id': 0, 'name': 1, 'email': 1, 'role': 1})
            c['agent'] = agent if agent else {}

            # Fetch widget data
            widget = get_widget_collection().find_one({'widget_id': c.get('widget_id')}, {'_id': 0, 'name': 1, 'widget_type': 1, 'is_active': 1, 'created_at': 1})
            c['widget'] = widget if widget else {}

        return Response(contacts)



    # @jwt_required
    def post(self, request):
        user = request.user
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        # Ensure user is authenticated and has a role
        
        role = user.get("role")
        token_admin_id = user.get("admin_id")

        data = request.data
        required_fields = ['widget_id']

        for field in required_fields:
            if not data.get(field):
                return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

        widget_id = data.get('widget_id')
        admin_id = data.get('admin_id') or token_admin_id  # fallback to logged-in user for agent

        # Agent role restrictions
        if role == 'agent':
            if admin_id != token_admin_id:
                return Response({'error': 'Agents can only create contacts for themselves.'}, status=403)
            agent = get_admin_collection().find_one({'admin_id': token_admin_id})
            allowed_widgets = agent.get('assigned_widgets', [])
            if widget_id not in allowed_widgets:
                return Response({'error': 'Access denied to this widget'}, status=403)

        contact = {
            'contact_id': data.get('contact_id') or generate_contact_id(),
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone', ''),
            'secondary_email': data.get('secondary_email', ''),
            'address': data.get('address', ''),
            'admin_id': admin_id,
            'widget_id': widget_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Add any custom fields
        reserved_keys = {'contact_id', 'widget_id', 'admin_id', 'created_at', 'updated_at', 'name', 'email', 'phone', 'secondary_email', 'address'}
        for key, value in data.items():
            if key not in reserved_keys:
                contact[key] = value

        try:
            result = get_contact_collection().insert_one(contact)
            contact['_id'] = str(result.inserted_id)
            return Response(contact, status=status.HTTP_201_CREATED)
        except DuplicateKeyError:
            return Response(
                {"error": "A contact with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )




class ContactRetrieveUpdateDeleteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []  

    def is_authorized(self, user, contact):
        if user.get("role") == "superadmin":
            return True
        elif user.get("role") == "agent":
            agent = get_admin_collection().find_one({'admin_id': user.get('admin_id')})
            assigned_widgets = agent.get('assigned_widgets', []) if agent else []
            return contact.get('widget_id') in assigned_widgets
        return False

    def get_object(self, contact_id):
        return get_contact_collection().find_one({'contact_id': contact_id})

    def get(self, request, pk):
        user = request.user  # Already set by JWTAuthentication
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if not self.is_authorized(user, contact):
            return Response({'error': 'Permission denied'}, status=403)

        contact['_id'] = str(contact['_id'])
        return Response(contact)

    def patch(self, request, pk):
        user = request.user
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        if not self.is_authorized(user, contact):
            return Response({'error': 'Permission denied'}, status=403)
        updated_data = request.data.copy()
        updated_data['updated_at'] = datetime.utcnow()
        result = get_contact_collection().update_one(
            {'contact_id': pk},
            {'$set': updated_data}
        )
        # Update in-memory dict and return updated copy
        contact.update(updated_data)
        contact['_id'] = str(contact['_id'])  # Convert ObjectId to string for frontend
        return Response(contact, status=200)

    def delete(self, request, pk):
        user = request.user
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if not self.is_authorized(user, contact):
            return Response({'error': 'Permission denied'}, status=403)

        get_contact_collection().delete_one({'contact_id': pk})
        return Response({'message': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)





class DeactivateRoom(APIView):
    @swagger_auto_schema(
        operation_description="Deactivate (archive) a chat room by room_id",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['room_id'],
            properties={
                'room_id': openapi.Schema(type=openapi.TYPE_STRING, description='Chat room ID'),
            },
        ),
        responses={
            200: openapi.Response('Room deactivated successfully', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request: Missing room_id',
            404: 'Chat room not found',
        }
    )
    def post(self, request):
        room_id = request.data.get("room_id")

        if not room_id:
            return Response({"error": "room_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        room_collection = get_room_collection()

        room = room_collection.find_one({"room_id": room_id})
        if not room:
            return Response({"error": "Chat room not found"}, status=status.HTTP_404_NOT_FOUND)

        # Update the room status to inactive/archived
        room_collection.update_one(
            {"room_id": room_id},
            {"$set": {"active": False, "archived_at": datetime.utcnow()}}  # Add archive timestamp too
        )

        return Response({"message": f"Room '{room_id}' deactivated and archived."}, status=status.HTTP_200_OK)
    


@api_view(["POST"])
def user_feedback(request):
    room_id = request.data.get("room_id")
    rating = request.data.get("rating")
    comment = request.data.get("comment", "")

    if not room_id or rating is None:
        return Response({"success": False, "error": "room_id and rating are required"}, status=400)

    chat_rooms = get_room_collection()

    # Step 1: Check if feedback already exists
    existing = chat_rooms.find_one(
        {"room_id": room_id},
        {"_id": 0, "user_feedback": 1}
    )

    if not existing:
        return Response({"success": False, "error": "Room not found"}, status=404)

    if "user_feedback" in existing:
        return Response({
            "success": False,
            "error": "Feedback already submitted",
            "user_feedback": existing["user_feedback"]
        }, status=409)  # 409 Conflict

    # Step 2: Submit feedback
    result = chat_rooms.update_one(
        {"room_id": room_id},
        {"$set": {"user_feedback": {"rating": rating, "comment": comment}}}
    )

    return Response({
        "success": True,
        "message": "Feedback submitted successfully",
        "user_feedback": {
            "result": result.modified_count > 0,
            "room_id": room_id,
            "created_at": datetime.utcnow().isoformat(),
            "rating": rating,
            "comment": comment
        }
    }, status=200)


class AgentFeedbackList(APIView):
    def get(self, request, agent_name):
        chat_rooms = get_room_collection()
        rating_filter = request.GET.get("rating")

        feedback_list = []

        room_filter = {"assigned_agent": agent_name}
        rooms = list(chat_rooms.find(room_filter))

        for room in rooms:
            feedback = room.get("user_feedback", {})
            rating = feedback.get("rating")
            comment = feedback.get("comment")

            if feedback:
                if rating_filter and str(rating) != str(rating_filter):
                    continue

                feedback_list.append({
                    "room_id": room["room_id"],
                    "created_at": room["created_at"].isoformat(),
                    "rating": rating,
                    "comment": comment
                })

        return Response({
            "agent_name": agent_name,
            "feedback_count": len(feedback_list),
            "feedback": feedback_list
        }, status=200)

from datetime import datetime, timedelta
from collections import defaultdict
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import statistics

class AgentAnalytics(APIView):
    permission_classes = [IsSuperAdmin]
    authentication_classes = [JWTAuthentication]
    """
    Get comprehensive analytics for a specific agent, including chat history, 
    response times, session data, and feedback.
    Supports optional filters for date range, preview messages, grouping by day/week, and rating.
    """
    
    def get(self, request, agent_name):
        try:
            chat_rooms = get_room_collection()
            messages = get_chat_collection()

            # Optional Query Params
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            include_preview = request.GET.get('include_preview') == 'true'
            group_by = request.GET.get('group_by')  # 'day' or 'week'
            rating_filter = request.GET.get("rating")

            # Parse date filters
            date_filter = {}
            if start_date:
                try:
                    start_date = datetime.strptime(start_date, "%Y-%m-%d")
                    date_filter["$gte"] = start_date
                except ValueError:
                    return Response({"error": "Invalid start_date format. Use YYYY-MM-DD"}, status=400)
            
            if end_date:
                try:
                    end_date = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # Include full day
                    date_filter["$lt"] = end_date
                except ValueError:
                    return Response({"error": "Invalid end_date format. Use YYYY-MM-DD"}, status=400)

            if rating_filter:
                try:
                    rating_filter = int(rating_filter)
                    if rating_filter < 1 or rating_filter > 5:
                        return Response({"error": "Rating filter must be between 1 and 5"}, status=400)
                except ValueError:
                    return Response({"error": "Invalid rating filter"}, status=400)

            # Step 1: Find rooms assigned to the agent
            room_filter = {"assigned_agent": agent_name}
            
            # Apply date filter to room creation if provided
            if date_filter:
                room_filter["created_at"] = date_filter.copy()

            rooms = list(chat_rooms.find(room_filter))

            if not rooms:
                return self._empty_response(agent_name)

            room_ids = [room["room_id"] for room in rooms]

            # Step 2: Get messages for these rooms
            message_filter = {"room_id": {"$in": room_ids}}
            
            # Apply date filter to messages if provided
            if date_filter:
                message_filter["timestamp"] = date_filter.copy()

            all_messages = list(messages.find(message_filter).sort("timestamp", 1))

            # Step 3: Process analytics
            analytics_data = self._process_analytics(rooms, all_messages, rating_filter, include_preview)

            # Step 4: Group stats if requested
            if group_by in ["day", "week"]:
                return self._get_grouped_stats(analytics_data, group_by, agent_name)

            return Response(analytics_data, status=200)

        except Exception as e:
            return Response({"error": f"Error processing analytics: {str(e)}"}, status=500)

    def _empty_response(self, agent_name):
        """Return empty response when no data is found"""
        return Response({
            "agent_name": agent_name,
            "total_chats_handled": 0,
            "active_chat_sessions": 0,
            "completed_chat_sessions": 0,
            "average_response_time_seconds": None,
            "average_first_response_time_seconds": None,
            "median_response_time_seconds": None,
            "total_messages_sent": 0,
            "total_session_duration_minutes": 0,
            "average_session_duration_minutes": None,
            "average_chat_duration_minutes": None,
            "response_time_distribution": {
                "under_1_min": 0,
                "1_5_min": 0,
                "5_15_min": 0,
                "over_15_min": 0
            },
            "feedback_summary": {
                "total_ratings": 0,
                "average_rating": None,
                "rating_distribution": {str(i): 0 for i in range(1, 6)}
            },
            "chat_history": [],
        }, status=200)

    def _process_analytics(self, rooms, all_messages, rating_filter, include_preview):
        """Process analytics data for the agent"""
        
        # Group messages by room
        messages_by_room = defaultdict(list)
        for msg in all_messages:
            messages_by_room[msg["room_id"]].append(msg)

        chat_history = []
        response_times = []
        first_response_times = []
        agent_message_count = 0
        total_session_duration = 0
        total_chat_duration = 0
        feedback_data = []

        for room in rooms:
            room_id = room["room_id"]
            msgs = messages_by_room.get(room_id, [])
            
            if not msgs:
                continue

            # Calculate response times
            room_response_times = self._calculate_response_times(msgs)
            first_response_time = self._calculate_first_response_time(msgs)
            
            if room_response_times:
                response_times.extend(room_response_times)
            if first_response_time:
                first_response_times.append(first_response_time)

            # Calculate chat duration (first to last message)
            chat_duration = (msgs[-1]["timestamp"] - msgs[0]["timestamp"]).total_seconds() / 60
            total_chat_duration += chat_duration

            # Count agent messages
            agent_messages = [m for m in msgs if m.get("sender_type") == "agent"]
            agent_message_count += len(agent_messages)

            # Calculate session duration from session history
            session_duration = self._calculate_session_duration(room)
            total_session_duration += session_duration

            # Process feedback
            feedback = room.get("user_feedback", {})
            rating = feedback.get("rating")
            comment = feedback.get("comment")
            
            # Convert rating to int safely
            try:
                rating_int = int(rating) if rating else None
            except (ValueError, TypeError):
                rating_int = None

            # Filter by rating if provided
            if rating_filter is not None and rating_int != rating_filter:
                continue

            # Collect feedback data
            if rating_int:
                feedback_data.append({
                    "rating": rating_int,
                    "comment": comment,
                    "room_id": room_id
                })

            # Build chat history item
            history_item = {
                "room_id": room_id,
                "created_at": room["created_at"].isoformat(),
                "closed_at": room.get("closed_at").isoformat() if room.get("closed_at") else None,
                "last_message_time": msgs[-1]["timestamp"].isoformat(),
                "total_messages": len(msgs),
                "agent_messages": len(agent_messages),
                "customer_messages": len([m for m in msgs if m.get("sender_type") == "customer"]),
                "first_response_time_seconds": first_response_time,
                "average_response_time_seconds": sum(room_response_times) / len(room_response_times) if room_response_times else None,
                "chat_duration_minutes": chat_duration,
                "session_duration_minutes": session_duration,
                "is_active": room.get("closed_at") is None,
                "user_feedback": {
                    "rating": rating_int,
                    "comment": comment
                } if feedback else None
            }

            if include_preview:
                history_item["preview"] = {
                    "first": f"{msgs[0].get('sender_type', 'unknown')}: {msgs[0].get('message', '')[:100]}",
                    "last": f"{msgs[-1].get('sender_type', 'unknown')}: {msgs[-1].get('message', '')[:100]}"
                }

            chat_history.append(history_item)

        # Calculate summary statistics
        active_sessions = sum(1 for item in chat_history if item["is_active"])
        completed_sessions = len(chat_history) - active_sessions
        
        # Response time statistics
        avg_response_time = sum(response_times) / len(response_times) if response_times else None
        avg_first_response_time = sum(first_response_times) / len(first_response_times) if first_response_times else None
        median_response_time = statistics.median(response_times) if response_times else None
        
        # Response time distribution
        response_time_distribution = self._calculate_response_time_distribution(response_times)
        
        # Session statistics
        avg_session_duration = total_session_duration / len(chat_history) if chat_history else None
        avg_chat_duration = total_chat_duration / len(chat_history) if chat_history else None
        
        # Feedback summary
        feedback_summary = self._calculate_feedback_summary(feedback_data)

        return {
            "agent_name": room["assigned_agent"] if rooms else "Unknown",
            "total_chats_handled": len(chat_history),
            "active_chat_sessions": active_sessions,
            "completed_chat_sessions": completed_sessions,
            "average_response_time_seconds": round(avg_response_time, 2) if avg_response_time else None,
            "average_first_response_time_seconds": round(avg_first_response_time, 2) if avg_first_response_time else None,
            "median_response_time_seconds": round(median_response_time, 2) if median_response_time else None,
            "total_messages_sent": agent_message_count,
            "total_session_duration_minutes": round(total_session_duration, 2),
            "average_session_duration_minutes": round(avg_session_duration, 2) if avg_session_duration else None,
            "average_chat_duration_minutes": round(avg_chat_duration, 2) if avg_chat_duration else None,
            "response_time_distribution": response_time_distribution,
            "feedback_summary": feedback_summary,
            "chat_history": chat_history,
        }

    def _calculate_response_times(self, msgs):
        """Calculate response times for agent messages"""
        response_times = []
        
        for i in range(len(msgs) - 1):
            current_msg = msgs[i]
            
            # If current message is from customer
            if current_msg.get("sender_type") == "customer":
                # Find next agent response
                for j in range(i + 1, len(msgs)):
                    next_msg = msgs[j]
                    if next_msg.get("sender_type") == "agent":
                        response_time = (next_msg["timestamp"] - current_msg["timestamp"]).total_seconds()
                        response_times.append(response_time)
                        break
        
        return response_times

    def _calculate_first_response_time(self, msgs):
        """Calculate first response time (first customer message to first agent response)"""
        first_customer_msg = None
        first_agent_response = None
        
        for msg in msgs:
            if msg.get("sender_type") == "customer" and first_customer_msg is None:
                first_customer_msg = msg
            elif msg.get("sender_type") == "agent" and first_customer_msg and first_agent_response is None:
                first_agent_response = msg
                break
        
        if first_customer_msg and first_agent_response:
            return (first_agent_response["timestamp"] - first_customer_msg["timestamp"]).total_seconds()
        
        return None

    def _calculate_session_duration(self, room):
        """Calculate total session duration from session history"""
        session_history = room.get("session_history", [])
        total_duration = 0
        
        for session in session_history:
            if session.get("start_time") and session.get("end_time"):
                duration = (session["end_time"] - session["start_time"]).total_seconds() / 60
                total_duration += duration
        
        return total_duration

    def _calculate_response_time_distribution(self, response_times):
        """Calculate response time distribution"""
        distribution = {
            "under_1_min": 0,
            "1_5_min": 0,
            "5_15_min": 0,
            "over_15_min": 0
        }
        
        for rt in response_times:
            rt_minutes = rt / 60
            if rt_minutes < 1:
                distribution["under_1_min"] += 1
            elif rt_minutes < 5:
                distribution["1_5_min"] += 1
            elif rt_minutes < 15:
                distribution["5_15_min"] += 1
            else:
                distribution["over_15_min"] += 1
        
        return distribution

    def _calculate_feedback_summary(self, feedback_data):
        """Calculate feedback summary statistics"""
        total_ratings = len(feedback_data)
        
        if total_ratings == 0:
            return {
                "total_ratings": 0,
                "average_rating": None,
                "rating_distribution": {str(i): 0 for i in range(1, 6)}
            }
        
        ratings = [f["rating"] for f in feedback_data]
        average_rating = sum(ratings) / len(ratings)
        
        rating_distribution = {str(i): 0 for i in range(1, 6)}
        for rating in ratings:
            rating_distribution[str(rating)] += 1
        
        return {
            "total_ratings": total_ratings,
            "average_rating": round(average_rating, 2),
            "rating_distribution": rating_distribution
        }

    def _get_grouped_stats(self, analytics_data, group_by, agent_name):
        """Return grouped statistics by day or week"""
        grouped = defaultdict(list)
        
        for item in analytics_data["chat_history"]:
            key_date = datetime.fromisoformat(item["created_at"])
            if group_by == "day":
                key = key_date.strftime("%Y-%m-%d")
            else:  # week
                key = key_date.strftime("%Y-W%U")
            grouped[key].append(item)

        grouped_stats = []
        for key, items in sorted(grouped.items()):
            # Calculate aggregated stats for this period
            total_chats = len(items)
            active_chats = sum(1 for item in items if item["is_active"])
            
            # Response time stats
            first_response_times = [item["first_response_time_seconds"] for item in items if item["first_response_time_seconds"]]
            avg_first_response = sum(first_response_times) / len(first_response_times) if first_response_times else None
            
            # Session duration stats
            session_durations = [item["session_duration_minutes"] for item in items if item["session_duration_minutes"]]
            avg_session_duration = sum(session_durations) / len(session_durations) if session_durations else None
            
            # Feedback stats
            ratings = [item["user_feedback"]["rating"] for item in items if item["user_feedback"] and item["user_feedback"]["rating"]]
            avg_rating = sum(ratings) / len(ratings) if ratings else None
            
            grouped_stats.append({
                "period": key,
                "total_chats": total_chats,
                "active_chats": active_chats,
                "completed_chats": total_chats - active_chats,
                "average_first_response_time_seconds": round(avg_first_response, 2) if avg_first_response else None,
                "average_session_duration_minutes": round(avg_session_duration, 2) if avg_session_duration else None,
                "average_rating": round(avg_rating, 2) if avg_rating else None,
                "total_ratings": len(ratings)
            })

        return Response({
            "agent_name": agent_name,
            "group_by": group_by,
            "summary": grouped_stats,
            "total_periods": len(grouped_stats)
        }, status=200)

# class AgentAnalytics(APIView):
#     permission_classes = [IsSuperAdmin]
#     authentication_classes = [JWTAuthentication]# No DRF permission checks
#     """
#     Get analytics for a specific agent, including chat history, response times, and feedback.
#     Supports optional filters for date range, preview messages, grouping by day/week, and rating.
#     """
#     def get(self, request, agent_name):
#         chat_rooms = get_room_collection()
#         messages = get_chat_collection()

#         # Optional Query Params
#         start_date = request.GET.get('start_date')
#         end_date = request.GET.get('end_date')
#         include_preview = request.GET.get('include_preview') == 'true'
#         group_by = request.GET.get('group_by')  # 'day' or 'week'
#         rating_filter = request.GET.get("rating")

#         # Parse date filters
#         if start_date:
#             start_date = datetime.strptime(start_date, "%Y-%m-%d")
#         if end_date:
#             end_date = datetime.strptime(end_date, "%Y-%m-%d")
#         if rating_filter:
#             try:
#                 rating_filter = int(rating_filter)
#             except ValueError:
#                 return Response({"error": "Invalid rating filter"}, status=400)

#         # Step 1: Find rooms assigned to the agent
#         room_filter = {"assigned_agent": agent_name}
#         if start_date or end_date:
#             room_filter["created_at"] = {}
#             if start_date:
#                 room_filter["created_at"]["$gte"] = start_date
#             if end_date:
#                 room_filter["created_at"]["$lte"] = end_date

#         rooms = list(chat_rooms.find(room_filter))

#         if not rooms:
#             return Response({
#                 "agent_name": agent_name,
#                 "total_chats_handled": 0,
#                 "active_chat_sessions": 0,
#                 "average_response_time_seconds": None,
#                 "chat_history": [],
#             }, status=200)

#         room_ids = [room["room_id"] for room in rooms]

#         chat_history = []
#         response_times = []

#         for room in rooms:
#             room_id = room["room_id"]

#             msgs = list(messages.find({"room_id": room_id}).sort("timestamp", 1))
#             if not msgs:
#                 continue

#             user_first = next((m for m in msgs if m["sender"] == "User"), None)
#             agent_first = next((m for m in msgs if m["sender"] == "Agent"), None)

#             first_response_time = (
#                 (agent_first["timestamp"] - user_first["timestamp"]).total_seconds()
#                 if user_first and agent_first else None
#             )

#             if first_response_time is not None:
#                 response_times.append(first_response_time)

#             time_spent = (msgs[-1]["timestamp"] - msgs[0]["timestamp"]).total_seconds()

#             feedback = room.get("user_feedback", {})
#             rating = feedback.get("rating")
#             comment = feedback.get("comment")
            
#             # Convert rating to int safely
#             try:
#                 rating_int = int(rating)
#             except (ValueError, TypeError):
#                 rating_int = None


#             # Filter by rating if provided
#             if rating_filter is not None and rating_int != rating_filter:
#                 continue

#             history_item = {
#                 "room_id": room_id,
#                 "created_at": room["created_at"].isoformat(),
#                 "closed_at": room.get("closed_at", None).isoformat() if room.get("closed_at") else None,
#                 "last_message_time": msgs[-1]["timestamp"].isoformat(),
#                 "total_messages": len(msgs),
#                 "first_response_time_seconds": first_response_time,
#                 "time_spent_seconds": time_spent,
#                 "user_feedback": {
#                     "rating": rating,
#                     "comment": comment
#                 } if feedback else None
#             }

#             if include_preview:
#                 history_item["preview"] = {
#                     "first": msgs[0]["sender"] + ": " + msgs[0].get("message", ""),
#                     "last": msgs[-1]["sender"] + ": " + msgs[-1].get("message", "")
#                 }

#             chat_history.append(history_item)

#         # Group stats if requested
#         if group_by in ["day", "week"]:
#             grouped = defaultdict(list)
#             for item in chat_history:
#                 key_date = datetime.fromisoformat(item["created_at"])
#                 key = key_date.strftime("%Y-%m-%d") if group_by == "day" else key_date.strftime("%Y-W%U")
#                 grouped[key].append(item)

#             grouped_stats = []
#             for key, items in grouped.items():
#                 valid_times = [i["first_response_time_seconds"] for i in items if i["first_response_time_seconds"] is not None]
#                 avg_response = sum(valid_times) / len(valid_times) if valid_times else None
#                 grouped_stats.append({
#                     "period": key,
#                     "chats": len(items),
#                     "average_response_time_seconds": avg_response
#                 })

#             return Response({
#                 "agent_name": agent_name,
#                 "group_by": group_by,
#                 "summary": grouped_stats
#             }, status=200)

#         return Response({
#             "agent_name": agent_name,
#             "total_chats_handled": len(chat_history),
#             "active_chat_sessions": sum(1 for r in rooms if r.get('closed_at') is None),
#             "average_response_time_seconds": (
#                 sum(response_times) / len(response_times) if response_times else None
#             ),
#             "chat_history": chat_history,
#         }, status=200)

class ExportChatHistoryAPIView(APIView):
    permission_classes = [IsSuperAdmin]  # Only admins or superadmins can access this view
    authentication_classes = [JWTAuthentication]  # Custom auth, no DRF auth needed
    
    """
    Export chat history for a room (and optional date range) as CSV or JSON.
    Query params:
      - room_id (required)
      - start_date (optional, ISO format)
      - end_date   (optional, ISO format)
      - format     (optional, one of 'csv','json'; default 'csv')
    """
    def get(self, request):
        print("✅ ExportChatHistoryAPIView HIT")
        room_id = request.query_params.get('room_id')
        if not room_id:
            return Response({"error": "room_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date   = request.query_params.get('end_date')
        fmt        = request.query_params.get('format', 'csv').lower()

        # Build query
        query = {'room_id': room_id}
        date_q = {}
        if start_date:
            dt = parse_datetime(start_date)
            if not dt: return Response({"error":"Invalid start_date"},400)
            date_q['$gte'] = dt
        if end_date:
            dt = parse_datetime(end_date)
            if not dt: return Response({"error":"Invalid end_date"},400)
            date_q['$lt'] = dt
        if date_q:
            query['timestamp'] = date_q

        msgs = list(get_chat_collection().find(query).sort('timestamp',1))

        # Normalize all messages safely
        for m in msgs:
            m['_id'] = str(m.get('_id', ''))
            ts = m.get('timestamp')
            if isinstance(ts, datetime):
                m['timestamp'] = ts.isoformat()
            else:
                m['timestamp'] = str(ts)

        # JSON
        if fmt == 'json':
            return HttpResponse(
                json.dumps(msgs, indent=2, cls=DjangoJSONEncoder),
                content_type='application/json',
                headers={'Content-Disposition': f'attachment; filename="chat_{room_id}.json"'}
            )

        # CSV
        if fmt == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            # header
            writer.writerow(['message_id','sender','text','timestamp'])
            for m in msgs:
                writer.writerow([
                    m.get('message_id',''),
                    m.get('sender',''),
                    m.get('message',''),
                    m.get('timestamp',''),
                ])
            return HttpResponse(
                output.getvalue(),
                content_type='text/csv',
                headers={'Content-Disposition': f'attachment; filename="chat_{room_id}.csv"'}
            )
        return Response({"error": "Unsupported format, choose csv or json "}, status=status.HTTP_400_BAD_REQUEST)

