from flask import Flask, render_template, request, redirect, url_for, session, jsonify
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

# ==================== ADMIN LOGIN ====================
@app.route("/bank_login", methods=["GET", "POST"])
def bank_login():
    error = None
    if request.method == "POST":
        bank_id = request.form.get("bank_id")
        password = request.form.get("password")
        next_page = request.form.get("next")
        if bank_id == "admin" and password == "1234":
            session["bank_logged_in"] = True
            # Redirect to requested page or dashboard
            if next_page == "kyc":
                return redirect(url_for("kyc"))
            elif next_page == "verify":
                return redirect(url_for("verify"))
            elif next_page == "blockchain":
                return redirect(url_for("blockchain"))
            elif next_page == "audit_logs":
                return redirect(url_for("audit_logs"))
            else:
                return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials"
    else:
        next_page = request.args.get("next")
    return render_template("bank_login.html", error=error, next_page=next_page)

# ==================== LOGOUT ====================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("bank_login"))

# ==================== DASHBOARD ====================
@app.route("/")
@app.route("/dashboard")
def dashboard():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="dashboard"))
    kyc_data = load_kyc()
    blockchain = load_blockchain()
    logs = list(audit_collection.find({}, {"_id":0}))
    activities = list(activity_collection.find({}, {"_id":0}).sort("time",-1))
    recent_activity = activities[:5]
    return render_template("dashboard.html",
                           total_kyc=len(kyc_data),
                           total_blocks=len(blockchain),
                           total_logs=len(logs),
                           recent_activity=recent_activity)

# ==================== KYC CREATE ====================
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

# ==================== KYC SUCCESS ====================
@app.route("/kyc_success")
def kyc_success():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="kyc_success"))
    hash_value = request.args.get("hash")
    return render_template("kyc_success.html", hash=hash_value)

# ==================== VERIFY KYC ====================
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

# ==================== BLOCKCHAIN ====================
@app.route("/blockchain")
def blockchain():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="blockchain"))
    log_activity("Viewed Blockchain Blocks")
    blockchain = load_blockchain()
    return render_template("blockchain.html", blocks=blockchain)

# ==================== AUDIT LOGS ====================
@app.route("/audit_logs")
def audit_logs():
    if not session.get("bank_logged_in"):
        return redirect(url_for("bank_login", next="audit_logs"))
    log_activity("Viewed Audit Logs")
    logs = list(audit_collection.find({}, {"_id":0}))
    return render_template("audit_logs.html", logs=logs)

# ==================== RUN ====================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)