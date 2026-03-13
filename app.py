from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import hashlib
import datetime
import random
import json
import os
import re
from federated import federated_aggregate
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import pytz  # Added for IST timezone

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ================= MONGODB CONNECTION =================
client = MongoClient("mongodb+srv://kycuser:kyc12345@cluster0.zgrfbcg.mongodb.net/?appName=Cluster0")

db = client["kyc_database"]

kyc_collection = db["kyc_data"]
blockchain_collection = db["blockchain"]
audit_collection = db["audit_logs"]
activity_collection = db["activity_logs"]

UPLOAD_FOLDER = "static/uploads"
clients = ['Bank A', 'Bank B', 'Bank C']

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ================= IST TIMESTAMP HELPER =================
def get_ist_timestamp():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

# =====================================================
# USER INDEX FOLDER HELPER
# =====================================================
def get_next_user_folder():
    existing = [
        d for d in os.listdir(UPLOAD_FOLDER)
        if os.path.isdir(os.path.join(UPLOAD_FOLDER, d)) and d.startswith("user_")
    ]
    if not existing:
        next_index = 1
    else:
        numbers = []
        for d in existing:
            try:
                numbers.append(int(d.split("_")[1]))
            except:
                pass
        next_index = max(numbers) + 1 if numbers else 1
    user_folder_name = f"user_{next_index}"
    user_folder = os.path.join(UPLOAD_FOLDER, user_folder_name)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder_name, user_folder

# =====================================================
# BLOCKCHAIN FUNCTIONS
# =====================================================
def load_blockchain():
    chain = list(blockchain_collection.find({}, {"_id":0}))
    if len(chain) == 0:
        genesis_block = {
            "index": 1,
            "timestamp": get_ist_timestamp(),
            "kyc_hash": "GENESIS",
            "previous_hash": "0",
            "hash": "GENESIS_HASH"
        }
        chain.append(genesis_block)
        save_blockchain(chain)
    return chain

def save_blockchain(chain):
    blockchain_collection.delete_many({})
    blockchain_collection.insert_many(chain)

# =====================================================
# KYC DATA
# =====================================================
def load_kyc():
    records = list(kyc_collection.find({}, {"_id":0}))
    return records

def store_kyc(data):
    kyc_collection.insert_one(data)

# =====================================================
# CREATE BLOCK
# =====================================================
def create_block(kyc_hash):
    blockchain = load_blockchain()
    previous_block = blockchain[-1]
    previous_hash = previous_block["hash"]
    block_string = str(len(blockchain)+1) + get_ist_timestamp() + kyc_hash + previous_hash
    block_hash = hashlib.sha256(block_string.encode()).hexdigest()
    block = {
        "index": len(blockchain) + 1,
        "timestamp": get_ist_timestamp(),
        "kyc_hash": kyc_hash,
        "previous_hash": previous_hash,
        "hash": block_hash
    }
    blockchain.append(block)
    save_blockchain(blockchain)

# =====================================================
# LOGGING FUNCTIONS
# =====================================================
def log_action(bank, action, kyc_hash):
    log = {
        "bank": bank,
        "action": action,
        "kyc_hash": kyc_hash,
        "time": get_ist_timestamp()
    }
    audit_collection.insert_one(log)

def log_activity(action):
    activity = {
        "action": action,
        "time": get_ist_timestamp()
    }
    activity_collection.insert_one(activity)

# =====================================================
# ROUTES
# =====================================================
@app.route('/')
def home():
    return render_template("dashboard.html")

@app.route("/bank_login", methods=["GET", "POST"])
def bank_login():
    error = None
    if request.method == "POST":
        bank_id = request.form["bank_id"]
        password = request.form["password"]
        next_page = request.form.get("next")
        if bank_id == "admin" and password == "1234":
            session["bank_logged_in"] = True
            if next_page == "view_kyc":
                return redirect(url_for("kyc_records_table"))
            elif next_page == "kyc":
                return redirect(url_for("kyc"))
            elif next_page == "verify":
                return redirect(url_for("verify"))
            elif next_page == "blockchain":
                return redirect(url_for("blockchain"))
            else:
                return redirect(url_for("dashboard"))
        else:
            error = "Invalid Bank ID or Password"
    else:
        next_page = request.args.get("next")
    return render_template("bank_login.html", error=error, next_page=next_page)

