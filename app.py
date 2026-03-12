from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import hashlib
import datetime
import random
import json
import os
import re
from federated import federated_aggregate
from werkzeug.utils import secure_filename
from pyngrok import ngrok
from pyngrok import ngrok, conf

app = Flask(__name__)
app.secret_key = "supersecretkey"

BLOCKCHAIN_FILE = "blockchain.json"
KYC_FILE = "kyc_data.json"
AUDIT_FILE = "audit_log.json"
UPLOAD_FOLDER = "static/uploads"
clients = ['Bank A', 'Bank B', 'Bank C']
ACTIVITY_FILE = "activity_log.json"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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
    if os.path.exists(BLOCKCHAIN_FILE):
        with open(BLOCKCHAIN_FILE, "r", encoding="utf-8") as f:
            chain = json.load(f)
    else:
        chain = []
    if len(chain) == 0:
        genesis_block = {
            "index": 1,
            "timestamp": str(datetime.datetime.now()),
            "kyc_hash": "GENESIS",
            "previous_hash": "0",
            "hash": "GENESIS_HASH"
        }
        chain.append(genesis_block)
        save_blockchain(chain)
    return chain


def save_blockchain(chain):
    with open(BLOCKCHAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(chain, f, indent=4)


# =====================================================
# KYC DATA
# =====================================================
def load_kyc():
    if os.path.exists(KYC_FILE):
        with open(KYC_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def store_kyc(data):
    existing = load_kyc()
    existing.append(data)
    with open(KYC_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4)


# =====================================================
# CREATE BLOCK
# =====================================================
def create_block(kyc_hash):
    blockchain = load_blockchain()
    previous_block = blockchain[-1]
    previous_hash = previous_block["hash"]
    block_string = str(len(blockchain)+1) + str(datetime.datetime.now()) + kyc_hash + previous_hash
    block_hash = hashlib.sha256(block_string.encode()).hexdigest()
    block = {
        "index": len(blockchain) + 1,
        "timestamp": str(datetime.datetime.now()),
        "kyc_hash": kyc_hash,
        "previous_hash": previous_hash,
        "hash": block_hash
    }
    blockchain.append(block)
    save_blockchain(blockchain)


# ================= HOME =================
@app.route("/")
def home():
    return render_template("index.html")


# ================= BANK LOGIN =================
# ================= BANK LOGIN =================
@app.route("/bank_login", methods=["GET", "POST"])
def bank_login():
    error = None
    if request.method == "POST":
        bank_id = request.form["bank_id"]
        password = request.form["password"]
        next_page = request.form.get("next")
        if bank_id == "admin" and password == "1234":
            session["bank_logged_in"] = True
            # Redirect based on next_page
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

# ================= KYC RECORDS TABLE =================
@app.route('/kyc_records')
def kyc_records_table():
    if not session.get('bank_logged_in'):
        return redirect(url_for('bank_login', next='view_kyc'))
    log_activity("Viewed KYC records")

    try:
        with open('kyc_data.json', 'r') as f:
            kyc_records = json.load(f)
    except:
        kyc_records = []

    return render_template('kyc_records.html', kyc_records=kyc_records)

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))


# ================= KYC SUBMISSION =================
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

        # create folder using KYC name
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
            "timestamp":str(datetime.datetime.now())
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


# ================= AUDIT LOG =================
def log_action(bank,action,kyc_hash):
    if os.path.exists(AUDIT_FILE):
        with open(AUDIT_FILE,"r") as f:
            logs=json.load(f)
    else:
        logs=[]
    log={
        "bank":bank,
        "action":action,
        "kyc_hash":kyc_hash,
        "time":str(datetime.datetime.now())
    }
    logs.append(log)
    with open(AUDIT_FILE,"w") as f:
        json.dump(logs,f,indent=4)




# ================= ACTIVITY LOG =================
def log_activity(action):
    if os.path.exists(ACTIVITY_FILE):
        try:
            with open(ACTIVITY_FILE, "r") as f:
                activities = json.load(f)
        except:
            activities = []
    else:
        activities = []

    activity = {
        "action": action,
        "time": str(datetime.datetime.now())
    }

    activities.append(activity)

    with open(ACTIVITY_FILE, "w") as f:
        json.dump(activities, f, indent=4)


# ================= FEDERATED =================
@app.route("/federated")
def federated():
    global_score,bank_scores=federated_aggregate()
    return render_template("federated.html", global_score=round(global_score,3), bank_scores=bank_scores)


# ================= VIEW AUDIT LOGS =================
@app.route("/audit_logs")
def audit_logs():
    log_activity("Viewed Audit Logs")
    if os.path.exists(AUDIT_FILE):
        with open(AUDIT_FILE, "r") as f:
            logs = json.load(f)
    else:
        logs = []
    return render_template("audit_logs.html", logs=logs)



# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    # clear bank session when returning to dashboard
    session.pop("bank_logged_in", None)

    kyc_data = load_kyc()
    blockchain = load_blockchain()

    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE) as f:
                logs = json.load(f)
        except:
            logs = []
    else:
        logs = []

    # LOAD ACTIVITY LOG
    if os.path.exists(ACTIVITY_FILE):
        try:
            with open(ACTIVITY_FILE) as f:
               activities = json.load(f)
        except:
            activities = []
    else:
        activities = []

    recent_activity = activities[-5:]

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
            # Find the KYC record by hash
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

    # Blockchain is valid
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)