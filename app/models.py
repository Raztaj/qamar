from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Association table for the many-to-many relationship between Subscriber and Tag
subscriber_tags = db.Table('subscriber_tags',
    db.Column('subscriber_id', db.Integer, db.ForeignKey('subscriber.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    whatsapp_number = db.Column(db.String(20), unique=True, nullable=False)
    state = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Active') # e.g., Active, Unsubscribed
    logs = db.relationship('CampaignLog', backref='subscriber', lazy=True)
    tags = db.relationship('Tag', secondary=subscriber_tags, lazy='subquery',
                           backref=db.backref('subscribers', lazy=True))

    def __repr__(self):
        return f"Subscriber('{self.name}', '{self.whatsapp_number}')"

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft') # e.g., Draft, Sending, Sent
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    logs = db.relationship('CampaignLog', backref='campaign', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Campaign('{self.name}', '{self.status}')"

class CampaignLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscriber.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False) # e.g., Success, Fail
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"CampaignLog('Campaign {self.campaign_id}', 'Subscriber {self.subscriber_id}', '{self.status}')"

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f"Tag('{self.name}')"

class StopWord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"StopWord('{self.word}')"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
