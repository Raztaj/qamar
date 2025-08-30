from app import app, db
from app.models import User
import click
from flask.cli import with_appcontext

# Create tables before running the app
with app.app_context():
    db.create_all()

@click.command('create-user')
@with_appcontext
@click.argument('username')
@click.argument('password')
def create_user_command(username, password):
    """Creates a new user."""
    user = User.query.filter_by(username=username).first()
    if user:
        print(f'User {username} already exists.')
        return
    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    print(f'User {username} created successfully.')

app.cli.add_command(create_user_command)


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5002)
