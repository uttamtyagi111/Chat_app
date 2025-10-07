import json
import uuid
import datetime
import asyncio
import os
import magic
from channels.layers import get_channel_layer
from channels.generic.websocket import AsyncWebsocketConsumer
from wish_bot.db import (
    get_chat_collection,
    get_room_collection,
    get_shortcut_collection,
    get_trigger_collection,
    insert_with_timestamps,
    get_contact_collection,
    get_admin_collection,
    get_widget_collection,
)
from utils.redis_client import redis_client
from asgiref.sync import sync_to_async
from utils.random_id import generate_room_id, generate_contact_id
import logging
from prometheus_client import Histogram
from functools import lru_cache
from typing import Optional, List, Dict, Any

# Prometheus metrics
message_delivery_time = Histogram('message_delivery_seconds', 'Time to deliver messages')
notification_time = Histogram('notification_delivery_seconds', 'Time to deliver notifications')
chat_history_time = Histogram('chat_history_seconds', 'Time to fetch chat history')
typing_event_time = Histogram('typing_event_seconds', 'Time to process typing events')
pdf_upload_time = Histogram('pdf_upload_seconds', 'Time to process PDF uploads')

logger = logging.getLogger(__name__)

# Test Redis connection
try:
    redis_client.ping()
    logger.info("[REDIS] Connection successful")
except Exception as e:
    logger.error(f"[REDIS] Connection failed: {e}")

# Cache TTL constants
CACHE_TTL_SHORT = 60  # 1 minute
CACHE_TTL_MEDIUM = 300  # 5 minutes
CACHE_TTL_LONG = 3600  # 1 hour

def get_notifier():
    return get_channel_layer()


def convert_to_serializable(obj):
    """Recursively convert MongoDB objects to JSON-serializable format"""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__') and not isinstance(obj, (str, int, float, bool)):
        # Handle ObjectId and other MongoDB types
        return str(obj)
    else:
        return obj

async def get_agent_widgets(admin_id: str) -> List[str]:
    """Get widgets assigned to an agent with caching"""
    cache_key = f"agent_widgets:{admin_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
    
    try:
        admin_collection = await sync_to_async(get_admin_collection)()
        agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': admin_id}))()
        widgets = agent_doc.get('assigned_widgets', []) if agent_doc else []
        redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(widgets))
        return widgets
    except Exception as e:
        logger.error(f"Error getting agent widgets for {admin_id}: {e}")
        return []

async def get_room_widget(room_id: str) -> Optional[str]:
    """Get widget ID for a room with caching"""
    cache_key = f"room_widget:{room_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached
    
    try:
        room_collection = await sync_to_async(get_room_collection)()
        room = await sync_to_async(lambda: room_collection.find_one({'room_id': room_id}))()
        widget_id = room.get('widget_id') if room else None
        if widget_id:
            redis_client.setex(cache_key, CACHE_TTL_LONG, widget_id)
        return widget_id
    except Exception as e:
        logger.error(f"Error getting room widget for {room_id}: {e}")
        return None

async def get_all_widget_ids() -> List[str]:
    """Get all widget IDs with caching"""
    cache_key = "all_widgets"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
    
    try:
        collection = await sync_to_async(get_widget_collection)()
        widgets = await sync_to_async(lambda: list(collection.find({}, {'widget_id': 1})))()
        widget_ids = [w['widget_id'] for w in widgets if 'widget_id' in w]
        redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(widget_ids))
        return widget_ids
    except Exception as e:
        logger.error(f"Error getting all widget IDs: {e}")
        return []

async def is_user_superadmin(admin_id: str) -> bool:
    """Check if user is superadmin with caching"""
    cache_key = f"superadmin:{admin_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return cached.decode() == 'true' if isinstance(cached, bytes) else cached == 'true'
    
    try:
        collection = await sync_to_async(get_admin_collection)()
        doc = await sync_to_async(lambda: collection.find_one({'admin_id': admin_id}))()
        is_super = doc and doc.get('role') == 'superadmin'
        redis_client.setex(cache_key, CACHE_TTL_MEDIUM, 'true' if is_super else 'false')
        return is_super
    except Exception as e:
        logger.error(f"Error checking superadmin status for {admin_id}: {e}")
        return False

async def get_eligible_admins_for_widget(widget_id: str) -> List[Dict[str, Any]]:
    """Get all admins eligible to receive notifications for a widget"""
    cache_key = f"widget_admins:{widget_id}"
    cached = redis_client.get(cache_key)
    
    if cached:
        return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
    
    try:
        admin_collection = await sync_to_async(get_admin_collection)()
        all_admins = await sync_to_async(lambda: list(admin_collection.find({})))()
        
        eligible_admins = []
        for admin in all_admins:
            admin_id = admin.get('admin_id')
            role = admin.get('role', 'agent')
            assigned_widgets = admin.get('assigned_widgets', [])
            
            # Normalize assigned_widgets to list
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            
            # Superadmin sees all widgets, agents only see assigned widgets
            if role == 'superadmin' or widget_id in assigned_widgets:
                eligible_admins.append({
                    'admin_id': admin_id,
                    'role': role,
                    'assigned_widgets': assigned_widgets
                })
        
        redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(eligible_admins))
        return eligible_admins
    except Exception as e:
        logger.error(f"Error getting eligible admins for widget {widget_id}: {e}")
        return []

async def notify_event(event_type: str, payload: Dict[str, Any]):
    """Send notification event to eligible admins"""
    with notification_time.time():
        try:
            channel_layer = get_notifier()
            widget_id = payload.get('widget_id')
            admin_id = payload.get('admin_id')
            
            if not widget_id or not admin_id:
                logger.warning(f"notify_event - Missing widget_id or admin_id: {payload}")
                return
            
            # Clear relevant caches to force refresh
            redis_client.delete(f"dashboard_summary:{admin_id}")
            redis_client.delete(f"room_list:{admin_id}")
            
            await channel_layer.group_send(
                f'notifications_admin_{admin_id}',
                {
                    'type': 'notify_filtered',
                    'event_type': event_type,
                    'payload': payload,
                }
            )
            logger.debug(f"Sent {event_type} notification to admin {admin_id} for widget {widget_id}")
        except Exception as e:
            logger.error(f"notify_event error: {e}", exc_info=True)

async def batch_notify_admins(event_type: str, widget_id: str, base_payload: Dict[str, Any]):
    """Batch notify all eligible admins for a widget"""
    try:
        eligible_admins = await get_eligible_admins_for_widget(widget_id)
        
        # Send notifications concurrently
        tasks = []
        for admin in eligible_admins:
            admin_id = admin['admin_id']
            payload = {**base_payload, 'admin_id': admin_id}
            tasks.append(notify_event(event_type, payload))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error in batch_notify_admins: {e}")

