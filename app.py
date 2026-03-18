from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_from_directory
import hashlib
import random
import re
import os
import time
from werkzeug.utils import secure_filename
from federated import federated_aggregate_weights
from datetime import datetime
import pytz
from pymongo import MongoClient


app = Flask(__name__)
app.secret_key = "supersecretkey"
ist = pytz.timezone('Asia/Kolkata')

# ================== Upload Folder ==================
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

clients = ['Bank A', 'Bank B', 'Bank C']

# ================== MongoDB Atlas Setup ==================
client = MongoClient(
    "mongodb+srv://kycuser:kyc1234@flaskkyccluster.dgb83uj.mongodb.net/kycdb?retryWrites=true&w=majority"
)

db = client['kycdb']

kyc_collection = db['kycdata']
blockchain_collection = db['blockchain']
audit_collection = db['audit_logs']
activity_collection = db['activity_logs']

# ================== File Route ==================
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ================== Blockchain Functions ==================
def load_blockchain():
    chain = list(blockchain_collection.find({}, {"_id":0}))
    if len(chain) == 0:
        genesis_block = {
            "index": 1,
            "timestamp": datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S"),
            "kyc_name": "GENESIS",
            "kyc_hash": "GENESIS",
            "previous_hash": "0",
            "hash": "GENESIS_HASH"
        }
        blockchain_collection.insert_one(genesis_block)
        chain.append(genesis_block)
    return chain

def create_block(kyc_hash, name):

    blockchain = load_blockchain()

    previous_block = blockchain[-1]
    previous_hash = previous_block["hash"]

    index = len(blockchain) + 1
    timestamp = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

    block_string = (
        str(index) +
        timestamp +
        name +
        kyc_hash +
        previous_hash
    )

    block_hash = hashlib.sha256(block_string.encode()).hexdigest()

    block = {
        "index": index,
        "timestamp": timestamp,
        "kyc_name": name,
        "kyc_hash": kyc_hash,
        "previous_hash": previous_hash,
        "hash": block_hash
    }

    blockchain_collection.insert_one(block)

# ================== KYC Functions ==================
def get_all_kyc():
    return list(kyc_collection.find({}, {"_id":0}))

def store_kyc(data):
    kyc_collection.insert_one(data)

# ================== Logs ==================
def log_action(bank, action, kyc_hash):
    audit_collection.insert_one({
        "bank": bank,
        "action": action,
        "kyc_hash": kyc_hash,
        "time": datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    })

def log_activity(action):
    activity_collection.insert_one({
        "action": action,
        "time": datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    })

# ================== Routes ==================
@app.route('/')
def home():
    return render_template("dashboard.html")

@app.route("/bank_login", methods=["GET", "POST"])
def bank_login():
    error = None
    next_page = request.args.get("next")

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

    return render_template("bank_login.html", error=error, next_page=next_page)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))

@app.route('/kyc_records')
def kyc_records_table():

    if not session.get('bank_logged_in'):
        return redirect(url_for('bank_login', next='view_kyc'))

    log_activity("Viewed KYC records")

    kyc_records = get_all_kyc()

    return render_template('kyc_records.html', kyc_records=kyc_records)

# ================== Create KYC ==================
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

        unique_id = str(int(time.time()))

        safe_name = name.replace(" ", "_")

        user_folder = f"{safe_name}_{unique_id}"
        user_path = os.path.join(app.config["UPLOAD_FOLDER"], user_folder)

        os.makedirs(user_path, exist_ok=True)

        photo_filename = "photo_" + secure_filename(photo.filename)
        pan_filename = "pan_" + secure_filename(pan_card.filename)
        address_filename = "address_" + secure_filename(address_proof.filename)

        photo.save(os.path.join(user_path, photo_filename))
        pan_card.save(os.path.join(user_path, pan_filename))
        address_proof.save(os.path.join(user_path, address_filename))

        data_string = name + aadhaar + pan + phone
        kyc_hash = hashlib.sha256(data_string.encode()).hexdigest()

        log_action("Bank A","KYC Created",kyc_hash)
        log_activity("New KYC Record Created")

        kyc_record = {
            "name": name,
            "aadhaar": aadhaar,
            "pan": pan,
            "phone": phone,
            "photo_path": f"{user_folder}/{photo_filename}",
            "pan_path": f"{user_folder}/{pan_filename}",
            "address_path": f"{user_folder}/{address_filename}",
            "hash": kyc_hash,
            "timestamp": datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
        }

        store_kyc(kyc_record)

        create_block(kyc_hash, name)

        return redirect(url_for("kyc_success", hash=kyc_hash))

    return render_template("kyc.html")

