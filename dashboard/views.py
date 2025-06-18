import traceback
from venv import logger
from django.http import JsonResponse
from pymongo.errors import DuplicateKeyError
from utils.random_id import generate_contact_id  # Import the contact ID generator
from wish_bot.db import  get_admin_collection, get_contact_collection # Import the contacts collection
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
from  authentication.permissions import IsAdminOrSuperAdmin, IsSuperAdmin

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
    authentication_classes = [JWTAuthentication]    # We are using custom auth
    permission_classes = [IsSuperAdmin]      # Only superadmin can add agents

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
        description="Only superadmin can add an agent. Requires name, email, password."
    )
    def post(self, request):
        # user = getattr(request, 'jwt_user', None)
        # if not user or user.get('role') != 'superadmin':
        #     return Response({'error': 'Unauthorized'}, status=403)

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
            if agents_collection.find_one({"email": email}):
                return Response({"message": "Agent with this email already exists."}, status=400)
        except Exception as e:
            return Response({"message": "Database error while checking existing agent"}, status=500)

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
            result = agents_collection.update_one({'admin_id': agent_id}, {'$set': update_fields},{'updated_at': datetime.utcnow()})

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


class AgentDetailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = []  # We'll handle role logic manually here

    @extend_schema(
        summary="Get agent details",
        description="Returns detailed info of a specific agent. Superadmin can view anyone. Agents can view their own profile.",
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
            print("🔐 JWT User Payload:", user)

            role = user.get("role")
            print("👤 Role:", role)
            print("🔎 agent_id from URL:", agent_id)

            if role == "superadmin":
                print("✅ Superadmin access granted")

            elif role == "agent":
                token_admin_id = user.get("admin_id")
                print("🆔 admin_id from token:", token_admin_id)

                # Fallback if agent_id is not passed
                if not agent_id:
                    print("ℹ️ No agent_id passed, using token admin_id")
                    agent_id = token_admin_id

                elif agent_id != token_admin_id:
                    print("❌ agent_id mismatch! Token:", token_admin_id, "URL param:", agent_id)
                    return Response({'error': 'Forbidden'}, status=403)

                print("✅ Agent access granted to their own data")

            else:
                print("❌ Unauthorized role:", role)
                return Response({'error': 'Unauthorized'}, status=403)

            # ✅ Fetch agent from DB
            agents_collection = get_admin_collection()
            print("📦 Fetching from DB: admin_id =", agent_id)

            agent = agents_collection.find_one({'admin_id': agent_id, 'role': 'agent'})
            if not agent:
                print("❌ Agent not found in DB")
                return Response({'error': 'Agent not found'}, status=404)

            print("✅ Agent found:", agent.get("name", "No Name"))
            agent['_id'] = str(agent['_id'])
            return Response({'agent': agent}, status=200)

        except Exception as e:
            print("🔥 Exception in AgentDetailAPIView:", str(e))
            traceback.print_exc()
            return Response({'error': f"Internal error: {str(e)}"}, status=500)






class AssignAgentToRoom(APIView):
    @extend_schema(
        operation_id="assignAgentToRoom",
        summary="Assign an agent to an existing chat room by room_id",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "room_id": {"type": "string", "description": "Chat room ID"},
                    "agent_name": {"type": "string", "description": "Name of the agent to assign"},
                },
                "required": ["room_id", "agent_name"],
                "example": {
                    "room_id": "room123",
                    "agent_name": "John Doe"
                }
            }
        },
        responses={
            200: {
                "description": "Agent assigned successfully",
                "content": {
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"}
                        },
                        "example": {
                            "message": "Agent 'John Doe' assigned to room 'room123'"
                        }
                    }
                }
            },
            400: {
                "description": "Bad Request: Missing room_id or agent_name",
                "content": {
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string"}
                        },
                        "example": {
                            "error": "room_id and agent_name are required"
                        }
                    }
                }
            },
            404: {
                "description": "Chat room not found",
                "content": {
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string"}
                        },
                        "example": {
                            "error": "Chat room not found"
                        }
                    }
                }
            },
            500: {
                "description": "Internal Server Error",
                "content": {
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string"}
                        },
                        "example": {
                            "error": "Unexpected server error"
                        }
                    }
                }
            }
        }
    )
    def post(self, request):
        try:
            room_id = request.data.get("room_id")
            agent_name = request.data.get("name")

            if not room_id or not agent_name:
                return Response(
                    {"error": "room_id and agent_name are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            room_collection = get_room_collection()

            room = room_collection.find_one({"room_id": room_id})
            if not room:
                return Response(
                    {"error": "Chat room not found"}, status=status.HTTP_404_NOT_FOUND
                )

            room_collection.update_one(
                {"room_id": room_id},
                {"$set": {"assigned_agent": agent_name}}
            )

            return Response(
                {"message": f"Agent '{agent_name}' assigned to room '{room_id}'"},
                status=status.HTTP_200_OK,
            )

        except PyMongoError as e:
            return Response(
                {"error": f"Database error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            return Response(
                {"error": f"Unexpected server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )




@jwt_required
def conversation_list(request):
    try:
        user = request.user
        role = user.get('role')
        assigned_widgets = user.get('assigned_widgets', [])

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
        ]

        if role == 'agent':
            pipeline.append({
                "$match": {
                    "room.widget_id": {"$in": assigned_widgets}
                }
            })

        pipeline += [
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
            "total_count": len(conversations)
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "error": f"Error fetching conversations: {str(e)}",
            "conversations": [],
            "total_count": 0
        }, status=500)




@jwt_required
def chat_room_view(request, room_id):
    try:
        user = request.jwt_user
        role = user.get("role")
        admin_id = user.get("admin_id")

        chat_collection = get_chat_collection()
        rooms_collection = get_room_collection()
        # widgets_collection = get_widget_collection()
        agents_collection = get_admin_collection()

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

        return JsonResponse({
            'success': True,
            'messages': messages,
            'room_id': room_id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Failed to load chat messages: {str(e)}",
            'messages': [],
            'room_id': room_id
        }, status=500)


@jwt_required
def widget_conversations(request, widget_id):
    try:
        user = request.user
        role = user.get('role')
        assigned_widgets = user.get('assigned_widgets', [])

        if role == 'agent' and widget_id not in assigned_widgets:
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



class ContactListCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    def get_user_from_request(self, request):
        auth = get_authorization_header(request).decode('utf-8')
        if auth.startswith('Bearer '):
            token = auth.split(' ')[1]
            return decode_token(token)  # Should return a user dict
        return None

    # @jwt_required
    def get(self, request):
        user = self.get_user_from_request(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        role = user.get("role")
        token_admin_id = user.get("admin_id")

        widget_id = request.query_params.get('widget_id')
        contact_id = request.query_params.get('contact_id')
        search = request.query_params.get('search')
        agent_id = request.query_params.get('agent_id') if role == 'superadmin' else token_admin_id

        query = {}

        # Filter only if specific fields are passed
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
            # Agent: filter by their ID and assigned widgets
            agent = get_admin_collection().find_one({'admin_id': token_admin_id})
            allowed_widgets = agent.get('assigned_widgets', [])
            # query['agent_id'] = token_admin_id
            if widget_id:
                if widget_id not in allowed_widgets:
                    return Response({'error': 'Access denied to this widget'}, status=403)
                query['widget_id'] = widget_id
            else:
                query['widget_id'] = {'$in': allowed_widgets}

        elif role == 'superadmin':
            # Superadmin: optionally filter by agent_id or widget_id
            if agent_id:
                query['agent_id'] = agent_id
            if widget_id:
                query['widget_id'] = widget_id

        # Fetch contacts
        contacts = list(get_contact_collection().find(query))
        for c in contacts:
            c['_id'] = str(c['_id'])

        return Response(contacts)


    # @jwt_required
    def post(self, request):
        user = self.get_user_from_request(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        # Ensure user is authenticated and has a role
        
        role = user.get("role")
        token_admin_id = user.get("admin_id")

        data = request.data
        required_fields = ['name', 'email', 'widget_id']

        for field in required_fields:
            if not data.get(field):
                return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

        widget_id = data.get('widget_id')
        agent_id = data.get('agent_id') or token_admin_id  # fallback to logged-in user for agent

        # Agent role restrictions
        if role == 'agent':
            if agent_id != token_admin_id:
                return Response({'error': 'Agents can only create contacts for themselves.'}, status=403)
            agent = get_admin_collection().find_one({'admin_id': token_admin_id})
            allowed_widgets = agent.get('assigned_widgets', [])
            if widget_id not in allowed_widgets:
                return Response({'error': 'Access denied to this widget'}, status=403)

        contact = {
            'contact_id': generate_contact_id(),
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone', ''),
            'secondary_email': data.get('secondary_email', ''),
            'address': data.get('address', ''),
            'agent_id': agent_id,
            'widget_id': widget_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

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
    def get_user_from_request(self, request):
        auth = get_authorization_header(request).decode('utf-8')
        if auth.startswith('Bearer '):
            token = auth.split(' ')[1]
            return decode_token(token)
        return None

    def is_agent_authorized_for_widget(self, user, contact):
        agent_id = user.get('admin_id')
        agent = get_admin_collection().find_one({'admin_id': agent_id})
        assigned_widgets = agent.get('assigned_widgets', [])
        return contact.get('widget_id') in assigned_widgets

    def get_object(self, contact_id):
        try:
            return get_contact_collection().find_one({'contact_id': contact_id})
        except Exception:
            return None


    def get(self, request, pk):
        user = self.get_user_from_request(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.get("role") == 'agent' and not self.is_agent_authorized_for_widget(user, contact):
            return Response({'error': 'Permission denied: Not assigned to this widget'}, status=403)

        contact['_id'] = str(contact['_id'])
        return Response(contact)

    def put(self, request, pk):
        user = self.get_user_from_request(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.get("role") == 'agent' and not self.is_agent_authorized_for_widget(user, contact):
            return Response({'error': 'Permission denied: Not assigned to this widget'}, status=403)

        updated_data = request.data
        updated_data['updated_at'] = datetime.utcnow()

        get_contact_collection().update_one({'contact_id': pk}, {'$set': updated_data})
        contact.update(updated_data)
        contact['_id'] = str(contact['_id'])
        return Response(contact)

    def delete(self, request, pk):
        user = self.get_user_from_request(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.get("role") == 'agent' and not self.is_agent_authorized_for_widget(user, contact):
            return Response({'error': 'Permission denied: Not assigned to this widget'}, status=403)

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



class AgentAnalytics(APIView):
    permission_classes = [IsSuperAdmin]
    authentication_classes = [JWTAuthentication]# No DRF permission checks
    """
    Get analytics for a specific agent, including chat history, response times, and feedback.
    Supports optional filters for date range, preview messages, grouping by day/week, and rating.
    """
    def get(self, request, agent_name):
        chat_rooms = get_room_collection()
        messages = get_chat_collection()

        # Optional Query Params
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        include_preview = request.GET.get('include_preview') == 'true'
        group_by = request.GET.get('group_by')  # 'day' or 'week'
        rating_filter = request.GET.get("rating")

        # Parse date filters
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        if rating_filter:
            try:
                rating_filter = int(rating_filter)
            except ValueError:
                return Response({"error": "Invalid rating filter"}, status=400)

        # Step 1: Find rooms assigned to the agent
        room_filter = {"assigned_agent": agent_name}
        if start_date or end_date:
            room_filter["created_at"] = {}
            if start_date:
                room_filter["created_at"]["$gte"] = start_date
            if end_date:
                room_filter["created_at"]["$lte"] = end_date

        rooms = list(chat_rooms.find(room_filter))

        if not rooms:
            return Response({
                "agent_name": agent_name,
                "total_chats_handled": 0,
                "active_chat_sessions": 0,
                "average_response_time_seconds": None,
                "chat_history": [],
            }, status=200)

        room_ids = [room["room_id"] for room in rooms]

        chat_history = []
        response_times = []

        for room in rooms:
            room_id = room["room_id"]

            msgs = list(messages.find({"room_id": room_id}).sort("timestamp", 1))
            if not msgs:
                continue

            user_first = next((m for m in msgs if m["sender"] == "User"), None)
            agent_first = next((m for m in msgs if m["sender"] == "Agent"), None)

            first_response_time = (
                (agent_first["timestamp"] - user_first["timestamp"]).total_seconds()
                if user_first and agent_first else None
            )

            if first_response_time is not None:
                response_times.append(first_response_time)

            time_spent = (msgs[-1]["timestamp"] - msgs[0]["timestamp"]).total_seconds()

            feedback = room.get("user_feedback", {})
            rating = feedback.get("rating")
            comment = feedback.get("comment")
            
            # Convert rating to int safely
            try:
                rating_int = int(rating)
            except (ValueError, TypeError):
                rating_int = None


            # Filter by rating if provided
            if rating_filter is not None and rating_int != rating_filter:
                continue

            history_item = {
                "room_id": room_id,
                "created_at": room["created_at"].isoformat(),
                "closed_at": room.get("closed_at", None).isoformat() if room.get("closed_at") else None,
                "last_message_time": msgs[-1]["timestamp"].isoformat(),
                "total_messages": len(msgs),
                "first_response_time_seconds": first_response_time,
                "time_spent_seconds": time_spent,
                "user_feedback": {
                    "rating": rating,
                    "comment": comment
                } if feedback else None
            }

            if include_preview:
                history_item["preview"] = {
                    "first": msgs[0]["sender"] + ": " + msgs[0].get("message", ""),
                    "last": msgs[-1]["sender"] + ": " + msgs[-1].get("message", "")
                }

            chat_history.append(history_item)

        # Group stats if requested
        if group_by in ["day", "week"]:
            grouped = defaultdict(list)
            for item in chat_history:
                key_date = datetime.fromisoformat(item["created_at"])
                key = key_date.strftime("%Y-%m-%d") if group_by == "day" else key_date.strftime("%Y-W%U")
                grouped[key].append(item)

            grouped_stats = []
            for key, items in grouped.items():
                valid_times = [i["first_response_time_seconds"] for i in items if i["first_response_time_seconds"] is not None]
                avg_response = sum(valid_times) / len(valid_times) if valid_times else None
                grouped_stats.append({
                    "period": key,
                    "chats": len(items),
                    "average_response_time_seconds": avg_response
                })

            return Response({
                "agent_name": agent_name,
                "group_by": group_by,
                "summary": grouped_stats
            }, status=200)

        return Response({
            "agent_name": agent_name,
            "total_chats_handled": len(chat_history),
            "active_chat_sessions": sum(1 for r in rooms if r.get('closed_at') is None),
            "average_response_time_seconds": (
                sum(response_times) / len(response_times) if response_times else None
            ),
            "chat_history": chat_history,
        }, status=200)

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