async def cleanup_redis_keys():
    """Periodic cleanup of stale Redis keys"""
    try:
        room_collection = await sync_to_async(get_room_collection)()
        active_rooms = await sync_to_async(lambda: list(room_collection.find({'is_active': True}, {'room_id': 1})))()
        active_room_ids = set(room['room_id'] for room in active_rooms)
        
        prefixes = ['live_visitor:*', 'unread:*', 'typing:*', 'predefined:*']
        for prefix in prefixes:
            for key in redis_client.scan_iter(prefix):
                key_str = key.decode() if isinstance(key, bytes) else key
                room_id = key_str.split(':')[-1] if 'predefined' not in key_str else key_str.split(':')[1]
                if room_id not in active_room_ids:
                    redis_client.delete(key)
                    logger.debug(f"Cleaned up stale key: {key_str}")
        
        admin_collection = await sync_to_async(get_admin_collection)()
        active_admins = await sync_to_async(lambda: list(admin_collection.find({}, {'admin_id': 1})))()
        active_admin_ids = set(admin['admin_id'] for admin in active_admins)
        
        for key in redis_client.scan_iter('agent_online:*'):
            admin_id = key.decode().split(':')[-1] if isinstance(key, bytes) else key.split(':')[-1]
            if admin_id not in active_admin_ids:
                redis_client.delete(key)
                redis_client.delete(f"agent_conn_count:{admin_id}")
                logger.debug(f"Cleaned up stale agent key: {key}")
    except Exception as e:
        logger.error(f"Error in Redis cleanup: {e}")

async def validate_pdf(file_data: bytes, max_size_mb: int = 10) -> tuple:
    """Validate PDF file (MIME type and size)"""
    try:
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(file_data)
        if file_type != 'application/pdf':
            return False, "Invalid file type. Only PDFs are allowed."
        
        size_mb = len(file_data) / (1024 * 1024)
        if size_mb > max_size_mb:
            return False, f"File size exceeds {max_size_mb}MB limit."
        
        return True, None
    except Exception as e:
        logger.error(f"Error validating PDF: {e}")
        return False, "Failed to validate PDF."

