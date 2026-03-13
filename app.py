from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import hashlib, os, re, random
from federated import federated_aggregate
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from datetime import datetime
import pytz

# ==================== APP INIT ====================
app = Flask(__name__)
app.secret_key = "supersecretkey"

# ==================== IST TIME ====================
IST = pytz.timezone("Asia/Kolkata")
def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

# ==================== MONGODB ====================
client = MongoClient("mongodb+srv://kycuser:kyc12345@cluster0.zgrfbcg.mongodb.net/?appName=Cluster0")
db = client["kyc_database"]
kyc_collection = db["kyc_data"]
blockchain_collection = db["blockchain"]
audit_collection = db["audit_logs"]
activity_collection = db["activity_logs"]

# ==================== UPLOADS ====================
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
clients = ['Bank A', 'Bank B', 'Bank C']

# ==================== BLOCKCHAIN ====================
def load_blockchain():
    chain = list(blockchain_collection.find({}, {"_id":0}))
    if len(chain) == 0:
        genesis_block = {
            "index": 1,
            "timestamp": now_ist(),
            "kyc_hash": "GENESIS",
            "previous_hash": "0",
            "hash": "GENESIS_HASH"
        }
        chain.append(genesis_block)
        try:
            blockchain_collection.insert_many(chain)
        except Exception as e:
            print("Error saving genesis block:", e)
    return chain

def save_blockchain(chain):
    try:
        blockchain_collection.delete_many({})
        blockchain_collection.insert_many(chain)
    except Exception as e:
        print("Error saving blockchain:", e)

def create_block(kyc_hash):
    blockchain = load_blockchain()
    previous_block = blockchain[-1]
    previous_hash = previous_block["hash"]
    block_string = str(len(blockchain)+1) + now_ist() + kyc_hash + previous_hash
    block_hash = hashlib.sha256(block_string.encode()).hexdigest()
    block = {
        "index": len(blockchain)+1,
        "timestamp": now_ist(),
        "kyc_hash": kyc_hash,
        "previous_hash": previous_hash,
        "hash": block_hash
    }
    blockchain.append(block)
    save_blockchain(blockchain)

# ==================== KYC ====================
def load_kyc():
    try:
        return list(kyc_collection.find({}, {"_id":0}))
    except:
        return []

def store_kyc(data):
    try:
        kyc_collection.insert_one(data)
    except Exception as e:
        print("Error storing KYC:", e)

def log_action(bank, action, kyc_hash):
    try:
        audit_collection.insert_one({
            "bank": bank,
            "action": action,
            "kyc_hash": kyc_hash,
            "time": now_ist()
        })
    except Exception as e:
        print("Error logging action:", e)

def log_activity(action):
    try:
        activity_collection.insert_one({
            "action": action,
            "time": now_ist()
        })
    except Exception as e:
        print("Error logging activity:", e)

# ==================== ROUTES ====================
@app.route('/')
def home():
    return render_template("dashboard.html")

@app.route("/kyc", methods=["GET", "POST"])
def kyc():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="kyc"))
    log_activity("Opened Create KYC Page")

    if request.method == "POST":
        name = request.form.get("name","").strip()
        aadhaar = request.form.get("aadhaar","").strip()
        pan = request.form.get("pan","").strip().upper()
        phone = request.form.get("phone","").strip()
        photo = request.files.get("photo")
        pan_card = request.files.get("pan_card")
        address_proof = request.files.get("address_proof")

        if not all([name,aadhaar,pan,phone,photo,pan_card,address_proof]):
            return render_template("kyc.html", error="All fields and documents are required!")

        if not (aadhaar.isdigit() and len(aadhaar)==12):
            return render_template("kyc.html", error="Aadhaar must be 12 digits!")
        if not (phone.isdigit() and len(phone)==10):
            return render_template("kyc.html", error="Phone must be 10 digits!")
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan):
            return render_template("kyc.html", error="Invalid PAN format!")

        user_folder_name = name.replace(" ","_")
        user_folder = os.path.join(UPLOAD_FOLDER, user_folder_name)
        os.makedirs(user_folder, exist_ok=True)

        photo_filename = secure_filename(photo.filename)
        pan_filename = secure_filename(pan_card.filename)
        address_filename = secure_filename(address_proof.filename)
        photo.save(os.path.join(user_folder, photo_filename))
        pan_card.save(os.path.join(user_folder, pan_filename))
        address_proof.save(os.path.join(user_folder, address_filename))

        data_string = name + aadhaar + pan + phone
        kyc_hash = hashlib.sha256(data_string.encode()).hexdigest()

        log_action("Bank A","KYC Created",kyc_hash)
        log_activity("New KYC Record Created")

        kyc_record = {
            "name":name,
            "aadhaar":aadhaar,
            "pan":pan,
            "phone":phone,
            "photo":f"uploads/{user_folder_name}/{photo_filename}",
            "pan_card":pan_filename,
            "address_proof":address_filename,
            "hash":kyc_hash,
            "timestamp": now_ist()
        }

        store_kyc(kyc_record)
        create_block(kyc_hash)

        return redirect(url_for("kyc_success", hash=kyc_hash))

    return render_template("kyc.html")

# ==================== PORT FIX FOR RENDER ====================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)