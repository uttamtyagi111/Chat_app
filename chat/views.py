from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import ChatRoom,Message

# @login_required
# def index(request):
#     # rooms = ChatRoom.objects.filter(created_by__username=request.user)
#     return render(request, 'chat/index.html')

# @login_required
# def room(request, room_name):
#     messages = Message.objects.filter(room__name=room_name).order_by('timestamp')
#     return render(request, 'chat/room.html', {
#         'room_name': room_name,
#         'messages': messages,
#         'username': request.user.username if request.user.is_authenticated else 'Anonymous'
#     })
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def index(request):
    return render(request, 'chat/index.html') 

import uuid

import uuid
from django.shortcuts import render

def chat_view(request):
    if not request.session.get('room_id'):
        request.session['room_id'] = str(uuid.uuid4())
        print("🎯 New Room ID assigned:", request.session['room_id'])  # Debug
    else:
        print("ℹ️ Existing Room ID:", request.session['room_id'])

    room_id = request.session['room_id']
    return render(request, 'chat/chatroom.html', {'room_id': room_id})


chat_rooms = {}  # in-memory room tracking

def user_chat(request):
    # generate unique room_id for each anonymous user
    room_id = str(uuid.uuid4())
    chat_rooms[room_id] = {'assigned_agent': None}
    return render(request, 'chat/user_chat.html', {'room_id': room_id})

def agent_dashboard(request):
    return render(request, 'chat/agent_dashboard.html', {'rooms': chat_rooms.items()})

def agent_chat(request, room_id):
    # mark agent as assigned
    if room_id in chat_rooms:
        chat_rooms[room_id]['assigned_agent'] = "Agent 007"  # replace with actual agent logic
    return render(request, 'chat/agent_chat.html', {'room_id': room_id})

from utils.redis_client import redis_client

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
