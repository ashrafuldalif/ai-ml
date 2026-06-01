from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from extensions import db
from models import Song, ListenLog, Genre, RLModelState
from rl_engine import UserRLModel, get_suggestion_songs, GLOBAL_MODEL_PATH
from datetime import datetime
import requests

user_bp = Blueprint('user', __name__)

def get_weather():
    try:
        resp = requests.get('https://wttr.in/Dhaka?format=j1', timeout=3)
        data = resp.json()
        humidity = float(data['current_condition'][0]['humidity'])
        temp = float(data['current_condition'][0]['temp_C'])
        return humidity, temp
    except:
        return 50.0, 25.0

@user_bp.route('/')
@login_required
def player():
    songs = Song.query.all()
    genres = Genre.query.all()
    return render_template('user/player.html', songs=songs, genres=genres)

@user_bp.route('/play/<int:song_id>', methods=['POST'])
@login_required
def play_song(song_id):
    song = Song.query.get_or_404(song_id)
    song.play_count += 1
    data = request.get_json() or {}
    mood = data.get('mood', 'neutral')
    humidity, temp = get_weather()
    now = datetime.utcnow()

    log = ListenLog(user_id=current_user.id, song_id=song.id,
                    hour_of_day=now.hour, day_of_week=now.weekday(),
                    mood=mood, weather_humidity=humidity,
                    weather_temp=temp, genre_id=song.genre_id)
    db.session.add(log)
    db.session.commit()

    rl = UserRLModel(current_user.id)
    action_name, state, action_idx = rl.suggest_strategy(
        mood, now.hour, humidity, temp,
        song.genre_id, 0,
        gender=current_user.gender,
        age=current_user.age)
    personal = get_suggestion_songs(
        action_name, current_user.id, song, db.session, Song, ListenLog, Genre)

    # Blend with global model — fills gaps when user has little history
    import os
    if os.path.exists(GLOBAL_MODEL_PATH):
        global_rl = UserRLModel(user_id=0)
        global_rl.model_path = GLOBAL_MODEL_PATH
        global_rl.load()
        global_action, _, _ = global_rl.suggest_strategy(
            mood, now.hour, humidity, temp,
            song.genre_id, 0,
            gender=current_user.gender,
            age=current_user.age)
        global_sugg = get_suggestion_songs(
            global_action, current_user.id, song, db.session, Song, ListenLog, Genre)
        seen = {s.id for s in personal}
        suggestions = personal + [s for s in global_sugg if s.id not in seen]
        suggestions = suggestions[:5]
    else:
        suggestions = personal

    session['last_log_id'] = log.id
    session['last_action_idx'] = action_idx

    return jsonify({
        'status': 'ok', 'log_id': log.id, 'action': action_name,
        'suggestions': [{'id': s.id, 'title': s.title, 'artist': s.artist,
                         'filename': s.filename,
                         'genre': s.genre.name if s.genre else 'Unknown'} for s in suggestions]
    })

@user_bp.route('/feedback', methods=['POST'])
@login_required
def feedback():
    data = request.get_json() or {}
    log_id = data.get('log_id')
    liked = int(data.get('liked', 0))
    completed = bool(data.get('completed', False))
    session_duration = float(data.get('session_duration', 0))

    log = ListenLog.query.get(log_id)
    if log and log.user_id == current_user.id:
        log.liked = liked
        log.completed = completed
        log.session_duration = session_duration
        db.session.commit()

        rl = UserRLModel(current_user.id)
        log_entry = {
            'mood': log.mood, 'hour_of_day': log.hour_of_day,
            'weather_humidity': log.weather_humidity,
            'weather_temp': log.weather_temp,
            'genre_id': log.genre_id,
            'liked': liked, 'completed': completed,
            'session_duration': session_duration, 'mood_match': True,
            'action_idx': session.get('last_action_idx', 0),
            'gender': current_user.gender,
            'age': current_user.age,
        }
        reward = rl.train_on_log(log_entry)

        state = RLModelState.query.filter_by(user_id=current_user.id).first()
        if not state:
            state = RLModelState(user_id=current_user.id)
            db.session.add(state)
        state.total_interactions = rl.interaction_count
        state.last_trained = datetime.utcnow()
        state.epsilon = rl.epsilon
        state.q_table_path = rl.model_path
        db.session.commit()

        return jsonify({'status': 'ok', 'reward': reward})
    return jsonify({'status': 'error'}), 400

@user_bp.route('/suggestions', methods=['POST'])
@login_required
def get_suggestions():
    data = request.get_json() or {}
    mood = data.get('mood', 'neutral')
    song_id = data.get('song_id')
    humidity, temp = get_weather()
    now = datetime.utcnow()
    current_song = Song.query.get(song_id) if song_id else None
    rl = UserRLModel(current_user.id)
    last_log = ListenLog.query.filter_by(user_id=current_user.id).order_by(ListenLog.timestamp.desc()).first()
    liked_last = last_log.liked if last_log else 0
    genre_id = current_song.genre_id if current_song else 0
    action_name, state, action_idx = rl.suggest_strategy(
        mood, now.hour, humidity, temp, genre_id, liked_last,
        gender=current_user.gender, age=current_user.age)
    suggestions = get_suggestion_songs(action_name, current_user.id, current_song, db.session, Song, ListenLog, Genre)
    return jsonify({
        'action': action_name,
        'suggestions': [{'id': s.id, 'title': s.title, 'artist': s.artist,
                         'filename': s.filename, 'cover': s.cover_image,
                         'genre': s.genre.name if s.genre else 'Unknown'} for s in suggestions]
    })

@user_bp.route('/playlist')
@login_required
def my_playlist():
    logs = ListenLog.query.filter_by(user_id=current_user.id, liked=1).all()
    songs = list({log.song_id: log.song for log in logs}.values())
    return render_template('user/playlist.html', songs=songs)


@user_bp.route('/recent')
@login_required
def recent_songs():
    # Fetch last 10 distinct songs played by this user, most recent first
    subq = (
        db.session.query(
            ListenLog.song_id,
            db.func.max(ListenLog.timestamp).label('last_played')
        )
        .filter(ListenLog.user_id == current_user.id)
        .group_by(ListenLog.song_id)
        .order_by(db.func.max(ListenLog.timestamp).desc())
        .limit(10)
        .subquery()
    )
    logs = (
        db.session.query(Song, subq.c.last_played)
        .join(subq, Song.id == subq.c.song_id)
        .order_by(subq.c.last_played.desc())
        .all()
    )
    return jsonify([
        {
            'id':       song.id,
            'title':    song.title,
            'artist':   song.artist,
            'filename': song.filename,
            'genre':    song.genre.name if song.genre else 'Unknown'
        }
        for song, _ in logs
    ])