from dotenv import load_dotenv
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timezone

load_dotenv()

# Singleton MongoClient
_mongo_client = None

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

def get_chat_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['messages']
    
    # Conditional index creation
    existing_indexes = collection.index_information()
    if 'room_id_1_timestamp_-1' not in existing_indexes:
        collection.create_index([('room_id', 1), ('timestamp', -1)])
    if 'message_id_1' not in existing_indexes:
        collection.create_index([('message_id', 1)])
    # Keep these only if created_at/updated_at are queried directly
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)])
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)])
    
    return collection

def get_room_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['rooms']
    
    existing_indexes = collection.index_information()
    if 'room_id_1' not in existing_indexes:
        collection.create_index([('room_id', 1)])
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)])
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)])
    
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