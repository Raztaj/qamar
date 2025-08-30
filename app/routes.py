import os
import pandas as pd
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_user, logout_user, login_required
import time
import random
from app import app, db
from app.models import Subscriber, Campaign, CampaignLog, StopWord, User, Tag
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

def _process_and_set_tags(subscriber, tags_string):
    """Helper function to process a comma-separated string of tags and associate them with a subscriber."""
    subscriber.tags.clear()
    tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
    for tag_name in tag_names:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        subscriber.tags.append(tag)

@app.route('/subscriber/edit/<int:subscriber_id>', methods=['GET', 'POST'])
@login_required
def edit_subscriber(subscriber_id):
    subscriber = Subscriber.query.get_or_404(subscriber_id)
    if request.method == 'POST':
        subscriber.name = request.form['name']
        subscriber.whatsapp_number = request.form['whatsapp_number']
        subscriber.state = request.form['state']
        subscriber.status = request.form['status']

        tags_string = request.form.get('tags', '')
        _process_and_set_tags(subscriber, tags_string)

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

@app.route('/subscriber/delete_all', methods=['POST'])
@login_required
def delete_all_subscribers():
    try:
        num_rows_deleted = db.session.query(Subscriber).delete()
        db.session.commit()
        flash(f'{num_rows_deleted} subscribers have been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'error')
    return redirect(url_for('subscribers'))

@app.route('/campaigns')
@login_required
def campaigns():
    all_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    all_tags = Tag.query.order_by(Tag.name).all()
    return render_template('campaigns.html', campaigns=all_campaigns, tags=all_tags)

@app.route('/campaign/audience_count', methods=['POST'])
@login_required
def audience_count():
    tag_ids = request.json.get('tag_ids', [])
    if not tag_ids:
        return jsonify({'count': 0})

    # Query for subscribers that have ALL of the selected tags.
    subscribers_query = Subscriber.query
    for tag_id in tag_ids:
        subscribers_query = subscribers_query.filter(Subscriber.tags.any(id=tag_id))

    # We only want active subscribers for the count
    count = subscribers_query.filter_by(status='Active').count()

    return jsonify({'count': count})

@app.route('/campaign/new_custom', methods=['POST'])
@login_required
def new_custom_campaign():
    subscriber_ids = request.form.getlist('subscriber_ids')
    if not subscriber_ids:
        flash('Please select at least one subscriber.', 'error')
        return redirect(url_for('subscribers'))

    subscribers = Subscriber.query.filter(Subscriber.id.in_(subscriber_ids)).all()
    return render_template('custom_campaign.html', subscribers=subscribers)

@app.route('/campaign/launch_by_tags', methods=['POST'])
@login_required
def launch_by_tags():
    name = request.form.get('name')
    message = request.form.get('message')
    tag_ids = request.form.getlist('tag_ids')

    if not all([name, message, tag_ids]):
        flash('Campaign name, message, and at least one tag are required.', 'error')
        return redirect(url_for('campaigns'))

    # Find active subscribers that have ALL of the selected tags.
    subscribers_to_send_query = Subscriber.query.filter_by(status='Active')
    for tag_id in tag_ids:
        subscribers_to_send_query = subscribers_to_send_query.filter(Subscriber.tags.any(id=tag_id))

    subscribers_to_send = subscribers_to_send_query.all()

    if not subscribers_to_send:
        flash('No active subscribers match the selected tags.', 'error')
        return redirect(url_for('campaigns'))

    # Create and save the new campaign
    new_campaign = Campaign(name=name, message=message, status='Sending')
    db.session.add(new_campaign)
    db.session.commit()
    flash(f'Campaign "{new_campaign.name}" is now sending to {len(subscribers_to_send)} subscribers... Please do not close this window.', 'success')

    # --- Re-usable Sending Logic ---
    stop_words_db = StopWord.query.all()
    stop_words_list = {sw.word.lower() for sw in stop_words_db}

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
                    personalized_message = new_campaign.message.replace('{الاسم}', sub.name)
                    status = sender.send_message(sub.whatsapp_number, personalized_message)

                    if "Success" in status:
                        log_status = 'Success'
                        total_sent += 1
                    else:
                        log_status = f'Fail: {status}'
                        total_failed += 1

                # --- Create Log ---
                log = CampaignLog(campaign_id=new_campaign.id, subscriber_id=sub.id, status=log_status)
                db.session.add(log)
                db.session.commit()

                # Add a random delay
                time.sleep(random.randint(5, 15))

    except Exception as e:
        new_campaign.status = 'Failed'
        db.session.commit()
        flash(f"A critical error occurred during sending: {e}", "error")
        return redirect(url_for('campaigns'))

    new_campaign.status = 'Sent'
    db.session.commit()
    flash(f'Campaign "{new_campaign.name}" finished. Sent: {total_sent}, Failed: {total_failed}, Skipped: {total_skipped}.', 'success')
    return redirect(url_for('campaigns'))


@app.route('/campaign/launch_custom', methods=['POST'])
@login_required
def launch_custom_campaign():
    name = request.form['name']
    message = request.form['message']
    subscriber_ids_str = request.form['subscriber_ids']

    if not all([name, message, subscriber_ids_str]):
        flash('Campaign name, message, and subscribers are required.', 'error')
        # This redirect is not ideal, but it's a fallback.
        return redirect(url_for('subscribers'))

    subscriber_ids = [int(id) for id in subscriber_ids_str.split(',')]
    subscribers_to_send = Subscriber.query.filter(Subscriber.id.in_(subscriber_ids)).all()

    if not subscribers_to_send:
        flash('No valid subscribers to send to.', 'error')
        return redirect(url_for('subscribers'))

    # Create and save the new campaign
    new_campaign = Campaign(name=name, message=message, status='Sending')
    db.session.add(new_campaign)
    db.session.commit()
    flash(f'Campaign "{new_campaign.name}" is now sending... Please do not close this window.', 'success')

    # Fetch stop words once
    stop_words_db = StopWord.query.all()
    stop_words_list = {sw.word.lower() for sw in stop_words_db}

    total_sent = 0
    total_failed = 0
    total_skipped = 0

    try:
        with WhatsAppSender(headless=False) as sender:
            for sub in subscribers_to_send:
                log_status = ""
                # --- Stop Word Check ---
                if sub.status != 'Active':
                    log_status = "Skipped (Inactive)"
                    total_skipped += 1
                else:
                    last_message = sender.read_last_message(sub.whatsapp_number)
                    if last_message and last_message.lower() in stop_words_list:
                        print(f"Skipping {sub.name} because a stop word was found.")
                        log_status = "Skipped (Stop Word)"
                        total_skipped += 1
                    else:
                        # --- Send Message ---
                        personalized_message = new_campaign.message.replace('{الاسم}', sub.name)
                        status = sender.send_message(sub.whatsapp_number, personalized_message)

                        if "Success" in status:
                            log_status = 'Success'
                            total_sent += 1
                        else:
                            log_status = f'Fail: {status}'
                            total_failed += 1

                # --- Create Log ---
                log = CampaignLog(campaign_id=new_campaign.id, subscriber_id=sub.id, status=log_status)
                db.session.add(log)
                db.session.commit()

                # Add a random delay
                time.sleep(random.randint(5, 15))

    except Exception as e:
        new_campaign.status = 'Failed'
        db.session.commit()
        flash(f"A critical error occurred during sending: {e}", "error")
        return redirect(url_for('campaigns'))

    new_campaign.status = 'Sent'
    db.session.commit()
    flash(f'Campaign "{new_campaign.name}" finished. Sent: {total_sent}, Failed: {total_failed}, Skipped: {total_skipped}.', 'success')
    return redirect(url_for('campaigns'))

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

                        # --- Tag Handling for Import ---
                        if 'tags' in df.columns:
                            tags_string = str(row['tags']) if pd.notna(row['tags']) else ''
                            # We need to add the subscriber to the session to get an ID before processing tags
                            db.session.flush()
                            _process_and_set_tags(subscriber, tags_string)

                        new_subscribers += 1

                db.session.commit()
                flash(f'Successfully imported {new_subscribers} new subscribers.')
                return redirect(url_for('subscribers'))

            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred: {e}')
                return redirect(request.url)

    return render_template('import.html')

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