async def store_pdf(file_data: bytes, file_name: str) -> tuple:
    """Store PDF file and return URL"""
    try:
        upload_dir = '/var/www/Chat_app/uploads/'
        os.makedirs(upload_dir, exist_ok=True)
        file_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{file_id}_{file_name}")
        
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        file_url = f"/uploads/{file_id}_{file_name}"
        return file_url, file_id
    except Exception as e:
        logger.error(f"Error storing PDF: {e}")
        return None, None

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
        self.user = f'user_{str(uuid.uuid4())}' if not self.is_agent else 'Agent'
        self.admin_id = self.scope.get('url_route', {}).get('kwargs', {}).get('admin_id') if self.is_agent else None

        logger.debug(f"Connection attempt - Room: {self.room_name}, Is Agent: {self.is_agent}, User: {self.user}, Agent ID: {self.admin_id}")

        # Validate room
        room_valid = await sync_to_async(self.validate_room)()
        if not room_valid:
            logger.debug(f"Room {self.room_name} is not valid, closing connection")
            await self.close()
            return

        # Get agent widgets if agent
        if self.is_agent and self.admin_id:
            self.agent_widgets = await get_agent_widgets(self.admin_id)
            logger.debug(f"Agent {self.admin_id} assigned widgets: {self.agent_widgets}")
        else:
            self.agent_widgets = []

        # Check agent access
        if self.is_agent:
            room_widget_id = await sync_to_async(self.get_widget_id_from_room)()
            if not self.can_access_room(room_widget_id):
                logger.debug(f"Agent {self.admin_id} cannot access room {self.room_name}")
                await self.close()
                return

        # Set room active for visitors
        if not self.is_agent:
            await self.set_room_active_status(self.room_name, True)
            redis_client.delete(f'unread:{self.room_name}')

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # Set agent online status
        if self.is_agent:
            await self.set_agent_online_status(True)

        await self.accept()
        logger.debug(f"WebSocket connection accepted for room: {self.room_name}")

        # Handle visitor connection
        if not self.is_agent:
            await self.handle_visitor_connection()
        else:
            # Send chat history and room list to agent
            await self.send_chat_history()
            await self.send_room_list()

    async def handle_visitor_connection(self):
        """Handle new visitor connection and notifications"""
        try:
            self.widget_id = await sync_to_async(self.get_widget_id_from_room)()
            connection_timestamp = datetime.datetime.utcnow()
            
            # Set live visitor status
            redis_client.setex(
                f"live_visitor:{self.room_name}", 
                CACHE_TTL_LONG, 
                connection_timestamp.isoformat()
            )

            # Batch notify all eligible admins
            await batch_notify_admins('new_live_visitor', self.widget_id, {
                'room_id': self.room_name,
                'widget_id': self.widget_id,
                'connection_timestamp': connection_timestamp.isoformat(),
                'visitor_id': self.user,
                'visitor_type': 'connected',
            })
            
            # Send room list update to force refresh
            await batch_notify_admins('room_list_update', self.widget_id, {
                'room_id': self.room_name,
                'widget_id': self.widget_id,
                'action': 'visitor_connected',
                'connection_timestamp': connection_timestamp.isoformat(),
                'force_refresh': True
            })

            # Load triggers and send first message
            self.triggers = await self.fetch_triggers_for_widget(self.widget_id)
            redis_client.setex(f"predefined:{self.room_name}:{self.user}", CACHE_TTL_LONG, 0)
            await self.send_trigger_message(0)
            
        except Exception as e:
            logger.error(f"Error in handle_visitor_connection: {e}", exc_info=True)

    def validate_room(self) -> bool:
        """Validate room exists and is active"""
        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            if room is None:
                logger.debug(f"Room {self.room_name} not found in database")
                return False
            return room.get('is_active', False)
        except Exception as e:
            logger.error(f"Error validating room {self.room_name}: {e}")
            return False

    def get_widget_id_from_room(self) -> Optional[str]:
        """Get widget ID from room"""
        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            return room.get('widget_id') if room else None
        except Exception as e:
            logger.error(f"Error getting widget ID for {self.room_name}: {e}")
            return None

    def can_access_room(self, room_widget_id: Optional[str]) -> bool:
        """Check if agent can access room"""
        if not self.is_agent or not self.admin_id:
            return True
        if not room_widget_id:
            return False
        return room_widget_id in self.agent_widgets

    async def set_agent_online_status(self, is_online: bool):
        """Set agent online/offline status with connection counting"""
        try:
            if self.is_agent and self.admin_id:
                status_key = f"agent_online:{self.admin_id}"
                count_key = f"agent_conn_count:{self.admin_id}"
                
                pipe = redis_client.pipeline()
                if is_online:
                    pipe.incr(count_key)
                    pipe.setex(status_key, CACHE_TTL_LONG, datetime.datetime.utcnow().isoformat())
                else:
                    pipe.decr(count_key)
                    pipe.get(count_key)
                
                results = pipe.execute()
                
                # Clean up if no more connections
                if not is_online and results[-1] and int(results[-1]) <= 0:
                    pipe = redis_client.pipeline()
                    pipe.delete(status_key)
                    pipe.delete(count_key)
                    pipe.execute()
        except Exception as e:
            logger.error(f"Error setting agent online status for {self.admin_id}: {e}")

    async def fetch_triggers_for_widget(self, widget_id: str) -> List[Dict]:
        """Fetch triggers for widget with caching"""
        if not widget_id:
            logger.debug("No widget_id provided, cannot fetch triggers")
            return []
        
        cache_key = f"triggers:{widget_id}"
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached.decode() if isinstance(cached, bytes) else cached)
        
        try:
            collection = await sync_to_async(get_trigger_collection)()
            triggers = await sync_to_async(lambda: list(
                collection.find({'widget_id': widget_id, 'is_active': True}).sort('order', 1)
            ))()
            
            # Convert MongoDB document to serializable format
            serializable_triggers = []
            for trigger in triggers:
                serializable_trigger = {}
                for key, value in trigger.items():
                    # Convert ObjectId to string
                    if key == '_id':
                        serializable_trigger[key] = str(value)
                    # Convert datetime objects to ISO format strings
                    elif isinstance(value, datetime.datetime):
                        serializable_trigger[key] = value.isoformat()
                    # Handle nested dictionaries
                    elif isinstance(value, dict):
                        serializable_trigger[key] = convert_to_serializable(value)
                    # Handle lists
                    elif isinstance(value, list):
                        serializable_trigger[key] = [
                            convert_to_serializable(item) if isinstance(item, (dict, list)) 
                            else item.isoformat() if isinstance(item, datetime.datetime)
                            else str(item) if hasattr(item, '__dict__') and not isinstance(item, (str, int, float, bool))
                            else item
                            for item in value
                        ]
                    # Handle other MongoDB types
                    elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool)):
                        serializable_trigger[key] = str(value)
                    else:
                        serializable_trigger[key] = value
                
                serializable_triggers.append(serializable_trigger)
            
            redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(serializable_triggers))
            return serializable_triggers
        except Exception as e:
            logger.error(f"Error fetching triggers for widget {widget_id}: {e}")
            return []

    async def send_trigger_message(self, index: int):
        """Send trigger message to visitor"""
        try:
            if self.is_agent:
                return
            
            if not hasattr(self, 'triggers') or not self.triggers or index >= len(self.triggers):
                return

            trigger = self.triggers[index]
            message = trigger.get('message')
            suggested_replies = trigger.get('suggested_replies', [])
            timestamp = datetime.datetime.utcnow()
            message_id = generate_room_id()

            doc = {
                'message_id': message_id,
                'room_id': self.room_name,
                'sender': 'Wish-bot',
                'message': message,
                'file_url': '',
                'file_name': '',
                'delivered': True,
                'seen': False,
                'timestamp': timestamp
                
            }

            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(insert_with_timestamps)(collection, doc)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'room_id': self.room_name,
                    'sender': 'Wish-bot',
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat(),
                    'suggested_replies': suggested_replies,
                    "is_trigger": True
                }
            )
        except Exception as e:
            logger.error(f"Error in send_trigger_message: {e}", exc_info=True)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        try:
            if hasattr(self, 'room_name'):
                disconnect_timestamp = datetime.datetime.utcnow()
                
                # Handle visitor disconnect
                if not self.is_agent:
                    redis_client.delete(f'live_visitor:{self.room_name}')
                    widget_id = getattr(self, 'widget_id', None) or await sync_to_async(self.get_widget_id_from_room)()
                    
                    if widget_id:
                        # Batch notify admins about disconnect
                        await batch_notify_admins('visitor_disconnected', widget_id, {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'disconnect_timestamp': disconnect_timestamp.isoformat(),
                            'visitor_id': self.user,
                            'close_code': close_code,
                        })
                        
                        await batch_notify_admins('room_list_update', widget_id, {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'action': 'visitor_disconnected',
                            'disconnect_timestamp': disconnect_timestamp.isoformat(),
                        })

                # Handle agent disconnect
                if self.is_agent:
                    await self.set_agent_online_status(False)

                # Clean up typing indicators
                redis_client.delete(f'typing:{self.room_name}:{self.user}')
                if not self.is_agent:
                    redis_client.delete(f'predefined:{self.room_name}:{self.user}')

                # Leave room group
                await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
                
                # Clean up stale keys
                await cleanup_redis_keys()
        except Exception as e:
            logger.error(f"Error in disconnect: {e}", exc_info=True)

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages"""
        try:
            # Parse data
            if text_data:
                data = json.loads(text_data)
            elif bytes_data:
                data = {'file_data': bytes_data}
            else:
                await self.send(text_data=json.dumps({'error': 'No data provided'}))
                return

            collection = await sync_to_async(get_chat_collection)()

            # Handle specific actions
            if data.get('action') == 'get_room_list' and self.is_agent:
                await self.send_room_list()
                return

            if data.get('action') == 'heartbeat' and self.is_agent:
                await self.set_agent_online_status(True)
                return

            if data.get('action') == 'mark_room_read' and self.is_agent:
                await self.mark_room_messages_read(data.get('room_id', self.room_name))
                return

            # Rate limiting for non-agent messages
            if not self.is_agent and (data.get('message') or data.get('file_url') or data.get('form_data') or data.get('file_data')):
                if not await self.check_rate_limit():
                    await self.send(text_data=json.dumps({'error': 'Rate limit exceeded.'}))
                    return

            # Handle typing indicators
            if data.get('typing') is not None and 'content' in data:
                await self.handle_typing(data)
                return

            # Handle seen status
            if data.get('status') == 'seen' and data.get('message_id'):
                await self.handle_seen_status(data, collection)
                return

            # Handle form submission
            if data.get('form_data'):
                await self.handle_form_data(data, collection)
                return

            # Handle file upload
            if data.get('file_data'):
                await self.handle_new_message({
                    'file_data': data.get('file_data'), 
                    'file_name': data.get('file_name', 'document.pdf')
                }, collection)
                return

            # Handle regular messages
            if data.get('message') or data.get('file_url'):
                await self.handle_new_message(data, collection)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await self.send(text_data=json.dumps({'error': 'Invalid message format'}))
        except Exception as e:
            logger.error(f"Error in receive: {e}", exc_info=True)

    async def check_rate_limit(self) -> bool:
        """Check rate limit for user messages"""
        try:
            rate_limit_key = f"rate_limit:{self.user}"
            current_time = datetime.datetime.utcnow()
            last_message_time = redis_client.get(rate_limit_key)
            
            if last_message_time:
                try:
                    last_time = datetime.datetime.fromisoformat(
                        last_message_time.decode() if isinstance(last_message_time, bytes) else last_message_time
                    )
                    if (current_time - last_time) < datetime.timedelta(seconds=1):
                        return False
                except ValueError:
                    redis_client.delete(rate_limit_key)
            
            redis_client.setex(rate_limit_key, 60, current_time.isoformat())
            return True
        except Exception as e:
            logger.error(f"Error in rate limit check: {e}")
            return True

    async def mark_room_messages_read(self, room_id: str):
        """Mark all messages in room as read"""
        try:
            room_widget_id = await get_room_widget(room_id)
            if not self.can_access_room(room_widget_id):
                return

            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(collection.update_many)(
                {'room_id': room_id, 'seen': False, 'sender': {'$ne': 'agent'}},
                {'$set': {'seen': True, 'seen_at': datetime.datetime.utcnow()}}
            )

            # Clear unread count
            unread_key = f'unread:{room_id}'
            redis_client.delete(unread_key)
            logger.debug(f"Cleared unread count for room {room_id}")

            # Notify admins of unread update
            await batch_notify_admins('unread_update', room_widget_id, {
                'room_id': room_id,
                'widget_id': room_widget_id,
                'unread_count': 0,
                'timestamp': datetime.datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error marking room messages as read: {e}")

    async def handle_typing(self, data: Dict[str, Any]):
        """Handle typing indicator"""
        with typing_event_time.time():
            try:
                typing = data.get('typing', False)
                content = data.get('content', '')
                typing_key = f'typing:{self.room_name}:{self.user}'
                
                # Throttle typing events
                last_sent = redis_client.get(f"{typing_key}:last_sent")
                if last_sent:
                    last_time = datetime.datetime.fromisoformat(
                        last_sent.decode() if isinstance(last_sent, bytes) else last_sent
                    )
                    if (datetime.datetime.utcnow() - last_time).total_seconds() < 1:
                        return
                
                # Update typing status
                pipe = redis_client.pipeline()
                if typing:
                    pipe.setex(typing_key, 10, content)
                    pipe.setex(f"{typing_key}:last_sent", 10, datetime.datetime.utcnow().isoformat())
                else:
                    pipe.delete(typing_key)
                    pipe.delete(f"{typing_key}:last_sent")
                pipe.execute()

                # Broadcast typing status
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_status',
                        'typing': typing,
                        'content': content,
                        'sender': self.user,
                        'is_agent': self.is_agent
                    }
                )
            except Exception as e:
                logger.error(f"Error handling typing: {e}")

    async def handle_seen_status(self, data: Dict[str, Any], collection):
        """Handle message seen status update"""
        try:
            message_id = data.get('message_id')
            sender = data.get('sender', self.user)
            
            if not message_id:
                logger.warning(f"handle_seen_status: No message_id provided for room {self.room_name}")
                return

            # Update message seen status
            result = await sync_to_async(collection.update_one)(
                {'message_id': message_id, 'room_id': self.room_name},
                {'$set': {'seen': True, 'seen_at': datetime.datetime.utcnow()}}
            )

            if result.modified_count == 0:
                logger.warning(f"handle_seen_status: No message updated for {message_id}")
                return

            logger.debug(f"handle_seen_status: Marked message {message_id} as seen")

            # Update unread count for agents
            if self.is_agent:
                unread_key = f'unread:{self.room_name}'
                current_unread = int(redis_client.get(unread_key) or 0)
                
                if current_unread > 0:
                    new_unread = max(0, current_unread - 1)
                    if new_unread == 0:
                        redis_client.delete(unread_key)
                    else:
                        redis_client.set(unread_key, new_unread)
                    
                    room_widget_id = await get_room_widget(self.room_name)
                    if room_widget_id:
                        await batch_notify_admins('unread_update', room_widget_id, {
                            'room_id': self.room_name,
                            'widget_id': room_widget_id,
                            'unread_count': new_unread,
                            'timestamp': datetime.datetime.utcnow().isoformat(),
                        })

            # Broadcast seen status to all clients
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_seen',
                    'message_id': message_id,
                    'sender': sender,
                    'timestamp': datetime.datetime.utcnow().isoformat(),
                    'contact_id': data.get('contact_id', '')
                }
            )
        except Exception as e:
            logger.error(f"Error in handle_seen_status: {e}", exc_info=True)

    async def handle_form_data(self, data: Dict[str, Any], collection):
        """Handle contact form submission"""
        try:
            form_data = data.get('form_data', {})
            message_id = data.get('message_id') or generate_room_id()
            timestamp = datetime.datetime.utcnow()
            name = form_data.get('name', '')
            email = form_data.get('email', '')
            phone = form_data.get('phone', '')

            # Get or create contact
            contact_collection = await sync_to_async(get_contact_collection)()
            room_collection = await sync_to_async(get_room_collection)()
            room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
            contact_id = room.get('contact_id') if room and room.get('contact_id') else generate_contact_id()
            widget_id = room.get('widget_id') if room else None

            # Save contact
            contact_doc = {
                'contact_id': contact_id,
                'room_id': self.room_name,
                'name': name,
                'email': email,
                'phone': phone,
                'widget_id': widget_id,
                'timestamp': timestamp
            }
            await sync_to_async(insert_with_timestamps)(contact_collection, contact_doc)

            # Save message
            message = f"Contact information submitted: {name} ({email})"
            doc = {
                'message_id': message_id,
                'room_id': self.room_name,
                'contact_id': contact_id,
                'sender': self.user,
                'message': message,
                'file_url': '',
                'file_name': '',
                'delivered': True,
                'seen': False,
                'timestamp': timestamp,
                'form_data': form_data
            }
            await sync_to_async(insert_with_timestamps)(collection, doc)

            # Update unread count and notify admins
            if not self.is_agent and widget_id:
                unread_key = f'unread:{self.room_name}'
                redis_client.incr(unread_key)
                unread_count = int(redis_client.get(unread_key) or 0)
                
                # Batch notify admins
                await batch_notify_admins('unread_update', widget_id, {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'unread_count': unread_count,
                    'timestamp': timestamp.isoformat(),
                })
                
                await batch_notify_admins('new_contact', widget_id, {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'contact_info': contact_doc,
                    'timestamp': timestamp.isoformat(),
                })
                
                await batch_notify_admins('room_list_update', widget_id, {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'action': 'contact_added',
                    'timestamp': timestamp.isoformat(),
                })

            # Broadcast message
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'contact_id': contact_id,
                    'sender': self.user,
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat(),
                    'form_data': form_data
                }
            )
        except Exception as e:
            logger.error(f"Error handling form data: {e}", exc_info=True)
            await self.send(text_data=json.dumps({'error': 'Failed to submit form data'}))

    async def handle_new_message(self, data: Dict[str, Any], collection):
        """Handle new message with optimized notifications"""
        with message_delivery_time.time():
            try:
                from bson import ObjectId
                timestamp = datetime.datetime.utcnow()
                timestamp_iso = timestamp.isoformat()
                message_id = data.get('message_id') or generate_room_id()
                contact_id = data.get('contact_id')
                sender = data.get('sender', self.user)
                shortcut_id = data.get('shortcut_id')
                file_url = data.get('file_url', '')
                file_name = data.get('file_name', '')
                display_sender_name = sender

                # Fetch room details
                room_collection = await sync_to_async(get_room_collection)()
                room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
                if not room:
                    logger.error(f"Room {self.room_name} not found")
                    return None

                # Get room metadata
                if not contact_id:
                    contact_id = room.get('contact_id') or generate_contact_id()
                widget_id = room.get('widget_id')
                assigned_admin_id = room.get('assigned_agent')

                # Set display name for agent
                if sender == 'agent' and assigned_admin_id:
                    admin_collection = await sync_to_async(get_admin_collection)()
                    agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': assigned_admin_id}))()
                    if agent_doc:
                        display_sender_name = agent_doc.get('name') or 'Agent'

                # Handle file upload (PDF)
                if data.get('file_data'):
                    with pdf_upload_time.time():
                        is_valid, error = await validate_pdf(data['file_data'])
                        if not is_valid:
                            await self.send(text_data=json.dumps({'error': error}))
                            return None
                        
                        file_url, file_id = await store_pdf(data['file_data'], data.get('file_name', 'document.pdf'))
                        if not file_url:
                            await self.send(text_data=json.dumps({'error': 'Failed to store PDF'}))
                            return None
                        file_name = data.get('file_name', 'document.pdf')
                        message = f"PDF uploaded: {file_name}"
                else:
                    message = data.get('message', '')

                # Handle shortcut messages
                suggested_replies = []
                is_shortcut = False
                if shortcut_id:
                    shortcut_collection = await sync_to_async(get_shortcut_collection)()
                    shortcut_doc = await sync_to_async(lambda: shortcut_collection.find_one({'shortcut_id': shortcut_id}))()
                    if shortcut_doc:
                        message = shortcut_doc.get('content', '')
                        suggested_replies = shortcut_doc.get('suggested_messages', [])
                        is_shortcut = True

                # Store message in DB
                doc = {
                    'message_id': message_id,
                    'room_id': self.room_name,
                    'contact_id': contact_id,
                    'sender': display_sender_name,
                    'message': message,
                    'file_url': file_url,
                    'file_name': file_name,
                    'delivered': True,
                    'seen': False,
                    'timestamp': timestamp,
                    'is_shortcut': is_shortcut,
                    'shortcut_id': shortcut_id if is_shortcut else None,
                    'suggested_replies': suggested_replies
                }
                await sync_to_async(insert_with_timestamps)(collection, doc)

                # Update chat history cache
                cache_key = f"chat_history:{self.room_name}"
                try:
                    cached = redis_client.get(cache_key)
                    if cached:
                        messages = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
                        messages.append({
                            k: v.isoformat() if isinstance(v, datetime.datetime) else str(v) if isinstance(v, ObjectId) else v 
                            for k, v in doc.items()
                        })
                        if len(messages) > 50:
                            messages = messages[-50:]
                        redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(messages))
                except Exception as e:
                    logger.error(f"Error updating chat cache: {e}")

                # Handle unread count for user messages
                new_unread = 0
                if not self.is_agent:
                    try:
                        unread_key = f'unread:{self.room_name}'
                        lua_script = """
                        local key = KEYS[1]
                        local new = redis.call('INCR', key)
                        return new
                        """
                        script = redis_client.register_script(lua_script)
                        new_unread = int(script(keys=[unread_key]))
                        logger.debug(f"Updated unread count for {self.room_name}: {new_unread}")
                    except Exception as e:
                        logger.error(f"Error updating unread count: {e}")

                # Broadcast message to room group
                message_data = {
                    'type': 'chat_message',
                    'room_id': self.room_name,
                    'message': message,
                    'contact_id': contact_id,
                    'sender': display_sender_name,
                    'message_id': message_id,
                    'file_url': file_url,
                    'file_name': file_name,
                    'timestamp': timestamp_iso,
                    'suggested_replies': suggested_replies,
                    'shortcut_id': shortcut_id if is_shortcut else None,
                    'is_shortcut': is_shortcut,
                    'sender_type': 'user' if not self.is_agent else 'agent',
                    'status': 'delivered'
                }
                await self.channel_layer.group_send(self.room_group_name, message_data)

                # Send notifications for user messages
                if not self.is_agent and widget_id:
                    try:
                        # Batch notify all eligible admins
                        notify_data = {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'message': {
                                k: v.isoformat() if isinstance(v, datetime.datetime) else str(v) if isinstance(v, ObjectId) else v 
                                for k, v in doc.items()
                            },
                            'unread_count': new_unread,
                            'timestamp': timestamp_iso,
                            'sender_type': 'user'
                        }
                        
                        await batch_notify_admins('new_message_agent', widget_id, notify_data)
                        await batch_notify_admins('unread_update', widget_id, {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'unread_count': new_unread,
                            'timestamp': timestamp_iso,
                        })
                        await batch_notify_admins('room_list_update', widget_id, {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'action': 'new_message',
                            'timestamp': timestamp_iso,
                        })
                    except Exception as e:
                        logger.error(f"Error sending notifications: {e}")

                # Handle trigger messages for users
                if not self.is_agent:
                    redis_key = f"predefined:{self.room_name}:{self.user}"
                    current_index = int(redis_client.get(redis_key) or 0)
                    next_index = current_index + 1
                    if hasattr(self, 'triggers') and self.triggers and next_index < len(self.triggers):
                        redis_client.setex(redis_key, CACHE_TTL_LONG, next_index)
                        await asyncio.sleep(0.5)
                        await self.send_trigger_message(next_index)
                        if next_index == 1:
                            await self.send_show_form_signal()

                return {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'message': message,
                    'file_url': file_url,
                    'file_name': file_name,
                    'message_id': message_id,
                    'contact_id': contact_id,
                    'sender': display_sender_name,
                    'timestamp': timestamp_iso,
                    'suggested_replies': suggested_replies
                }
            except Exception as e:
                logger.error(f"Error in handle_new_message: {e}", exc_info=True)
                return None

    async def chat_message(self, event):
        """Send chat message to client"""
        with message_delivery_time.time():
            try:
                if event.get('room_id') != self.room_name:
                    return

                message_data = {
                    'message': event['message'],
                    'sender': event['sender'],
                    'message_id': event['message_id'],
                    'file_url': event.get('file_url', ''),
                    'file_name': event.get('file_name', ''),
                    'timestamp': event['timestamp'],
                    'status': 'delivered',
                    'suggested_replies': event.get('suggested_replies', []),
                    'contact_id': event.get('contact_id', ''),
                    'shortcut_id': event.get('shortcut_id'),
                    'is_shortcut': event.get('is_shortcut', False),
                    'sender_type': event.get('sender_type', 'unknown')
                }
                await self.send(text_data=json.dumps(message_data))
            except Exception as e:
                logger.error(f"Error in chat_message: {e}", exc_info=True)

    async def send_chat_history(self):
        """Send chat history to client"""
        with chat_history_time.time():
            try:
                room_widget_id = await get_room_widget(self.room_name)
                if not self.can_access_room(room_widget_id):
                    await self.send(text_data=json.dumps({'error': 'Access denied'}))
                    return
                
                cache_key = f"chat_history:{self.room_name}"
                cached = redis_client.get(cache_key)
                
                if cached:
                    messages = json.loads(cached.decode() if isinstance(cached, bytes) else cached)
                else:
                    collection = await sync_to_async(get_chat_collection)()
                    messages = await sync_to_async(lambda: list(
                        collection.find({'room_id': self.room_name}, {'_id': 0}).sort('timestamp', -1).limit(50)
                    ))()
                    redis_client.setex(cache_key, CACHE_TTL_MEDIUM, json.dumps(messages))

                for msg in reversed(messages):
                    await self.send(text_data=json.dumps({
                        'message': msg.get('message', ''),
                        'sender': msg.get('sender', 'unknown'),
                        'message_id': msg.get('message_id', ''),
                        'file_url': msg.get('file_url', ''),
                        'file_name': msg.get('file_name', ''),
                        'timestamp': msg.get('timestamp', ''),
                        'status': 'history',
                        'contact_id': msg.get('contact_id', '')
                    }))
            except Exception as e:
                logger.error(f"Error sending chat history: {e}")

    async def send_room_list(self):
        """Send room list to agent"""
        try:
            cache_key = f"room_list:{self.admin_id}"
            cached = redis_client.get(cache_key)
            if cached:
                await self.send(text_data=cached.decode() if isinstance(cached, bytes) else cached)
                return

            room_collection = await sync_to_async(get_room_collection)()
            chat_collection = await sync_to_async(get_chat_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()

            # Filter rooms by widget access
            if self.is_agent and self.agent_widgets:
                rooms = await sync_to_async(lambda: list(
                    room_collection.find({'is_active': True, 'widget_id': {'$in': self.agent_widgets}})
                ))()
            else:
                rooms = await sync_to_async(lambda: list(
                    room_collection.find({'is_active': True})
                ))()

            # Batch fetch live and unread status
            pipe = redis_client.pipeline()
            for room in rooms:
                room_id = room['room_id']
                pipe.exists(f'live_visitor:{room_id}')
                pipe.get(f'unread:{room_id}')
            results = pipe.execute()
            live_statuses = results[::2]
            unread_counts = results[1::2]

            room_list = []
            total_unread = 0
            live_rooms = []
            current_time = datetime.datetime.utcnow()

            for idx, room in enumerate(rooms):
                room_id = room['room_id']
                assigned_agent = room.get('assigned_agent')
                
                # Filter by assigned agent
                if self.is_agent and assigned_agent and assigned_agent not in [None, 'agent', 'superadmin', self.admin_id]:
                    continue

                # Fetch last message and contact
                last_message = await sync_to_async(lambda: chat_collection.find_one(
                    {'room_id': room_id}, sort=[('timestamp', -1)]
                ))()
                contact_doc = await sync_to_async(lambda: contact_collection.find_one({'room_id': room_id}))()
                
                unread_count = int(unread_counts[idx] or 0)
                total_unread += unread_count

                is_live = bool(live_statuses[idx])
                if is_live:
                    live_rooms.append(room_id)

                timestamp = last_message.get('timestamp') if last_message else None
                timestamp_str = timestamp if isinstance(timestamp, str) else (
                    timestamp.isoformat() if isinstance(timestamp, datetime.datetime) else ''
                )

                # Create sorting timestamp - use epoch seconds for reliable sorting
                # Live rooms get current time (highest priority)
                # Rooms with messages get their timestamp
                # Rooms without messages get 0 (lowest priority)
                if is_live:
                    sorting_value = current_time.timestamp()
                elif isinstance(timestamp, datetime.datetime):
                    sorting_value = timestamp.timestamp()
                elif isinstance(timestamp, str):
                    try:
                        sorting_value = datetime.datetime.fromisoformat(timestamp).timestamp()
                    except (ValueError, AttributeError):
                        sorting_value = 0
                else:
                    sorting_value = 0

                room_list.append({
                    'room_id': room_id,
                    'widget_id': room.get('widget_id'),
                    'contact': {
                        'name': contact_doc.get('name') if contact_doc else '',
                        'email': contact_doc.get('email') if contact_doc else '',
                        'phone': contact_doc.get('phone') if contact_doc else ''
                    },
                    'latest_message': last_message.get('message') if last_message else '',
                    'latest_message_sender': last_message.get('sender') if last_message else '',
                    'timestamp': timestamp_str,
                    'sorting_value': sorting_value,
                    'unread_count': unread_count,
                    'has_unread': unread_count > 0,
                    'assigned_agent': assigned_agent,
                    'is_live': is_live
                })

            # Sort rooms: live first (descending sorting_value), then by timestamp (descending)
            room_list.sort(key=lambda x: (not x['is_live'], -x['sorting_value']))

            # Remove sorting helper
            for room in room_list:
                room.pop('sorting_value', None)

            response = json.dumps({
                'type': 'room_list',
                'rooms': room_list,
                'total_unread': total_unread,
                'live_room_ids': live_rooms,
                'agent_widgets': self.agent_widgets if self.is_agent else [],
                'timestamp': datetime.datetime.utcnow().isoformat()
            })

            redis_client.setex(cache_key, CACHE_TTL_SHORT, response)
            await self.send(text_data=response)
        except Exception as e:
            logger.error(f"Error sending room list: {e}", exc_info=True)

    async def send_show_form_signal(self):
        """Send signal to show contact form"""
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'show_form_signal',
                    'show_form': True,
                    'form_type': 'contact'
                }
            )
        except Exception as e:
            logger.error(f"Error sending show form signal: {e}")

    async def typing_status(self, event):
        """Handle typing status event"""
        if event['sender'] != self.user:
            display_name = "Agent" if event.get('is_agent', False) else "User"
            await self.send(text_data=json.dumps({
                'type': 'typing_status',
                'typing': event['typing'],
                'content': event.get('content', ''),
                'sender': display_name,
                'original_sender': event['sender']
            }))

    async def message_seen(self, event):
        """Handle message seen event"""
        await self.send(text_data=json.dumps({
            'type': 'message_seen',
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp'],
            'contact_id': event.get('contact_id', '')
        }))

    async def show_form_signal(self, event):
        """Handle show form signal event"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'show_form_signal',
                'show_form': event['show_form'],
                'form_type': event['form_type']
            }))
        except Exception as e:
            logger.error(f"Error in show_form_signal: {e}")

    @sync_to_async
    def set_room_active_status(self, room_id: str, status: bool):
        """Set room active status"""
        try:
            collection = get_room_collection()
            result = collection.update_one(
                {'room_id': room_id},
                {'$set': {'is_active': status}},
                upsert=True
            )
            logger.debug(f"Room status update for {room_id}: {result.modified_count} modified")
            
            if not status:
                # Clean up caches for inactive room
                redis_client.delete(f"room_widget:{room_id}")
                redis_client.delete(f"chat_history:{room_id}")
                redis_client.delete(f"unread:{room_id}")
                redis_client.delete(f"live_visitor:{room_id}")
                for key in redis_client.scan_iter(f"predefined:{room_id}:*"):
                    redis_client.delete(key)
        except Exception as e:
            logger.error(f"Error updating room status for {room_id}: {e}")


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle notification WebSocket connection"""
        self.admin_id = self.scope.get('url_route', {}).get('kwargs', {}).get('admin_id')
        self.query_string = self.scope.get('query_string', b'').decode()
        self.is_agent = 'agent=true' in self.query_string
        self.is_superadmin = await is_user_superadmin(self.admin_id)

        if not self.admin_id:
            await self.close()
            return

        # Get widgets for filtering
        if self.is_superadmin:
            self.agent_widgets = await get_all_widget_ids()
        else:
            self.agent_widgets = await get_agent_widgets(self.admin_id)

        # Join notification group
        await self.channel_layer.group_add(f'notifications_admin_{self.admin_id}', self.channel_name)
        await self.accept()
        
        # Send initial dashboard summary
        await self.send_dashboard_summary()
        
        # Set agent online
        redis_client.setex(f"agent_online:{self.admin_id}", CACHE_TTL_LONG, datetime.datetime.utcnow().isoformat())
        logger.debug(f"NotificationConsumer connected for admin {self.admin_id}")

    async def disconnect(self, close_code):
        """Handle notification WebSocket disconnection"""
        try:
            await self.channel_layer.group_discard(f'notifications_admin_{self.admin_id}', self.channel_name)
            if self.admin_id:
                await self.set_agent_online_status(False)
            await cleanup_redis_keys()
            logger.debug(f"NotificationConsumer disconnected for admin {self.admin_id}")
        except Exception as e:
            logger.error(f"Error in NotificationConsumer disconnect: {e}")

    async def set_agent_online_status(self, is_online: bool):
        """Set agent online/offline status"""
        try:
            if self.admin_id:
                status_key = f"agent_online:{self.admin_id}"
                count_key = f"agent_conn_count:{self.admin_id}"
                
                pipe = redis_client.pipeline()
                if is_online:
                    pipe.incr(count_key)
                    pipe.setex(status_key, CACHE_TTL_LONG, datetime.datetime.utcnow().isoformat())
                else:
                    pipe.decr(count_key)
                    pipe.get(count_key)
                
                results = pipe.execute()
                
                if not is_online and results[-1] and int(results[-1]) <= 0:
                    pipe = redis_client.pipeline()
                    pipe.delete(status_key)
                    pipe.delete(count_key)
                    pipe.execute()
        except Exception as e:
            logger.error(f"Error setting agent online status: {e}")

    async def receive(self, text_data):
        """Handle incoming notification messages"""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'get_dashboard_summary':
                await self.send_dashboard_summary()
            elif action == 'heartbeat':
                redis_client.setex(f"agent_online:{self.admin_id}", CACHE_TTL_LONG, datetime.datetime.utcnow().isoformat())
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_response',
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }))
            elif action in ['mark_messages_read', 'mark_room_read']:
                room_id = data.get('payload', {}).get('room_id')
                if room_id:
                    await self.mark_room_messages_read(room_id)
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in NotificationConsumer: {e}")
        except Exception as e:
            logger.error(f"Error in NotificationConsumer receive: {e}")

    def can_access_room(self, room_widget_id: Optional[str]) -> bool:
        """Check if admin can access room"""
        if self.is_superadmin:
            return True
        if not room_widget_id:
            return False
        return room_widget_id in self.agent_widgets

    async def mark_room_messages_read(self, room_id: str):
        """Mark all messages in room as read"""
        try:
            room_widget_id = await get_room_widget(room_id)
            if not self.can_access_room(room_widget_id):
                return

            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(collection.update_many)(
                {'room_id': room_id, 'seen': False, 'sender': {'$ne': 'agent'}},
                {'$set': {'seen': True, 'seen_at': datetime.datetime.utcnow()}}
            )

            unread_key = f'unread:{room_id}'
            redis_client.delete(unread_key)
            logger.debug(f"Cleared unread count for room {room_id}")

            await batch_notify_admins('unread_update', room_widget_id, {
                'room_id': room_id,
                'widget_id': room_widget_id,
                'unread_count': 0,
                'timestamp': datetime.datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error marking room messages as read: {e}")

    async def send_dashboard_summary(self):
        """Send dashboard summary to admin"""
        try:
            cache_key = f"dashboard_summary:{self.admin_id}"
            cached = redis_client.get(cache_key)
            if cached:
                await self.send(text_data=cached.decode() if isinstance(cached, bytes) else cached)
                return

            room_collection = await sync_to_async(get_room_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()

            # Filter by widgets
            widget_filter = {'widget_id': {'$in': self.agent_widgets}} if self.agent_widgets else {}
            rooms = await sync_to_async(lambda: list(room_collection.find({
                'is_active': True,
                **widget_filter
            }, {'room_id': 1, 'assigned_agent': 1, 'widget_id': 1})))()

            total_rooms = len(rooms)
            total_unread = 0
            rooms_with_unread = 0
            live_rooms = []
            assigned_rooms = []

            # Batch fetch live and unread status
            pipe = redis_client.pipeline()
            for room in rooms:
                room_id = room['room_id']
                pipe.exists(f'live_visitor:{room_id}')
                pipe.get(f'unread:{room_id}')
            results = pipe.execute()
            live_statuses = results[::2]
            unread_counts = results[1::2]

            for idx, room in enumerate(rooms):
                room_id = room['room_id']
                assigned_agent = room.get('assigned_agent')
                unread = int(unread_counts[idx] or 0)

                # Count unread only for accessible rooms
                if self.is_superadmin or assigned_agent == self.admin_id or assigned_agent is None:
                    total_unread += unread
                    if unread > 0:
                        rooms_with_unread += 1

                if bool(live_statuses[idx]):
                    live_rooms.append(room_id)
                if assigned_agent == self.admin_id or self.is_superadmin:
                    assigned_rooms.append(room_id)

            # Count contacts today
            today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            contacts_today = await sync_to_async(lambda: contact_collection.count_documents({
                'timestamp': {'$gte': today},
                **widget_filter
            }))()

            # Count online agents
            online_agents = len([key for key in redis_client.scan_iter('agent_online:*')])

            response = json.dumps({
                'type': 'dashboard_summary',
                'data': {
                    'total_rooms': total_rooms,
                    'total_unread': total_unread,
                    'rooms_with_unread': rooms_with_unread,
                    'contacts_today': contacts_today,
                    'online_agents': online_agents,
                    'live_visitors': len(live_rooms),
                    'assigned_rooms': len(assigned_rooms),
                    'live_room_ids': live_rooms,
                    'assigned_room_ids': assigned_rooms,
                    'agent_widgets': self.agent_widgets,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }
            })

            redis_client.setex(cache_key, 30, response)
            await self.send(text_data=response)
        except Exception as e:
            logger.error(f"Error sending dashboard summary: {e}", exc_info=True)

    async def notify_filtered(self, event):
        """Handle filtered notification events"""
        try:
            event_type = event.get('event_type')
            payload = event.get('payload', {})
            widget_id = payload.get('widget_id')

            # Clear caches for important events
            should_refresh = event_type in [
                'new_message_agent', 
                'unread_update', 
                'new_contact', 
                'new_room', 
                'new_live_visitor', 
                'visitor_disconnected', 
                'room_list_update'
            ]
            
            if should_refresh:
                redis_client.delete(f"dashboard_summary:{self.admin_id}")
                redis_client.delete(f"room_list:{self.admin_id}")
                
                # Force immediate refresh for live visitor events
                if event_type in ['new_live_visitor', 'visitor_disconnected'] or payload.get('force_refresh'):
                    # Send dashboard summary
                    await self.send_dashboard_summary()
                    
                    # Send refresh signal
                    await self.send(text_data=json.dumps({
                        'type': 'refresh_room_list',
                        'timestamp': datetime.datetime.utcnow().isoformat()
                    }))

            # Send the event to the admin
            await self.send(text_data=json.dumps({
                'type': f'dashboard_{event_type}',
                'payload': payload,
                'timestamp': datetime.datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error in notify_filtered: {e}", exc_info=True)


# Utility functions for external use

async def get_unread_summary_by_widget(widget_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Get unread message summary grouped by widget"""
    try:
        room_collection = await sync_to_async(get_room_collection)()
        widget_filter = {'widget_id': {'$in': widget_ids}} if widget_ids else {}
        
        rooms = await sync_to_async(lambda: list(
            room_collection.find({'is_active': True, **widget_filter}, {'room_id': 1, 'widget_id': 1})
        ))()
        
        unread_summary = {
            'total_unread': 0,
            'rooms_with_unread': 0,
            'room_details': [],
            'widget_breakdown': {}
        }
        
        # Batch fetch unread counts
        pipe = redis_client.pipeline()
        for room in rooms:
            pipe.get(f'unread:{room["room_id"]}')
        unread_counts = pipe.execute()
        
        for idx, room in enumerate(rooms):
            room_id = room['room_id']
            room_widget_id = room.get('widget_id')
            unread_count = int(unread_counts[idx] or 0)
            
            if unread_count > 0:
                unread_summary['total_unread'] += unread_count
                unread_summary['rooms_with_unread'] += 1
                unread_summary['room_details'].append({
                    'room_id': room_id,
                    'widget_id': room_widget_id,
                    'unread_count': unread_count
                })
                
                if room_widget_id:
                    if room_widget_id not in unread_summary['widget_breakdown']:
                        unread_summary['widget_breakdown'][room_widget_id] = {
                            'unread_count': 0,
                            'rooms_count': 0
                        }
                    unread_summary['widget_breakdown'][room_widget_id]['unread_count'] += unread_count
                    unread_summary['widget_breakdown'][room_widget_id]['rooms_count'] += 1
        
        return unread_summary
    except Exception as e:
        logger.error(f"Error getting unread summary by widget: {e}")
        return {
            'total_unread': 0,
            'rooms_with_unread': 0,
            'room_details': [],
            'widget_breakdown': {}
        }


