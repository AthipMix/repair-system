import csv
import io
import os
import uuid
from datetime import date
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, send_file, abort
from sqlalchemy import inspect, text
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.utils import secure_filename

from config import Config
from extensions import db, login_manager
from models import User, RepairRequest, RepairImage, Comment
from utils import generate_request_no
from decorators import roles_required

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
login_manager.init_app(app)

os.makedirs(os.path.join(app.root_path, "static", "uploads", "before"), exist_ok=True)
os.makedirs(os.path.join(app.root_path, "static", "uploads", "after"), exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.context_processor
def inject_helpers():
    return {
        "role_label": {
            "admin": "ผู้ดูแลระบบ",
            "teacher": "ครู / บุคลากร",
            "technician": "เจ้าหน้าที่ซ่อม"
        },
        "status_label": {
            "pending": "รอรับเรื่อง",
            "accepted": "รับเรื่องแล้ว",
            "in_progress": "กำลังดำเนินการ",
            "completed": "ซ่อมเสร็จ"
        },
        "problem_label": {
            "electrical": "ไฟฟ้า",
            "furniture": "เฟอร์นิเจอร์",
            "computer": "คอมพิวเตอร์",
            "aircon": "เครื่องปรับอากาศ",
            "other": "อื่น ๆ"
        },
        "urgency_label": {
            "low": "ต่ำ", "medium": "ปานกลาง", "high": "สูง"
        }
    }

@app.route("/")
def index():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def auth_login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("เข้าสู่ระบบสำเร็จ", "success")
            return redirect(url_for("dashboard"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("login.html")

@app.route("/logout")
def auth_logout():
    logout_user()
    flash("ออกจากระบบแล้ว", "success")
    return redirect(url_for("auth_login"))

@app.route("/dashboard")
@login_required
def dashboard():
    query = RepairRequest.query
    if current_user.role == "teacher":
        query = query.filter_by(user_id=current_user.id)
    elif current_user.role == "technician":
        query = query.filter_by(assigned_to=current_user.id)

    total = query.count()
    pending = query.filter_by(status="pending").count()
    in_progress = query.filter_by(status="in_progress").count()
    completed = query.filter_by(status="completed").count()
    accepted = query.filter_by(status="accepted").count()
    recent = query.order_by(RepairRequest.created_at.desc()).limit(8).all()
    role_titles = {
        "admin": ("ศูนย์ควบคุมระบบ", "ภาพรวมงานแจ้งซ่อมทั้งหมดและการจัดการภายในระบบ"),
        "teacher": ("พื้นที่ของครู / บุคลากร", "ติดตามงานแจ้งซ่อมที่คุณแจ้งและสถานะล่าสุด"),
        "technician": ("พื้นที่ของเจ้าหน้าที่ซ่อม", "ดูงานที่ได้รับมอบหมายและอัปเดตความคืบหน้า")
    }
    dashboard_title, dashboard_subtitle = role_titles.get(current_user.role, ("Dashboard", "จัดการงานแจ้งซ่อม"))
    return render_template(
        "dashboard.html",
        total=total, pending=pending, accepted=accepted,
        in_progress=in_progress, completed=completed, recent=recent,
        dashboard_title=dashboard_title, dashboard_subtitle=dashboard_subtitle
    )

@app.route("/repairs")
@login_required
def repairs():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    problem_type = request.args.get("problem_type", "")

    query = RepairRequest.query
    if current_user.role == "teacher":
        query = query.filter_by(user_id=current_user.id)
    elif current_user.role == "technician":
        query = query.filter_by(assigned_to=current_user.id)

    if q:
        query = query.filter(
            db.or_(
                RepairRequest.request_no.ilike(f"%{q}%"),
                RepairRequest.building.ilike(f"%{q}%"),
                RepairRequest.room.ilike(f"%{q}%"),
                RepairRequest.description.ilike(f"%{q}%")
            )
        )
    if status:
        query = query.filter_by(status=status)
    if problem_type:
        query = query.filter_by(problem_type=problem_type)

    items = query.order_by(RepairRequest.created_at.desc()).all()
    return render_template("repairs.html", repairs=items, q=q, status=status, problem_type=problem_type)

@app.route("/repair/create", methods=["GET", "POST"])
def create_repair():
    """Public repair form. Login is not required for people who only want to report a problem."""
    if request.method == "POST":
        requester_name = request.form.get("requester_name", "").strip()
        requester_contact = request.form.get("requester_contact", "").strip()
        building = request.form.get("building", "").strip()
        room = request.form.get("room", "").strip()
        problem_type = request.form.get("problem_type", "")
        description = request.form.get("description", "").strip()
        urgency = request.form.get("urgency", "medium")

        if not all([requester_name, building, room, problem_type, description]):
            flash("กรุณากรอกข้อมูลที่จำเป็นให้ครบ", "danger")
            return render_template("repair_form.html", public_form=True)

        guest = User.query.filter_by(username="public_user").first()
        if not guest:
            guest = User(
                username="public_user",
                fullname="ผู้แจ้งทั่วไป",
                role="teacher",
                email="public@school.local"
            )
            guest.set_password(uuid.uuid4().hex)
            db.session.add(guest)
            db.session.flush()

        repair = RepairRequest(
            request_no=generate_request_no(),
            user_id=guest.id,
            requester_name=requester_name,
            requester_contact=requester_contact,
            building=building,
            room=room,
            problem_type=problem_type,
            description=description,
            urgency=urgency
        )
        db.session.add(repair)
        db.session.flush()
        save_uploads(repair)
        db.session.commit()
        return redirect(url_for("track_repair", request_no=repair.request_no))

    return render_template("repair_form.html", public_form=True)

@app.route("/track", methods=["GET", "POST"])
def track_repair():
    request_no = request.values.get("request_no", "").strip().upper()
    repair = RepairRequest.query.filter_by(request_no=request_no).first() if request_no else None
    return render_template("track.html", repair=repair, request_no=request_no)

@app.route("/repair/<int:repair_id>")
def repair_detail(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    technicians = User.query.filter_by(role="technician").order_by(User.fullname).all()
    return render_template("repair_detail.html", repair=repair, technicians=technicians)

@app.route("/repair/<int:repair_id>/comment", methods=["POST"])
@login_required
def add_comment(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    text = request.form.get("comment", "").strip()
    if text:
        db.session.add(Comment(repair_id=repair.id, user_id=current_user.id, comment=text))
        db.session.commit()
        flash("เพิ่มความคิดเห็นแล้ว", "success")
    return redirect(url_for("repair_detail", repair_id=repair.id))

@app.route("/repair/<int:repair_id>/assign", methods=["POST"])
@roles_required("admin")
def assign_repair(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    technician_id = request.form.get("technician_id", type=int)
    due_date_text = request.form.get("due_date", "")
    technician = User.query.filter_by(id=technician_id, role="technician").first()

    if not technician:
        flash("ไม่พบเจ้าหน้าที่ซ่อม", "danger")
        return redirect(url_for("repair_detail", repair_id=repair.id))

    repair.assigned_to = technician.id
    repair.status = "accepted"
    if due_date_text:
        try:
            repair.due_date = date.fromisoformat(due_date_text)
        except ValueError:
            flash("รูปแบบวันที่ไม่ถูกต้อง", "danger")
            return redirect(url_for("repair_detail", repair_id=repair.id))
    db.session.commit()
    flash("มอบหมายงานสำเร็จ", "success")
    return redirect(url_for("repair_detail", repair_id=repair.id))

@app.route("/repair/<int:repair_id>/status", methods=["POST"])
@login_required
def update_status(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    new_status = request.form.get("status", "")
    allowed = {"pending", "accepted", "in_progress", "completed"}

    if new_status not in allowed:
        flash("สถานะไม่ถูกต้อง", "danger")
        return redirect(url_for("repair_detail", repair_id=repair.id))

    if current_user.role == "teacher" and repair.user_id != current_user.id:
        abort(403)
    if current_user.role == "technician" and repair.assigned_to != current_user.id:
        abort(403)

    transitions = {
        "pending": {"accepted"},
        "accepted": {"in_progress"},
        "in_progress": {"completed"},
        "completed": set()
    }
    if new_status not in transitions.get(repair.status, set()):
        flash("ไม่สามารถเปลี่ยนสถานะจากขั้นตอนนี้ได้", "warning")
        return redirect(url_for("repair_detail", repair_id=repair.id))

    repair.status = new_status
    if new_status == "completed":
        repair.completion_date = date.today()
        repair.cost = request.form.get("cost", type=float)
        repair.result = request.form.get("result", "").strip()

    db.session.commit()
    flash("อัปเดตสถานะสำเร็จ", "success")
    return redirect(url_for("repair_detail", repair_id=repair.id))

def save_uploads(repair):
    for image_type in ("before", "after"):
        files = request.files.getlist(f"{image_type}_images")
        for file in files:
            if not file or not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in app.config["UPLOAD_EXTENSIONS"]:
                continue
            filename = f"{uuid.uuid4().hex}{ext}"
            relative = f"uploads/{image_type}/{filename}"
            full_path = os.path.join(app.root_path, "static", relative)
            file.save(full_path)
            db.session.add(RepairImage(
                repair_id=repair.id,
                image_type=image_type,
                image_path=relative
            ))

@app.route("/repair/<int:repair_id>/upload", methods=["POST"])
@login_required
def upload_images(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    if current_user.role not in ("admin", "technician") and repair.user_id != current_user.id:
        abort(403)
    save_uploads(repair)
    db.session.commit()
    flash("อัปโหลดรูปภาพสำเร็จ", "success")
    return redirect(url_for("repair_detail", repair_id=repair.id))

@app.route("/admin/users")
@roles_required("admin")
def admin_users():
    users = User.query.order_by(User.role, User.fullname).all()
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/create", methods=["POST"])
@roles_required("admin")
def create_user():
    username = request.form.get("username", "").strip()
    fullname = request.form.get("fullname", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "teacher")
    email = request.form.get("email", "").strip()

    if not username or not fullname or not password or role not in ("admin", "teacher", "technician"):
        flash("กรุณากรอกข้อมูลผู้ใช้ให้ครบ", "danger")
        return redirect(url_for("admin_users"))
    if User.query.filter_by(username=username).first():
        flash("Username นี้ถูกใช้แล้ว", "warning")
        return redirect(url_for("admin_users"))

    user = User(username=username, fullname=fullname, role=role, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash("เพิ่มผู้ใช้สำเร็จ", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("ไม่สามารถลบบัญชีตัวเองได้", "warning")
        return redirect(url_for("admin_users"))
    if user.requests or user.assigned_requests:
        flash("ไม่สามารถลบผู้ใช้ที่มีประวัติงานได้", "warning")
        return redirect(url_for("admin_users"))
    db.session.delete(user)
    db.session.commit()
    flash("ลบผู้ใช้สำเร็จ", "success")
    return redirect(url_for("admin_users"))

@app.route("/export/csv")
@roles_required("admin")
def export_csv():
    repairs = RepairRequest.query.order_by(RepairRequest.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Request No", "Requester", "Building", "Room", "Problem Type",
        "Urgency", "Status", "Technician", "Due Date", "Cost", "Created At"
    ])
    for r in repairs:
        writer.writerow([
            r.request_no, r.requester.fullname, r.building, r.room,
            r.problem_type, r.urgency, r.status,
            r.technician.fullname if r.technician else "",
            r.due_date or "", r.cost or "", r.created_at.strftime("%Y-%m-%d %H:%M")
        ])
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv; charset=utf-8", as_attachment=True,
                     download_name="repair_requests.csv")

@app.route("/repair/<int:repair_id>/print")
def print_repair(repair_id):
    repair = db.get_or_404(RepairRequest, repair_id)
    return render_template("repair_print.html", repair=repair)

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="คุณไม่มีสิทธิ์เข้าถึงหน้านี้"), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="ไม่พบหน้าที่ต้องการ"), 404

def seed_data():
    db.create_all()

    # Keep an existing SQLite database usable after adding public requester fields.
    inspector = inspect(db.engine)
    columns = {c["name"] for c in inspector.get_columns("repair_requests")}
    if "requester_name" not in columns:
        db.session.execute(text("ALTER TABLE repair_requests ADD COLUMN requester_name VARCHAR(120)"))
    if "requester_contact" not in columns:
        db.session.execute(text("ALTER TABLE repair_requests ADD COLUMN requester_contact VARCHAR(120)"))
    db.session.commit()

    accounts = [
        ("admin", "admin123", "ผู้ดูแลระบบ", "admin", "admin@school.local"),
        ("teacher", "teacher123", "ครูสมชาย", "teacher", "teacher@school.local"),
        ("tech", "tech123", "ช่างสมศักดิ์", "technician", "tech@school.local"),
    ]
    for username, password, fullname, role, email in accounts:
        if not User.query.filter_by(username=username).first():
            u = User(username=username, fullname=fullname, role=role, email=email)
            u.set_password(password)
            db.session.add(u)
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        seed_data()
    app.run(debug=True)
