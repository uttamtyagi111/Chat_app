from pymongo.errors import DuplicateKeyError
from utils.random_id import generate_contact_id  # Import the contact ID generator
from wish_bot.db import  get_contact_collection # Import the contacts collection
import csv,io,json,uuid
from datetime import datetime
from pymongo.errors import PyMongoError  # Assuming PyMongo for MongoDB
from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
from django.core.serializers.json import DjangoJSONEncoder
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from wish_bot.db import get_room_collection,get_chat_collection 
from wish_bot.db import get_agent_collection, get_mongo_client
from drf_spectacular.utils import extend_schema,OpenApiResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib import messages
from pymongo import DESCENDING
from collections import defaultdict
from django.shortcuts import render
from rest_framework.decorators import api_view

# Optional helper to get conversations collection
def get_conversations_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    return db['conversations']


def agent_list(request):
    agents_collection = get_agent_collection()
    agents = list(agents_collection.find())
    return render(request, 'dashboard/agent_list.html', {'agents': agents})

class AddAgentView(APIView):
    @extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'example': 'John Doe'},
                    'email': {'type': 'string', 'format': 'email', 'example': 'john@example.com'}
                },
                'required': ['name', 'email']
            }
        },
        responses={
            201: OpenApiResponse(response={"message": "Agent created successfully."}),
            400: OpenApiResponse(response={"message": "Agent already exists or invalid input."}),
            500: OpenApiResponse(description="Internal Server Error")
        },
        description="Add a new agent to the system. Name and Email must be unique."
    )
    def post(self, request):
        agents_collection = get_agent_collection()

        name = request.data.get('name')
        email = request.data.get('email')

        if not name or not email:
            return Response("Name and Email are required", status=status.HTTP_400_BAD_REQUEST)
        
         # Check for duplicates by name or email
        if agents_collection.find_one({"$or": [{"name": name}, {"email": email}]}):
            return Response(
                {"message": "Agent with this name or email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            agents_collection.insert_one({
                'agent_id': str(uuid.uuid4()),
                'name': name,
                'email': email,
                'is_online': False,
                'last_active': None,
            })
            return Response({"message": f"Agent {name} created successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(f"Error inserting agent: {str(e)}", status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class EditAgentAPIView(APIView):
    @extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'example': 'Jane Smith'},
                    'email': {'type': 'string', 'format': 'email', 'example': 'jane@example.com'}
                },
                'required': ['name', 'email']
            }
        },
        responses={
            200: OpenApiResponse(response={'message': 'Agent updated successfully.'}),
            400: OpenApiResponse(description='Bad Request - Duplicate or missing fields'),
            404: OpenApiResponse(description='Agent not found'),
            500: OpenApiResponse(description='Server error')
        },
        description="Update an existing agent by agent_id. Name and Email must be unique across other agents."
    )
    def put(self, request, agent_id):
        try:
            agents_collection = get_agent_collection()

            agent = agents_collection.find_one({'agent_id': agent_id})
            if not agent:
                return Response({'detail': 'Agent not found'}, status=status.HTTP_404_NOT_FOUND)

            name = request.data.get('name')
            email = request.data.get('email')

            if not name or not email:
                return Response({'detail': 'Name and Email are required'}, status=status.HTTP_400_BAD_REQUEST)

            # Check for duplicate name/email among other agents
            duplicate_agent = agents_collection.find_one({
                'agent_id': {'$ne': agent_id},
                '$or': [{'name': name}, {'email': email}]
            })
            if duplicate_agent:
                return Response(
                    {'detail': 'Another agent with this name or email already exists.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result = agents_collection.update_one(
                {'agent_id': agent_id},
                {'$set': {'name': name, 'email': email}}
            )

            if result.modified_count == 0:
                return Response({'message': 'No changes were made.'}, status=status.HTTP_200_OK)

            return Response({'message': 'Agent updated successfully.'}, status=status.HTTP_200_OK)

        except PyMongoError as e:
            return Response({'detail': f"Database error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'detail': f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class DeleteAgentAPIView(APIView):
    @extend_schema(
        responses={
            204: 'Agent deleted successfully.',
            404: 'Agent not found.',
            500: 'Server error'
        },
        description="Delete an agent by agent_id."
    )
    def delete(self, request, agent_id):
        try:
            agents_collection = get_agent_collection()

            # Check if agent exists before deletion
            agent = agents_collection.find_one({'agent_id': agent_id})
            if not agent:
                return Response({'detail': 'Agent not found.'}, status=status.HTTP_404_NOT_FOUND)

            agents_collection.delete_one({'agent_id': agent_id})

            return Response({'message': 'Agent deleted successfully.'},status=status.HTTP_204_NO_CONTENT)

        except PyMongoError as e:
            return Response({'detail': f"Database error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'detail': f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class AgentDetailAPIView(APIView):
    @extend_schema(
        summary="Retrieve agent details",
        description="Fetch a single agent by agent_id and return related conversations.",
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'agent': {'type': 'object'},
                    'conversations': {'type': 'array', 'items': {'type': 'object'}}
                }
            },
            404: {'description': 'Agent not found'},
            500: {'description': 'Unexpected or database error'}
        }
    )
    def get(self, request, agent_id):
        agents_collection = get_agent_collection()
        conversations_collection = get_conversations_collection()

        try:
            agent = agents_collection.find_one({'agent_id': agent_id})
            if not agent:
                return Response({'detail': 'Agent not found'}, status=status.HTTP_404_NOT_FOUND)

            conversations = list(conversations_collection.find({'agent_id': agent_id}))

            # Convert ObjectId fields to string
            agent['_id'] = str(agent['_id'])
            for conv in conversations:
                if '_id' in conv:
                    conv['_id'] = str(conv['_id'])

            return Response({
                'agent': agent,
                'conversations': conversations
            }, status=status.HTTP_200_OK)

        except PyMongoError as e:
            return Response({'detail': f"Database error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({'detail': f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            agent_name = request.data.get("agent_name")

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

from django.http import JsonResponse
def conversation_list(request):
    try:
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
            # Join with rooms collection
            {
                "$lookup": {
                    "from": "rooms",  # Replace with your actual rooms collection name
                    "localField": "_id",
                    "foreignField": "room_id",
                    "as": "room"
                }
            },
            {"$unwind": {"path": "$room", "preserveNullAndEmptyArrays": True}},
            
            # Join with widgets collection
            {
                "$lookup": {
                    "from": "widgets",  # Replace with your actual widgets collection name
                    "localField": "room.widget_id",
                    "foreignField": "widget_id",
                    "as": "widget"
                }
            },
            {"$unwind": {"path": "$widget", "preserveNullAndEmptyArrays": True}},
            
            # Project final shape
            {
                "$project": {
                    "room_id": "$_id",
                    "last_message": 1,
                    "last_timestamp": 1,
                    "total_messages": 1,
                    "widget": {
                        "widget_id": "$widget.widget_id",
                        "name": "$widget.name",
                        # "domain": "$widget.domain",
                        "is_active": "$widget.is_active",
                        "created_at": "$widget.created_at"
                    }
                }
            },
            {"$sort": {"last_timestamp": DESCENDING}}
        ]

        conversations = list(collection.aggregate(pipeline))

        # Format timestamps
        for convo in conversations:
            if isinstance(convo.get('last_timestamp'), datetime):
                convo['last_timestamp'] = convo['last_timestamp'].isoformat()
            
            # Handle case where widget might be None
            if not convo.get('widget'):
                convo['widget'] = {
                    'widget_id': '',
                    'name': 'No Widget',
                    # 'domain': '',
                    'is_active': False,
                    'created_at': ''
                }
            if convo.get('widget') and convo['widget'].get('created_at'):
                            if isinstance(convo['widget']['created_at'], datetime):
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

def chat_room_view(request, room_id):
    try:
        collection = get_chat_collection()
        messages = list(collection.find({'room_id': room_id}).sort('timestamp', 1))

        for msg in messages:
            msg['_id'] = str(msg['_id'])
            msg['timestamp'] = msg['timestamp'].isoformat()

    except Exception as e:
        messages = []
        messages.error(request, f"Failed to load chat messages: {e}")

    return render(request, 'dashboard/chat_room.html', {'messages': messages, 'room_id': room_id})



class ContactListCreateView(APIView):
    def get(self, request):
        agent_id = request.query_params.get('agent_id')
        contact_id = request.query_params.get('contact_id')
        search = request.query_params.get('search')

        query = {}
        if agent_id:
            query['agent_id'] = agent_id
        if contact_id:
            query['contact_id'] = contact_id
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'phone': {'$regex': search, '$options': 'i'}},
                {'secondary_email': {'$regex': search, '$options': 'i'}},
            ]

        contacts = list(get_contact_collection().find(query))
        for c in contacts:
            c['_id'] = str(c['_id'])
        return Response(contacts)

    def post(self, request):
        data = request.data
        
        required_fields = ['name', 'email']

        for field in required_fields:
            if not data.get(field):
                return Response({'error': f'{field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Add required and optional fields
        contact = {
            'contact_id': generate_contact_id(),  # Generate a unique contact ID
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone', ''),
            'secondary_email': data.get('secondary_email', ''),
            'address': data.get('address', ''),
            'agent_id': data.get('agent_id', ''),
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
    def get_object(self, contact_id):
        try:
            return get_contact_collection().find_one({'contact_id': contact_id})
        except Exception:
            return None

    def get(self, request, pk):
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        contact['_id'] = str(contact['_id'])  # Convert ObjectId to string for JSON response
        return Response(contact)

    def put(self, request, pk):
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        updated_data = request.data
        updated_data['updated_at'] = datetime.utcnow()

        get_contact_collection().update_one({'contact_id': pk}, {'$set': updated_data})
        contact.update(updated_data)
        contact['_id'] = str(contact['_id'])
        return Response(contact)

    def delete(self, request, pk):
        contact = self.get_object(pk)
        if not contact:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

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

