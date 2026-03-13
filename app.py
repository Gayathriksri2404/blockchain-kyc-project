from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import hashlib
import datetime
import random
import os
import re
from federated import federated_aggregate
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import pytz

# ===================== MongoDB Connection =====================
mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("DB_NAME")

if not mongo_uri or not db_name:
    raise ValueError("MONGO_URI or DB_NAME environment variable is missing!")

client = MongoClient(mongo_uri)
db = client[db_name]

# Collections (instead of JSON files)
kyc_collection = db["kyc_data"]
blockchain_collection = db["blockchain"]
activity_collection = db["activity_log"]
audit_collection = db["audit_log"]
# ===============================================================

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ------------------ Helper Functions ------------------
def now_ist():
    tz = pytz.timezone("Asia/Kolkata")
    return datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def load_blockchain():
    chain = list(blockchain_collection.find({}, {"_id": 0}))
    if len(chain) == 0:
        genesis_block = {
            "index": 1,
            "timestamp": now_ist(),
            "kyc_hash": "GENESIS",
            "previous_hash": "0",
            "hash": "GENESIS_HASH"
        }
        try:
            blockchain_collection.insert_one(genesis_block)
            chain.append(genesis_block)
        except Exception as e:
            print("Error saving genesis block:", e)
    return chain

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    # Step 3: Limit fetched records to reduce memory usage
    kyc_list = list(kyc_collection.find({}, {"_id":0}).sort("timestamp",-1).limit(10))
    blockchain_list = list(blockchain_collection.find({}, {"_id":0}).sort("index",-1).limit(10))
    activity_list = list(activity_collection.find({}, {"_id":0}).sort("time",-1).limit(5))
    
    return render_template("dashboard.html", kyc=kyc_list, blockchain=blockchain_list, activity=activity_list)

@app.route("/create_kyc", methods=["GET", "POST"])
def create_kyc():
    if request.method == "POST":
        # Your existing KYC creation logic here
        name = request.form.get("name")
        customer_id = request.form.get("customer_id")
        # ... other fields ...
        
        kyc_record = {
            "name": name,
            "customer_id": customer_id,
            "timestamp": now_ist()
        }
        kyc_collection.insert_one(kyc_record)
        
        # Optional: Log activity
        activity_collection.insert_one({"action": "create_kyc", "time": now_ist(), "user": name})
        
        return redirect(url_for("dashboard"))
    return render_template("create_kyc.html")

@app.route("/verify_kyc")
def verify_kyc():
    # Example: fetch last 10 KYC records for verification
    kyc_list = list(kyc_collection.find({}, {"_id":0}).sort("timestamp",-1).limit(10))
    return render_template("verify_kyc.html", kyc=kyc_list)

# Add your other routes similarly, keeping your current logic
# Use kyc_collection, blockchain_collection, activity_collection, audit_collection instead of JSON files

# ------------------ Run ------------------
if __name__ == "__main__":
    app.run(debug=True)
    