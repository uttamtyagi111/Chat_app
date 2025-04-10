from utils.redis_client import redis_client
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import logging
import uuid
import boto3
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
print(f"DEBUG: AWS_STORAGE_BUCKET_NAME = {settings.AWS_STORAGE_BUCKET_NAME}")
logger = logging.getLogger(__name__)

class UploadFileAPIView(APIView):
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
            print("Bucket name:", bucket_name)  # Debug
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


