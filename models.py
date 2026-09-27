from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    fullname = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher")
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requests = db.relationship(
        "RepairRequest",
        foreign_keys="RepairRequest.user_id",
        backref="requester",
        lazy=True
    )
    assigned_requests = db.relationship(
        "RepairRequest",
        foreign_keys="RepairRequest.assigned_to",
        backref="technician",
        lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class RepairRequest(db.Model):
    __tablename__ = "repair_requests"
    id = db.Column(db.Integer, primary_key=True)
    request_no = db.Column(db.String(30), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requester_name = db.Column(db.String(120), nullable=True)
    requester_contact = db.Column(db.String(120), nullable=True)
    building = db.Column(db.String(100), nullable=False)
    room = db.Column(db.String(50), nullable=False)
    problem_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=False)
    urgency = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(30), nullable=False, default="pending")
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    completion_date = db.Column(db.Date, nullable=True)
    cost = db.Column(db.Float, nullable=True)
    result = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    images = db.relationship(
        "RepairImage", backref="repair", lazy=True,
        cascade="all, delete-orphan"
    )
    comments = db.relationship(
        "Comment", backref="repair", lazy=True,
        cascade="all, delete-orphan", order_by="Comment.created_at"
    )

class RepairImage(db.Model):
    __tablename__ = "repair_images"
    id = db.Column(db.Integer, primary_key=True)
    repair_id = db.Column(db.Integer, db.ForeignKey("repair_requests.id"), nullable=False)
    image_type = db.Column(db.String(20), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    repair_id = db.Column(db.Integer, db.ForeignKey("repair_requests.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requester_name = db.Column(db.String(120), nullable=True)
    requester_contact = db.Column(db.String(120), nullable=True)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="comments")
