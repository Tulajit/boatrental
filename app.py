import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import uuid
import stripe
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

DB = "bookings.db"
HOURLY_RATE = 349
DEPOSIT_RATE = 0.10
OPEN_HOUR = 8
CLOSE_HOUR = 22

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            date TEXT,
            start_time TEXT,
            duration INTEGER,
            passengers INTEGER,
            stripe_checkout_id TEXT
        )
        """)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/book', methods=['POST'])
def book():
    name = request.form['name']
    email = request.form['email']
    date = request.form['date']
    start_time = request.form['start_time']
    duration = int(request.form['duration'])
    passengers = int(request.form['passengers'])

    start = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    end = start + timedelta(hours=duration)
    if start.hour < OPEN_HOUR or end.hour > CLOSE_HOUR or duration < 2 or duration > 8 or passengers > 12:
        return "Invalid booking request", 400

    with sqlite3.connect(DB) as conn:
        rows = conn.execute("SELECT * FROM bookings WHERE date=?",
                            (date,)).fetchall()
        for row in rows:
            existing_start = datetime.strptime(f"{row[3]} {row[4]}", "%Y-%m-%d %H:%M")
            existing_end = existing_start + timedelta(hours=row[5])
            if (start < existing_end and end > existing_start):
                return "Time slot not available", 400

        booking_id = str(uuid.uuid4())
        session['booking'] = {
            "id": booking_id,
            "name": name,
            "email": email,
            "date": date,
            "start_time": start_time,
            "duration": duration,
            "passengers": passengers
        }

        deposit = int(HOURLY_RATE * duration * DEPOSIT_RATE * 100)
        checkout = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': f'Boat booking deposit for {duration} hrs'},
                    'unit_amount': deposit,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('success', _external=True),
            cancel_url=url_for('index', _external=True),
        )
        session['checkout_id'] = checkout.id
        return redirect(checkout.url, code=303)

@app.route('/success')
def success():
    booking = session.get('booking')
    checkout_id = session.get('checkout_id')
    if not booking or not checkout_id:
        return redirect(url_for('index'))

    with sqlite3.connect(DB) as conn:
        conn.execute("""INSERT INTO bookings
                        (id, name, email, date, start_time, duration, passengers, stripe_checkout_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                     (booking['id'], booking['name'], booking['email'], booking['date'],
                      booking['start_time'], booking['duration'], booking['passengers'], checkout_id))

    session.clear()
    return render_template('success.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form['password'] == os.environ.get("ADMIN_PASSWORD"):
            session['admin'] = True
        else:
            flash("Invalid password")
            return redirect(url_for('admin'))

    if not session.get('admin'):
        return render_template('login.html')

    with sqlite3.connect(DB) as conn:
        bookings = conn.execute("SELECT * FROM bookings").fetchall()
    return render_template('admin.html', bookings=bookings)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