def get_agent_notification_preferences(admin_id: str) -> Dict[str, Any]:
    """Get agent notification preferences"""
    pref_key = f"agent_prefs:{admin_id}"
    prefs = redis_client.get(pref_key)
    if prefs:
        return json.loads(prefs.decode() if isinstance(prefs, bytes) else prefs)
    
    default_prefs = {
        'new_messages': True,
        'new_contacts': True,
        'room_updates': True,
        'sound_notifications': True,
        'desktop_notifications': True,
        'widget_filter': True
    }
    redis_client.setex(pref_key, 86400, json.dumps(default_prefs))
    return default_prefs


def set_agent_notification_preferences(admin_id: str, preferences: Dict[str, Any]):
    """Set agent notification preferences"""
    pref_key = f"agent_prefs:{admin_id}"
    redis_client.setex(pref_key, 86400, json.dumps(preferences))


def get_agent_accessible_rooms(admin_id: str) -> List[str]:
    """Get list of rooms accessible to an agent"""
    try:
        admin_collection = get_admin_collection()
        agent_doc = admin_collection.find_one({'admin_id': admin_id})
        
        if not agent_doc:
            return []
        
        agent_widgets = agent_doc.get('assigned_widgets', [])
        if not agent_widgets:
            return []
        
        room_collection = get_room_collection()
        rooms = list(room_collection.find({
            'is_active': True,
            'widget_id': {'$in': agent_widgets}
        }, {'room_id': 1}))
        
        return [room['room_id'] for room in rooms]
    except Exception as e:
        logger.error(f"Error getting agent accessible rooms for {admin_id}: {e}")
        return []


