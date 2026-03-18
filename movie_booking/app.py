from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, SubmitField, validators
from wtforms.validators import DataRequired, Email, Length, EqualTo
from config import SECRET_KEY, MONGO_URI
from models.db import users, movies, bookings, init_db
from datetime import datetime
import re

app = Flask(__name__)
app.secret_key = SECRET_KEY
bcrypt = Bcrypt(app)

# Initialize database indexes
init_db()

# WTForms Classes
class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create Account')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

# Custom Jinja2 filters
@app.template_filter('format_datetime')
def format_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    return value.strftime('%B %d, %Y at %I:%M %p')

# Routes
@app.route('/')
def home():
    featured_movies = list(movies.find().limit(6))
    return render_template("index.html", featured_movies=featured_movies)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if user already exists
        existing_user = users.find_one({"email": form.email.data.lower()})
        if existing_user:
            flash('Email already registered. Please login instead.', 'danger')
            return redirect(url_for('login'))

        # Hash password
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

        # Create user
        user_data = {
            "name": form.name.data,
            "email": form.email.data.lower(),
            "password": hashed_password,
            "created_at": datetime.utcnow(),
            "is_active": True
        }

        users.insert_one(user_data)
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template("register.html", form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = users.find_one({"email": form.email.data.lower()})

        if user and bcrypt.check_password_hash(user['password'], form.password.data):
            session['user'] = user['email']
            session['user_name'] = user['name']
            flash(f'Welcome back, {user["name"]}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template("login.html", form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_email = session['user']
    user_bookings = list(bookings.find({"user": user_email}).sort("created_at", -1).limit(5))
    all_movies = list(movies.find())
    
    # Format bookings for template
    formatted_bookings = []
    for booking in user_bookings:
        formatted_booking = {
            '_id': str(booking.get('_id', '')),
            'movie_name': booking.get('movie_name', 'Unknown Movie'),
            'seats': booking.get('seats', []),
            'total_seats': len(booking.get('seats', [])),
            'total_price': booking.get('total_price', 0),
            'status': booking.get('status', 'confirmed'),
            'created_at': booking.get('created_at', datetime.utcnow())
        }
        formatted_bookings.append(formatted_booking)

    return render_template("dashboard.html", user_bookings=formatted_bookings, movies=all_movies)

@app.route('/movies')
def show_movies():
    if 'user' not in session:
        return redirect(url_for('login'))

    all_movies = list(movies.find())
    return render_template("movies.html", movies=all_movies)

@app.route('/movie/<movie_id>')
def movie_details(movie_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        movie = movies.find_one({"_id": movie_id})
        if not movie:
            flash('Movie not found.', 'danger')
            return redirect(url_for('show_movies'))

        return render_template("movie_details.html", movie=movie)
    except:
        flash('Invalid movie ID.', 'danger')
        return redirect(url_for('show_movies'))

@app.route('/seats/<movie_id>')
def seats(movie_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        movie = movies.find_one({"_id": movie_id})
        if not movie:
            flash('Movie not found.', 'danger')
            return redirect(url_for('show_movies'))

        # Get booked seats for this movie
        booked_seats = []
        existing_bookings = bookings.find({"movie_id": movie_id})
        for booking in existing_bookings:
            booked_seats.extend(booking.get('seats', []))

        return render_template("seats.html", movie=movie, booked_seats=booked_seats)
    except:
        flash('Invalid movie ID.', 'danger')
        return redirect(url_for('show_movies'))

@app.route('/booking-confirmation/<movie_id>', methods=['GET', 'POST'])
def booking_confirmation(movie_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # User confirmed the booking, now create it
        selected_seats = request.form.getlist('seats')
        
        if not movie_id or not selected_seats:
            flash('Invalid booking details.', 'danger')
            return redirect(url_for('show_movies'))

        try:
            movie = movies.find_one({"_id": movie_id})
            if not movie:
                flash('Movie not found.', 'danger')
                return redirect(url_for('show_movies'))

            # Check for seat conflicts one more time
            existing_bookings = bookings.find({"movie_id": movie_id})
            booked_seats = []
            for booking in existing_bookings:
                booked_seats.extend(booking.get('seats', []))

            conflict_seats = [seat for seat in selected_seats if seat in booked_seats]
            if conflict_seats:
                flash(f'Seats {", ".join(conflict_seats)} were just booked by another user. Please select different seats.', 'danger')
                return redirect(url_for('seats', movie_id=movie_id))

            # Create booking
            booking_data = {
                "user": session['user'],
                "user_name": session['user_name'],
                "movie_id": movie_id,
                "movie_name": movie['name'],
                "seats": sorted(selected_seats),
                "total_seats": len(selected_seats),
                "total_price": len(selected_seats) * 250,  # ₹250 per seat
                "created_at": datetime.utcnow(),
                "status": "booked"
            }

            result = bookings.insert_one(booking_data)
            flash(f'🎉 Booking confirmed! {len(selected_seats)} seats booked for {movie["name"]}.', 'success')
            return redirect(url_for('booking_success', booking_id=str(result.inserted_id)))

        except Exception as e:
            flash('An error occurred while booking. Please try again.', 'danger')
            return redirect(url_for('show_movies'))
    
    else:
        # GET request - show confirmation page
        try:
            movie = movies.find_one({"_id": movie_id})
            if not movie:
                flash('Movie not found.', 'danger')
                return redirect(url_for('show_movies'))

            # Get selected seats from query parameters
            selected_seats = request.args.get('seats', '').split(',')
            selected_seats = [seat.strip() for seat in selected_seats if seat.strip()]

            if not selected_seats:
                flash('Please select seats first.', 'danger')
                return redirect(url_for('seats', movie_id=movie_id))

            total_price = len(selected_seats) * 250

            return render_template("confirmation.html", 
                                 movie=movie, 
                                 selected_seats=selected_seats,
                                 total_seats=len(selected_seats),
                                 total_price=total_price)
        except Exception as e:
            flash('An error occurred. Please try again.', 'danger')
            return redirect(url_for('show_movies'))

@app.route('/booking-success/<booking_id>')
def booking_success(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        from bson.objectid import ObjectId
        # Try to convert to ObjectId
        try:
            booking_obj_id = ObjectId(booking_id)
        except:
            booking_obj_id = booking_id
        
        booking = bookings.find_one({"_id": booking_obj_id, "user": session['user']})
        if not booking:
            flash('Booking not found.', 'danger')
            return redirect(url_for('mybookings'))

        return render_template("booking_success.html", booking=booking)
    except Exception as e:
        flash(f'Error loading booking: {str(e)}', 'danger')
        return redirect(url_for('mybookings'))

@app.route('/book', methods=['POST'])
def book():
    if 'user' not in session:
        return redirect(url_for('login'))

    movie_id = request.form.get('movie_id')
    selected_seats = request.form.getlist('seats')

    if not movie_id or not selected_seats:
        flash('Please select a movie and seats.', 'danger')
        return redirect(url_for('show_movies'))

    try:
        movie = movies.find_one({"_id": movie_id})
        if not movie:
            flash('Movie not found.', 'danger')
            return redirect(url_for('show_movies'))

        # Check for seat conflicts
        existing_bookings = bookings.find({"movie_id": movie_id})
        booked_seats = []
        for booking in existing_bookings:
            booked_seats.extend(booking.get('seats', []))

        conflict_seats = [seat for seat in selected_seats if seat in booked_seats]
        if conflict_seats:
            flash(f'Seats {", ".join(conflict_seats)} are already booked. Please select different seats.', 'danger')
            return redirect(url_for('seats', movie_id=movie_id))

        # Create booking immediately
        booking_data = {
            "user": session['user'],
            "user_name": session['user_name'],
            "movie_id": movie_id,
            "movie_name": movie['name'],
            "seats": sorted(selected_seats),
            "total_seats": len(selected_seats),
            "total_price": len(selected_seats) * 250,  # ₹250 per seat
            "created_at": datetime.utcnow(),
            "status": "booked"
        }

        result = bookings.insert_one(booking_data)
        flash(f'🎉 Booking confirmed! {len(selected_seats)} seat(s) booked.', 'success')
        return redirect(url_for('booking_success', booking_id=str(result.inserted_id)))

    except Exception as e:
        flash('An error occurred while booking. Please try again.', 'danger')
        return redirect(url_for('show_movies'))

@app.route('/mybookings')
def mybookings():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        user_bookings = list(bookings.find({"user": session['user']}).sort("created_at", -1))
        
        # Format bookings for template
        formatted_bookings = []
        for booking in user_bookings:
            formatted_booking = {
                '_id': str(booking.get('_id', '')),
                'movie_name': booking.get('movie_name', 'Unknown Movie'),
                'seats': booking.get('seats', []),
                'total_seats': len(booking.get('seats', [])),
                'total_price': booking.get('total_price', 0),
                'status': booking.get('status', 'confirmed'),
                'created_at': booking.get('created_at', datetime.utcnow())
            }
            formatted_bookings.append(formatted_booking)
        
        return render_template("booking.html", bookings=formatted_bookings)
    except Exception as e:
        flash(f'Error loading bookings: {str(e)}', 'danger')
        return render_template("booking.html", bookings=[])

@app.route('/cancel-booking/<booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        from bson.objectid import ObjectId
        booking = bookings.find_one({"_id": ObjectId(booking_id), "user": session['user']})
        if not booking:
            flash('Booking not found.', 'danger')
            return redirect(url_for('mybookings'))

        # Only allow cancellation if booking is recent (within 2 hours)
        booking_time = booking['created_at']
        time_diff = datetime.utcnow() - booking_time
        if time_diff.total_seconds() > 7200:  # 2 hours
            flash('Bookings can only be cancelled within 2 hours of booking.', 'danger')
            return redirect(url_for('mybookings'))

        bookings.update_one({"_id": ObjectId(booking_id)}, {"$set": {"status": "cancelled"}})
        flash('Booking cancelled successfully.', 'success')
        return redirect(url_for('mybookings'))

    except:
        flash('An error occurred while cancelling the booking.', 'danger')
        return redirect(url_for('mybookings'))

@app.route('/api/check-seats/<movie_id>')
def check_seats(movie_id):
    if 'user' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        existing_bookings = bookings.find({"movie_id": movie_id, "status": "confirmed"})
        booked_seats = []
        for booking in existing_bookings:
            booked_seats.extend(booking.get('seats', []))

        return jsonify({"booked_seats": booked_seats})
    except:
        return jsonify({"error": "Failed to check seats"}), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)