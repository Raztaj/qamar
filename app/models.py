from app import db

class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    whatsapp_number = db.Column(db.String(20), unique=True, nullable=False)
    state = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Active')

    def __repr__(self):
        return f"Subscriber('{self.name}', '{self.whatsapp_number}')"
