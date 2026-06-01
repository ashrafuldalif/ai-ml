from extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(20), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    listen_logs = db.relationship('ListenLog', backref='user', lazy=True, cascade='all, delete-orphan')

class Genre(db.Model):
    __tablename__ = 'genres'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    songs = db.relationship('Song', backref='genre', lazy=True)

class Song(db.Model):
    __tablename__ = 'songs'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    genre_id = db.Column(db.Integer, db.ForeignKey('genres.id'), nullable=True)
    filename = db.Column(db.String(300), nullable=False)
    cover_image = db.Column(db.String(300), default='default_cover.png')
    duration = db.Column(db.Float, default=0.0)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    play_count = db.Column(db.Integer, default=0)
    listen_logs = db.relationship('ListenLog', backref='song', lazy=True, cascade='all, delete-orphan')

class ListenLog(db.Model):
    __tablename__ = 'listen_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey('songs.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    hour_of_day = db.Column(db.Integer)
    day_of_week = db.Column(db.Integer)
    mood = db.Column(db.String(50), default='neutral')
    weather_humidity = db.Column(db.Float, default=50.0)
    weather_temp = db.Column(db.Float, default=25.0)
    session_duration = db.Column(db.Float, default=0.0)
    liked = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    genre_id = db.Column(db.Integer, db.ForeignKey('genres.id'), nullable=True)

class RLModelState(db.Model):
    __tablename__ = 'rl_model_states'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    q_table_path = db.Column(db.String(300))
    total_interactions = db.Column(db.Integer, default=0)
    last_trained = db.Column(db.DateTime, default=datetime.utcnow)
    epsilon = db.Column(db.Float, default=1.0)