def get_widget_statistics(widget_id: str) -> Dict[str, Any]:
    """Get statistics for a specific widget"""
    try:
        room_collection = get_room_collection()
        contact_collection = get_contact_collection()
        chat_collection = get_chat_collection()
        
        # Get active rooms
        active_rooms = list(room_collection.find({
            'widget_id': widget_id,
            'is_active': True
        }, {'room_id': 1}))
        
        room_ids = [room['room_id'] for room in active_rooms]
        
        # Get unread counts
        pipe = redis_client.pipeline()
        for room_id in room_ids:
            pipe.get(f'unread:{room_id}')
        unread_counts = pipe.execute()
        total_unread = sum(int(count or 0) for count in unread_counts)
        
        # Get total contacts
        total_contacts = contact_collection.count_documents({'widget_id': widget_id})
        
        # Get recent messages (last 24 hours)
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        recent_messages = chat_collection.count_documents({
            'room_id': {'$in': room_ids},
            'timestamp': {'$gte': yesterday}
        })
        
        return {
            'widget_id': widget_id,
            'active_rooms': len(active_rooms),
            'total_unread': total_unread,
            'total_contacts': total_contacts,
            'recent_messages_24h': recent_messages,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting widget statistics for {widget_id}: {e}")
        return {
            'widget_id': widget_id,
            'active_rooms': 0,
            'total_unread': 0,
            'total_contacts': 0,
            'recent_messages_24h': 0,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }