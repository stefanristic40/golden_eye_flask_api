from flask import Flask, request, jsonify, send_from_directory
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import face_recognition
from dotenv import load_dotenv
import numpy as np
import os
import json
import uuid
from bson import ObjectId
import re

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


def extract_face_encodings(img_path):
    image = face_recognition.load_image_file(img_path)
    encodings = face_recognition.face_encodings(image)
    if encodings:
        return encodings[0]  # Assuming one face per image
    return None


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
        original_filename = secure_filename(thumbnail.filename)
        file_extension = os.path.splitext(original_filename)[1]
        random_filename = f"{uuid.uuid4()}{file_extension}"
        filepath = os.path.join(UPLOAD_FOLDER, random_filename)
        thumbnail.save(filepath)

        data["thumbnail"] = random_filename

        # Extract and store face encoding
        face_encoding = extract_face_encodings(filepath)
        if face_encoding is not None:
            data["face_encoding"] = face_encoding.tolist()

    # Insert the entry into the database
    entries_collection.insert_one(data)

    return jsonify({"message": "Entry created successfully"}), 200


@app.route("/api/search", methods=["POST"])
def search():
    matches = []

    if "image" in request.files:
        query_image = request.files["image"]
        filename = secure_filename(query_image.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        query_image.save(filepath)

        # Extract face encoding from the query image
        query_encoding = extract_face_encodings(filepath)
        if query_encoding is None:
            return jsonify({"error": "No face found in the image"}), 400

        # Find similar faces in the database
        matches = list(entries_collection.find())
        similarities = []

        for entry in matches:
            if "face_encoding" in entry:
                entry_encoding = np.array(entry["face_encoding"])
                distance = np.linalg.norm(query_encoding - entry_encoding)
                similarities.append((distance, entry))

        # Sort by distance (lower is better)
        similarities.sort(key=lambda x: x[0])

        # Return top 5 similar faces
        matches = [entry for _, entry in similarities[:3]]

    if "date_start" in request.form and "date_end" in request.form:

        date_start = request.form.get("date_start")
        date_end = request.form.get("date_end")
        incident_type = request.form.get("incident_type")

        matches = list(
            entries_collection.find(
                {
                    "date": {"$gte": date_start, "$lte": date_end},
                    "incident_types": incident_type,
                }
            )
        )

    if "case_id" in request.form:
        case_id = request.form.get("case_id")
        # Search like %case_id%
        matches = list(entries_collection.find({"case_id": {"$regex": case_id}}))

    if "search_text" in request.form:
        search_text = request.form.get("search_text")
        # Search like %search_text%
        matches = list(
            entries_collection.find(
                {
                    "$or": [
                        {"organization": {"$regex": search_text, "$options": "i"}},
                        {"sub_organization": {"$regex": search_text, "$options": "i"}},
                        {"name": {"$regex": search_text, "$options": "i"}},
                        {"brief_description": {"$regex": search_text, "$options": "i"}},
                        {"area": {"$regex": search_text, "$options": "i"}},
                        {"cas": {"$regex": search_text, "$options": "i"}},
                        {"martyped": {"$regex": search_text, "$options": "i"}},
                        {"injured": {"$regex": search_text, "$options": "i"}},
                        {"killed": {"$regex": search_text, "$options": "i"}},
                        {"case_id": {"$regex": search_text, "$options": "i"}},
                    ]
                }
            )
        )

    if "incident_type" in request.form:
        incident_type = request.form.get("incident_type")
        matches = list(entries_collection.find({"incident_types": incident_type}))

    for entry in matches:
        entry.pop("face_encoding", None)

    # Convert ObjectId to string in entries
    for entry in matches:
        for key, value in entry.items():
            if isinstance(value, ObjectId):
                entry[key] = str(value)

    return jsonify(matches), 200


@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    app.run(debug=True)
