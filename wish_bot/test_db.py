from datetime import datetime, timezone
from db import get_redis_client, get_mongo_client, get_chat_collection, get_room_collection
from pymongo.errors import OperationFailure
import redis
import uuid


def cleanup_test_data():
    print("Cleaning up test data...")
    chat_collection = get_chat_collection()
    room_collection = get_room_collection()
    chat_collection.delete_many({'message_id': {'$regex': '^test_msg_'}})
    room_collection.delete_many({'room_id': {'$regex': '^test_room_'}})
    print("Test data cleaned up.")


def test_redis_connection():
    print("Testing Redis connection...")
    try:
        redis_client = get_redis_client()
        # Test set and get
        redis_client.set('test_key', 'test_value')
        value = redis_client.get('test_key')
        assert value == 'test_value', f"Expected 'test_value', got '{value}'"
        print("Redis test passed: Set and get operations successful.")
    except redis.ConnectionError as e:
        print(f"Redis connection failed: {e}")
        raise
    except redis.AuthenticationError as e:
        print(f"Redis authentication failed: {e}")
        raise
    except AssertionError as e:
        print(f"Redis test failed: {e}")
        raise


def test_mongodb_connection():
    print("Testing MongoDB connection...")
    try:
        mongo_client = get_mongo_client()
        # Test ping
        mongo_client.admin.command('ping')
        print("MongoDB test passed: Ping successful.")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        raise


def test_chat_collection():
    print("Testing chat collection...")
    try:
        collection = get_chat_collection()
        # Test index creation
        indexes = collection.index_information()
        assert 'message_id_1' in indexes, "message_id_1 index not found"
        assert indexes['message_id_1'].get('unique'), "message_id_1 is not unique"
        print("Chat collection test passed: Indexes verified.")
        
        # Test insert with unique ID
        test_msg_id = f"test_msg_{uuid.uuid4()}"
        result = collection.insert_one({
            'message_id': test_msg_id,
            'room_id': 'test_room',
            'content': 'Test message',
            'timestamp': datetime.now(timezone.utc)
        })
        print(f"Inserted document: {result.inserted_id}")
        
        # Test query
        doc = collection.find_one({'message_id': test_msg_id})
        assert doc is not None, "Inserted document not found"
        assert doc['content'] == 'Test message', "Content mismatch in retrieved document"
        print("Chat collection test passed: Insert and query successful.")
    except OperationFailure as e:
        print(f"Chat collection test failed: {e}")
        raise
    except AssertionError as e:
        print(f"Chat collection test failed: {e}")
        raise


def test_room_collection():
    print("Testing room collection...")
    try:
        collection = get_room_collection()
        # Test index creation
        indexes = collection.index_information()
        assert 'room_id_1' in indexes, "room_id_1 index not found"
        assert indexes['room_id_1'].get('unique'), "room_id_1 is not unique"
        print("Room collection test passed: Indexes verified.")
        
        # Test insert with unique ID
        test_room_id = f"test_room_{uuid.uuid4()}"
        result = collection.insert_one({
            'room_id': test_room_id,
            'name': 'Test Room'
        })
        print(f"Inserted document: {result.inserted_id}")
        
        # Test query
        doc = collection.find_one({'room_id': test_room_id})
        assert doc is not None, "Inserted document not found"
        assert doc['name'] == 'Test Room', "Name mismatch in retrieved document"
        print("Room collection test passed: Insert and query successful.")
    except OperationFailure as e:
        print(f"Room collection test failed: {e}")
        raise
    except AssertionError as e:
        print(f"Room collection test failed: {e}")
        raise


def run_tests():
    print("Running all tests...")
    try:
        cleanup_test_data()
        test_redis_connection()
        test_mongodb_connection()
        test_chat_collection()
        test_room_collection()
        print("All tests passed successfully!")
    except Exception as e:
        print(f"Test suite failed: {e}")
        raise


if __name__ == "__main__":
    run_tests()