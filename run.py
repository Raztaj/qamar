from app import app, db

# Create tables before running the app
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5002)
