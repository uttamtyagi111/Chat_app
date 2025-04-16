import json
import subprocess
from datetime import datetime
from utils.redis_client import redis_client
from wish_bot.db import get_chat_collection, get_room_collection

def export_redis():
    messages = []
    keys = redis_client.keys('message:*')
    for key in keys:
        data = redis_client.hgetall(key)
        messages.append(data)

    with open('redis_messages.json', 'w') as f:
        json.dump(messages, f, indent=2)
    print("Exported Redis messages to redis_messages.json")

def migrate_redis_to_mongo():
    collection = get_chat_collection()
    try:
        with open('redis_messages.json') as f:
            messages = json.load(f)
            for msg in messages:
                doc = {
                    'message_id': msg.get('message_id', msg.get('id', '')),
                    'room_id': msg.get('room_id', 'default_room'),
                    'sender': msg.get('sender', 'anonymous'),
                    'message': msg.get('message', ''),
                    'file_url': msg.get('file_url', ''),
                    'file_name': msg.get('file_name', ''),
                    'delivered': msg.get('delivered', 'true') == 'true',
                    'seen': msg.get('seen', 'false') == 'true',
                    'timestamp': datetime.fromisoformat(msg.get('timestamp', datetime.now().isoformat())) if msg.get('timestamp') else datetime.now(),
                    'seen_at': datetime.fromisoformat(msg['seen_at']) if msg.get('seen_at') else None
                }
                collection.insert_one(doc)
        print("Migrated Redis data to MongoDB!")
    except FileNotFoundError:
        print("No redis_messages.json found, skipping Redis migration")
    except ValueError as e:
        print(f"Error parsing timestamp: {e}")

def export_chatroom():
    try:
        subprocess.run(['python', 'manage.py', 'dumpdata', 'chat.ChatRoom', '--output', 'rooms.json'], check=True)
        print("Exported ChatRoom data to rooms.json")
    except subprocess.CalledProcessError:
        print("No ChatRoom data found, skipping export")

def migrate_rooms_to_mongo():
    collection = get_room_collection()
    try:
        with open('rooms.json') as f:
            data = json.load(f)
            for item in data:
                if item['model'] == 'chat.chatroom':
                    fields = item['fields']
                    collection.update_one(
                        {'room_id': fields['room_id']},
                        {'$set': {'is_active': fields['is_active']}},
                        upsert=True
                    )
        print("Migrated ChatRoom data to MongoDB!")
    except FileNotFoundError:
        print("No rooms.json found, skipping room migration")

def main():
    print("Starting migration process...")
    export_redis()
    migrate_redis_to_mongo()
    export_chatroom()
    migrate_rooms_to_mongo()
    print("All migrations completed successfully!")

if __name__ == '__main__':
    main()