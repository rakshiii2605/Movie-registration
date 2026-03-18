from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import MONGO_URI

def init_db():
    """Initialize database with indexes for better performance"""
    try:
        # Create indexes
        users.create_index("email", unique=True)
        movies.create_index("name")
        bookings.create_index([("user", 1), ("created_at", -1)])
        bookings.create_index("movie_id")
        bookings.create_index("status")

        print("Database indexes created successfully")
    except Exception as e:
        print(f"Error creating indexes: {e}")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    print("Connected to MongoDB successfully")

    db = client["movieDB"]

    # Collections
    users = db["users"]
    movies = db["movies"]
    bookings = db["bookings"]

except ConnectionFailure:
    print("Failed to connect to MongoDB. Please check your connection string.")
    client = None
    db = None
    users = None
    movies = None
    bookings = None