@app.route('/kyc_records')
def kyc_records_table():
    if not session.get('bank_logged_in'):
        return redirect(url_for('bank_login', next='view_kyc'))
    log_activity("Viewed KYC records")
    kyc_records = list(kyc_collection.find({}, {"_id":0}))
    return render_template('kyc_records.html', kyc_records=kyc_records)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))

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

        if not all([name,aadhaar,pan,phone]):
            return render_template("kyc.html", error="All fields are required!")
        if not (aadhaar.isdigit() and len(aadhaar)==12):
            return render_template("kyc.html", error="Aadhaar must be 12 digits!")
        if not (phone.isdigit() and len(phone)==10):
            return render_template("kyc.html", error="Phone must be 10 digits!")
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan):
            return render_template("kyc.html", error="Invalid PAN format!")
        if not photo or not pan_card or not address_proof:
            return render_template("kyc.html", error="All documents required!")

        user_folder_name = name.replace(" ", "_")
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
            "timestamp":get_ist_timestamp()
        }

        store_kyc(kyc_record)
        create_block(kyc_hash)

        return redirect(url_for("kyc_success", hash=kyc_hash))

    return render_template("kyc.html")

# ================= VERIFY =================
@app.route("/verify", methods=["GET","POST"])
def verify():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="verify"))
    log_activity("Opened Verify KYC Page")
    
    result=None
    verified=False
    photo_path=None

    if request.method=="POST":
        key=request.form.get("kyc_key","").strip()
        chain=load_blockchain()
        hashes = [block.get("kyc_hash") for block in chain]

        if key and key in hashes:
            result="KYC VERIFIED ✅"
            verified=True
            log_action("Bank B","KYC Verified",key)
            kyc_records=load_kyc()
            for record in kyc_records:
                if record.get("hash")==key:
                    photo_path=record.get("photo")
                    break
        else:
            result="KYC NOT FOUND ❌"

    return render_template("verify.html",result=result,verified=verified,photo_path=photo_path)

# ================= KYC SUCCESS =================
@app.route("/kyc_success")
def kyc_success():
    hash_value = request.args.get("hash")
    return render_template("kyc_success.html", hash=hash_value)

# ================= BLOCKCHAIN VIEW =================
@app.route("/blockchain")
def blockchain():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="blockchain"))
    log_activity("Viewed Blockchain Blocks")

    blockchain = load_blockchain()
    return render_template("blockchain.html", blocks=blockchain)

@app.route("/view_chain")
def view_chain():
    return jsonify(load_blockchain())

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    session.pop("bank_logged_in", None)
    kyc_data = load_kyc()
    blockchain = load_blockchain()
    logs = list(audit_collection.find({}, {"_id":0}))
    activities = list(activity_collection.find({}, {"_id":0}).sort("time",-1))
    recent_activity = activities[:5]

    return render_template(
        "dashboard.html",
        total_kyc=len(kyc_data),
        total_blocks=len(blockchain),
        total_logs=len(logs),
        recent_activity=recent_activity
    )

@app.route('/federated_dashboard')
def federated_dashboard():
    return render_template('federated_dashboard.html', clients=clients)

@app.route('/fl_round/<int:round_num>')
def fl_round(round_num):
    client_updates = {client: random.uniform(0.5, 1.0) for client in clients}
    global_model = sum(client_updates.values()) / len(clients)
    return jsonify({
        'round': round_num,
        'client_updates': client_updates,
        'global_model': global_model
    })

# ================= BLOCKCHAIN VALIDATION =================
def validate_blockchain():
    chain = load_blockchain()
    kyc_records = load_kyc()
    for i in range(1, len(chain)):
        previous_block = chain[i - 1]
        current_block = chain[i]
        if current_block.get("previous_hash") != previous_block.get("hash"):
            kyc_hash = current_block.get("kyc_hash")
            kyc_name = None
            for record in kyc_records:
                if record.get("hash") == kyc_hash:
                    kyc_name = record.get("name")
                    break
            return {
                "status": False,
                "tampered_index": current_block.get("index"),
                "kyc_hash": kyc_hash,
                "kyc_name": kyc_name
            }
    return {"status": True}

@app.route("/check_blockchain")
def check_blockchain():
    validation = validate_blockchain()
    if validation["status"]:
        message = "Blockchain Integrity Verified ✅"
        tampered = None
    else:
        tampered = validation
        message = f"Blockchain Tampering Detected ❌ at block index {tampered['tampered_index']} (KYC Name: {tampered['kyc_name']}, Hash: {tampered['kyc_hash']})"
    return render_template("blockchain_status.html", message=message, tampered=tampered)

# ================= RUN =================
# For Render, use gunicorn instead of app.run
# Locally you can still run: python app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)