# ================== Verify ==================
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

            kyc_records=get_all_kyc()

            for record in kyc_records:

                if record.get("hash")==key:

                    photo_path = record.get("photo_path")
                    break

        else:

            result="KYC NOT FOUND ❌"

    return render_template("verify.html",result=result,verified=verified,photo_path=photo_path)

@app.route("/kyc_success")
def kyc_success():
    hash_value = request.args.get("hash")
    return render_template("kyc_success.html", hash=hash_value)

# ================== Blockchain ==================
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

@app.route("/audit_logs")
def audit_logs():

    log_activity("Viewed Audit Logs")

    logs = list(audit_collection.find({}, {"_id":0}))

    return render_template("audit_logs.html", logs=logs)

@app.route("/dashboard")
def dashboard():

    session.pop("bank_logged_in", None)

    kyc_data = get_all_kyc()
    blockchain = load_blockchain()
    logs = list(audit_collection.find({}, {"_id":0}))
    activities = list(activity_collection.find({}, {"_id":0}))

    recent_activity = activities[-5:]

    return render_template(
        "dashboard.html",
        total_kyc=len(kyc_data),
        total_blocks=len(blockchain),
        total_logs=len(logs),
        recent_activity=recent_activity
    )

# ================== Federated Learning ==================
# -------------------- List of clients (banks) --------------------
clients = ["BankA", "BankB", "BankC"]

@app.route('/federated_dashboard')
def federated_dashboard():
    return render_template('federated_dashboard.html', clients=clients)

@app.route('/fl_round/<int:round_num>')
def fl_round(round_num):
    global_accuracy, bank_results, local_w, global_w = federated_aggregate_weights()
    return jsonify({
        "round": round_num,
        "client_updates": bank_results,
        "global_model": global_accuracy
    })

@app.route("/federated_accuracy")
def federated_accuracy():
    global_acc, bank_results, local_w, global_w = federated_aggregate_weights()
    return jsonify({
        "global_accuracy": global_acc,
        "bank_results": bank_results,
        "local_weights": {k: v["weights"].tolist() for k,v in local_w.items()},
        "global_weights": {
            "weights": global_w["weights"].tolist(),
            "bias": float(global_w["bias"])
        }
    })

#========================blockchain status===================

def validate_blockchain():

    chain = load_blockchain()

    for i in range(1, len(chain)):

        previous_block = chain[i-1]
        current_block = chain[i]

        # Step 1: Check previous hash connection
        if current_block["previous_hash"] != previous_block["hash"]:
            return {
               "status": False,
               "tampered_index": current_block["index"],
               "reason": "Previous hash mismatch",
               "kyc_hash": current_block.get("kyc_hash", "Unknown"),
               "kyc_name": current_block.get("kyc_name", "Unknown")
            }

        # Step 2: Recalculate hash
        recalculated_string = (
            str(current_block["index"]) +
            current_block["timestamp"] +
            current_block.get("kyc_name","") +
            current_block["kyc_hash"] +
            current_block["previous_hash"]
        )

        recalculated_hash = hashlib.sha256(
            recalculated_string.encode()
        ).hexdigest()

        # Step 3: Compare hashes
        if recalculated_hash != current_block["hash"]:
            return {
                "status": False,
                "tampered_index": current_block["index"],
                "reason": "Block data modified",
                "kyc_hash": current_block.get("kyc_hash", "Unknown"),
                "kyc_name": current_block.get("kyc_name", "Unknown")
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
        message = f"Blockchain Tampering Detected ❌ at block index {tampered['tampered_index']} ({tampered['reason']})(KYC Name: {tampered['kyc_name']}, Hash: {tampered['kyc_hash']})"

    return render_template("blockchain_status.html", message=message, tampered=tampered)


# ================== Run ==================
if __name__ == "__main__":
     app.run(debug=True)