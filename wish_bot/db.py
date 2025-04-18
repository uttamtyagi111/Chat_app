from dotenv import load_dotenv
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timezone
import redis

load_dotenv()

# Singleton MongoClient
_mongo_client = None
_redis_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        uri = os.getenv('MONGO_URI')
        if not uri:
            raise ValueError("MONGO_URI not set in environment variables")
        _mongo_client = MongoClient(uri, server_api=ServerApi('1'))
        try:
            _mongo_client.admin.command('ping')
            print("Connected to MongoDB Atlas!")
        except Exception as e:
            print(f"Connection error: {e}")
            _mongo_client = None
            raise
    return _mongo_client

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL')
        try:
            if redis_url:
                # Use REDIS_URL (internal for Render, external for local)
                _redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to localhost for local development
                _redis_client = redis.StrictRedis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True
                )
            # Test the connection
            _redis_client.ping()
            print("Connected to Redis!")
        except redis.ConnectionError as e:
            print(f"Redis connection error: {e}")
            if "No such host" in str(e):
                print("Error: Redis hostname not found. Ensure REDIS_URL is correct and accessible (e.g., internal URL for Render, external URL for local).")
            elif "SSL" in str(e):
                print("Error: SSL/TLS issue. Ensure REDIS_URL uses 'rediss://' for external connections and your environment supports SSL.")
            _redis_client = None
            raise
        except redis.AuthenticationError as e:
            print(f"Redis authentication error: {e}")
            print("Error: Check username and password in REDIS_URL (e.g., rediss://username:password@host:port).")
            _redis_client = None
            raise
    return _redis_client
def find_duplicates(collection, field):
    duplicates = collection.aggregate([
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}}
    ])
    return list(duplicates)
def remove_duplicates(collection, field):
    duplicates = find_duplicates(collection, field)
    for doc in duplicates:
        ids_to_delete = doc["ids"][1:]
        collection.delete_many({"_id": {"$in": ids_to_delete}})
    print(f"Removed {len(duplicates)} duplicate {field} entries.")

def get_chat_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['messages']
    
    existing_indexes = collection.index_information()
    
    if 'message_id_1' in existing_indexes:
        if not existing_indexes['message_id_1'].get('unique', False):
            collection.drop_index('message_id_1')
            remove_duplicates(collection, 'message_id')
            collection.create_index([('message_id', 1)], unique=True, name='message_id_1')
    else:
        remove_duplicates(collection, 'message_id')
        collection.create_index([('message_id', 1)], unique=True, name='message_id_1')

    if 'room_id_1_timestamp_-1' not in existing_indexes:
        collection.create_index([('room_id', 1), ('timestamp', -1)], name='room_id_1_timestamp_-1')
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

def get_room_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['rooms']
    
    existing_indexes = collection.index_information()
    
    if 'room_id_1' in existing_indexes:
        if not existing_indexes['room_id_1'].get('unique', False):
            print("Dropping non-unique room_id_1 index...")
            collection.drop_index('room_id_1')
            remove_duplicates(collection, 'room_id')
            collection.create_index([('room_id', 1)], unique=True, name='room_id_1')
    else:
        remove_duplicates(collection, 'room_id')
        collection.create_index([('room_id', 1)], unique=True, name='room_id_1')

    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

def insert_with_timestamps(collection, document):
    """Insert a document with created_at and updated_at timestamps in UTC"""
    current_time = datetime.now(timezone.utc)
    document['created_at'] = current_time
    document['updated_at'] = current_time
    return collection.insert_one(document)

def update_with_timestamp(collection, query, update_data):
    """Update a document and update the updated_at timestamp in UTC"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now(timezone.utc)
    return collection.update_one(query, update_data)

def update_many_with_timestamp(collection, query, update_data):
    """Update multiple documents and update the updated_at timestamp in UTC"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now(timezone.utc)
    return collection.update_many(query, update_data)