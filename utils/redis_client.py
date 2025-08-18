import redis

redis_client = redis.StrictRedis(
    host='localhost',
    port=6379,
    db=0,
    # username='default',
    # password='Geeks@1302',
    decode_responses=True
)
