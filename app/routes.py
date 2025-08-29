import os
import pandas as pd
from flask import render_template, request, redirect, url_for, flash
from app import app, db
from app.models import Subscriber

@app.route('/')
@app.route('/index')
def index():
    return redirect(url_for('subscribers'))

@app.route('/subscribers')
def subscribers():
    all_subscribers = Subscriber.query.all()
    return render_template('subscribers.html', subscribers=all_subscribers)

@app.route('/import', methods=['GET', 'POST'])
def import_subscribers():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file:
            try:
                # Read the file using pandas
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.filename.endswith('.xlsx'):
                    df = pd.read_excel(file)
                else:
                    flash('Invalid file type')
                    return redirect(request.url)

                # Ensure required columns are present
                required_columns = ['name', 'whatsapp_number']
                if not all(col in df.columns for col in required_columns):
                    flash(f'File must contain the following columns: {", ".join(required_columns)}')
                    return redirect(request.url)

                new_subscribers = 0
                for _, row in df.iterrows():
                    # Check for existing subscriber
                    exists = Subscriber.query.filter_by(whatsapp_number=row['whatsapp_number']).first()
                    if not exists:
                        subscriber = Subscriber(
                            name=row['name'],
                            whatsapp_number=str(row['whatsapp_number']),
                            state=row.get('state') # Use .get() for optional columns
                        )
                        db.session.add(subscriber)
                        new_subscribers += 1

                db.session.commit()
                flash(f'Successfully imported {new_subscribers} new subscribers.')
                return redirect(url_for('subscribers'))

            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred: {e}')
                return redirect(request.url)

    return render_template('import.html')
