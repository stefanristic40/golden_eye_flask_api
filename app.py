from flask import Flask, request, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
import json

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get the MongoDB URI from the environment variable
mongodb_uri = os.getenv("MONGODB_URI")

# Connect to MongoDB
client = MongoClient(mongodb_uri)
db = client["user_database"]
users_collection = db["users"]
entries_collection = db["entries"]


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    # Check if user already exists
    if users_collection.find_one({"username": username}):
        return jsonify({"error": "User already exists"}), 400

    # Hash the password
    hashed_password = generate_password_hash(password)

    # Insert the user into the database
    users_collection.insert_one({"username": username, "password": hashed_password})

    return jsonify({"message": "User created successfully"}), 201


@app.route("/api/signin", methods=["POST"])
def signin():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    # Retrieve the user from the database
    user = users_collection.find_one({"username": username})

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    return jsonify({"message": "Sign-in successful"}), 200


# Ensure the uploads folder exists
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/api/entry", methods=["POST"])
def create_entry():
    # Parse form fields
    data = {
        "date": request.form.get("date"),
        "time": request.form.get("time"),
        "organization": request.form.get("organization"),
        "sub_organization": request.form.get("sub_organization"),
        "name": request.form.get("name"),
        "comds": request.form.get("comds"),
        "brief_description": request.form.get("brief_description"),
        "area": request.form.get("area"),
        "cas": request.form.get("cas"),
        "martyped": request.form.get("martyped"),
        "injured": request.form.get("injured"),
        "killed": request.form.get("killed"),
        "latitude": request.form.get("latitute"),  # Note spelling correction
        "longitude": request.form.get("longitude"),
        "case_id": request.form.get("case_id"),
        "watch_list": request.form.get("watch_list"),
        "incident_types": request.form.getlist("incident_types"),
    }

    # Parse JSON-encoded incident_types
    incident_types_json = request.form.get("incident_types")
    if incident_types_json:
        try:
            data["incident_types"] = json.loads(incident_types_json)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format for incident_types"}), 400

    # Handle file upload
    if "thumbnail" in request.files:
        thumbnail = request.files["thumbnail"]
        filename = secure_filename(thumbnail.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        thumbnail.save(filepath)
        data["thumbnail"] = filepath

    # Insert the entry into the database
    entries_collection.insert_one(data)

    return jsonify({"message": "Entry created successfully"}), 200


if __name__ == "__main__":
    app.run(debug=True)
