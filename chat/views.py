from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import ChatRoom,Message

@login_required
def index(request):
    rooms = ChatRoom.objects.filter(created_by=request.user)
    return render(request, 'chat/index.html', {'rooms': rooms})

@login_required
def room(request, room_name):
    messages = Message.objects.filter(room__name=room_name).order_by('timestamp')
    return render(request, 'chat/room.html', {
        'room_name': room_name,
        'messages': messages,
        'username': request.user.username if request.user.is_authenticated else 'Anonymous'
    })

