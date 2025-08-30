import os
import pandas as pd
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_user, logout_user, login_required
import time
import random
from app import app, db
from app.models import Subscriber, Campaign, CampaignLog, StopWord, User
from app.forms import LoginForm
from sender import WhatsAppSender

from sqlalchemy import func

@app.route('/')
@app.route('/index')
@login_required
def dashboard():
    total_subscribers = Subscriber.query.count()
    total_campaigns = Campaign.query.count()

    successful_logs = CampaignLog.query.filter(CampaignLog.status == 'Success').count()
    total_logs = CampaignLog.query.count()
    success_rate = (successful_logs / total_logs * 100) if total_logs > 0 else 0

    return render_template('dashboard.html',
                           total_subscribers=total_subscribers,
                           total_campaigns=total_campaigns,
                           successful_logs=successful_logs,
                           success_rate=f'{success_rate:.2f}')

@app.route('/subscribers')
@login_required
def subscribers():
    all_subscribers = Subscriber.query.all()
    return render_template('subscribers.html', subscribers=all_subscribers)

@app.route('/subscriber/edit/<int:subscriber_id>', methods=['GET', 'POST'])
@login_required
def edit_subscriber(subscriber_id):
    subscriber = Subscriber.query.get_or_404(subscriber_id)
    if request.method == 'POST':
        subscriber.name = request.form['name']
        subscriber.whatsapp_number = request.form['whatsapp_number']
        subscriber.state = request.form['state']
        subscriber.status = request.form['status']
        db.session.commit()
        flash('Subscriber updated successfully!', 'success')
        return redirect(url_for('subscribers'))
    return render_template('edit_subscriber.html', subscriber=subscriber)

@app.route('/subscriber/delete/<int:subscriber_id>', methods=['POST'])
@login_required
def delete_subscriber(subscriber_id):
    subscriber_to_delete = Subscriber.query.get_or_404(subscriber_id)
    db.session.delete(subscriber_to_delete)
    db.session.commit()
    flash('Subscriber deleted successfully!', 'success')
    return redirect(url_for('subscribers'))

@app.route('/campaigns', methods=['GET', 'POST'])
@login_required
def campaigns():
    if request.method == 'POST':
        name = request.form['name']
        message = request.form['message']
        if name and message:
            new_campaign = Campaign(name=name, message=message)
            db.session.add(new_campaign)
            db.session.commit()
            flash('Campaign created successfully!', 'success')
            return redirect(url_for('campaigns'))
        else:
            flash('Name and message are required.', 'error')

    all_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns.html', campaigns=all_campaigns)

@app.route('/campaign/edit/<int:campaign_id>', methods=['GET', 'POST'])
@login_required
def edit_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    if campaign.status != 'Draft':
        flash('Only draft campaigns can be edited.', 'error')
        return redirect(url_for('campaigns'))

    if request.method == 'POST':
        campaign.name = request.form['name']
        campaign.message = request.form['message']
        db.session.commit()
        flash('Campaign updated successfully!', 'success')
        return redirect(url_for('campaigns'))

    return render_template('edit_campaign.html', campaign=campaign)

@app.route('/campaign/delete/<int:campaign_id>', methods=['POST'])
@login_required
def delete_campaign(campaign_id):
    campaign_to_delete = Campaign.query.get_or_404(campaign_id)
    db.session.delete(campaign_to_delete)
    db.session.commit()
    flash('Campaign and all its logs have been deleted successfully!', 'success')
    return redirect(url_for('campaigns'))

@app.route('/campaign/<int:campaign_id>/details')
@login_required
def campaign_details(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    return render_template('campaign_details.html', campaign=campaign)

@app.route('/import', methods=['GET', 'POST'])
@login_required
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

@app.route('/campaign/<int:campaign_id>/launch', methods=['POST'])
@login_required
def launch_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    if campaign.status != 'Draft':
        flash('This campaign has already been sent or is currently sending.', 'error')
        return redirect(url_for('campaigns'))

    subscribers_to_send = Subscriber.query.filter_by(status='Active').all()
    if not subscribers_to_send:
        flash('No active subscribers to send to.', 'error')
        return redirect(url_for('campaigns'))

    # Fetch stop words once
    stop_words_db = StopWord.query.all()
    stop_words_list = {sw.word.lower() for sw in stop_words_db}

    campaign.status = 'Sending'
    db.session.commit()
    flash(f'Campaign "{campaign.name}" is now sending... Please do not close this window.', 'success')

    total_sent = 0
    total_failed = 0
    total_skipped = 0

    try:
        with WhatsAppSender(headless=False) as sender:
            for sub in subscribers_to_send:
                log_status = ""
                # --- Stop Word Check ---
                last_message = sender.read_last_message(sub.whatsapp_number)
                if last_message and last_message.lower() in stop_words_list:
                    print(f"Skipping {sub.name} because a stop word was found.")
                    log_status = "Skipped (Stop Word)"
                    total_skipped += 1
                else:
                    # --- Send Message ---
                    personalized_message = campaign.message.replace('{الاسم}', sub.name)
                    status = sender.send_message(sub.whatsapp_number, personalized_message)

                    if "Success" in status:
                        log_status = 'Success'
                        total_sent += 1
                    else:
                        log_status = f'Fail: {status}'
                        total_failed += 1

                # --- Create Log ---
                log = CampaignLog(campaign_id=campaign.id, subscriber_id=sub.id, status=log_status)
                db.session.add(log)
                db.session.commit()

                # Add a random delay
                time.sleep(random.randint(5, 15))

    except Exception as e:
        campaign.status = 'Failed'
        db.session.commit()
        flash(f"A critical error occurred during sending: {e}", "error")
        return redirect(url_for('campaigns'))

    campaign.status = 'Sent'
    db.session.commit()
    flash(f'Campaign "{campaign.name}" finished. Sent: {total_sent}, Failed: {total_failed}, Skipped: {total_skipped}.', 'success')
    return redirect(url_for('campaigns'))

@app.route('/stopwords', methods=['GET', 'POST'])
@login_required
def stopwords():
    if request.method == 'POST':
        word = request.form.get('word', '').strip()
        if word:
            # Check if word already exists
            exists = StopWord.query.filter_by(word=word).first()
            if not exists:
                new_word = StopWord(word=word)
                db.session.add(new_word)
                db.session.commit()
                flash(f'Stop word "{word}" added.', 'success')
            else:
                flash(f'Stop word "{word}" already exists.', 'error')
        else:
            flash('Stop word cannot be empty.', 'error')
        return redirect(url_for('stopwords'))

    all_stop_words = StopWord.query.all()
    return render_template('stopwords.html', stop_words=all_stop_words)

@app.route('/stopwords/delete/<int:word_id>', methods=['POST'])
@login_required
def delete_stop_word(word_id):
    word_to_delete = StopWord.query.get_or_404(word_id)
    db.session.delete(word_to_delete)
    db.session.commit()
    flash(f'Stop word "{word_to_delete.word}" deleted.', 'success')
    return redirect(url_for('stopwords'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        return redirect(url_for('dashboard'))
    return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('dashboard'))
