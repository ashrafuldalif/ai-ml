from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Song, Genre, User, ListenLog, RLModelState
from rl_engine import UserRLModel
from werkzeug.utils import secure_filename
from sqlalchemy import func
import os

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(is_admin=False).count()
    total_songs = Song.query.count()
    total_plays = db.session.query(func.sum(Song.play_count)).scalar() or 0
    total_logs = ListenLog.query.count()
    genre_stats = db.session.query(Genre.name, func.count(ListenLog.id))\
        .join(ListenLog, Genre.id == ListenLog.genre_id).group_by(Genre.name).all()
    recent_logs = ListenLog.query.order_by(ListenLog.timestamp.desc()).limit(20).all()
    return render_template('admin/dashboard.html', total_users=total_users,
        total_songs=total_songs, total_plays=total_plays, total_logs=total_logs,
        genre_stats=genre_stats, recent_logs=recent_logs)

@admin_bp.route('/songs')
@login_required
@admin_required
def songs():
    return render_template('admin/songs.html', songs=Song.query.all(), genres=Genre.query.all())

@admin_bp.route('/songs/add', methods=['POST'])
@login_required
@admin_required
def add_song():
    title = request.form.get('title')
    artist = request.form.get('artist')
    genre_id = request.form.get('genre_id')
    file = request.files.get('audio_file')
    if not file or not file.filename:
        flash('Audio file required', 'danger')
        return redirect(url_for('admin.songs'))
    folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    filename = secure_filename(file.filename)
    file.save(os.path.join(folder, filename))

    cover_filename = 'default_cover.png'
    cover_file = request.files.get('cover_image')
    if cover_file and cover_file.filename:
        cover_folder = os.path.join('static', 'covers')
        os.makedirs(cover_folder, exist_ok=True)
        cover_filename = secure_filename(cover_file.filename)
        cover_file.save(os.path.join(cover_folder, cover_filename))

    song = Song(title=title, artist=artist, genre_id=genre_id or None,
                filename=filename, cover_image=cover_filename)
    db.session.add(song)
    db.session.commit()
    flash('Song added!', 'success')
    return redirect(url_for('admin.songs'))

@admin_bp.route('/songs/delete/<int:song_id>', methods=['POST'])
@login_required
@admin_required
def delete_song(song_id):
    song = Song.query.get_or_404(song_id)
    try:
        db.session.delete(song)
        db.session.commit()
        flash('Song deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Could not delete song: {e}', 'danger')
    return redirect(url_for('admin.songs'))

@admin_bp.route('/genres')
@login_required
@admin_required
def genres():
    return render_template('admin/genres.html', genres=Genre.query.all())

@admin_bp.route('/genres/add', methods=['POST'])
@login_required
@admin_required
def add_genre():
    name = request.form.get('name')
    if name:
        db.session.add(Genre(name=name))
        db.session.commit()
        flash('Genre added!', 'success')
    return redirect(url_for('admin.genres'))

@admin_bp.route('/genres/delete/<int:genre_id>', methods=['POST'])
@login_required
@admin_required
def delete_genre(genre_id):
    g = Genre.query.get_or_404(genre_id)
    db.session.delete(g)
    db.session.commit()
    flash('Genre deleted', 'success')
    return redirect(url_for('admin.genres'))

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    return render_template('admin/users.html', users=User.query.filter_by(is_admin=False).all())

@admin_bp.route('/users/<int:user_id>/rl')
@login_required
@admin_required
def user_rl(user_id):
    user = User.query.get_or_404(user_id)
    rl = UserRLModel(user_id)
    stats = rl.get_stats()
    rl_state = RLModelState.query.filter_by(user_id=user_id).first()
    logs = ListenLog.query.filter_by(user_id=user_id).order_by(ListenLog.timestamp.desc()).limit(50).all()
    mood_counts = db.session.query(ListenLog.mood, func.count(ListenLog.id))\
        .filter_by(user_id=user_id).group_by(ListenLog.mood).all()
    genre_counts = db.session.query(Genre.name, func.count(ListenLog.id))\
        .join(ListenLog, Genre.id == ListenLog.genre_id)\
        .filter(ListenLog.user_id == user_id).group_by(Genre.name).all()
    hour_counts = db.session.query(ListenLog.hour_of_day, func.count(ListenLog.id))\
        .filter_by(user_id=user_id).group_by(ListenLog.hour_of_day).all()
    return render_template('admin/user_rl.html', user=user, stats=stats,
        rl_state=rl_state, logs=logs, mood_counts=mood_counts,
        genre_counts=genre_counts, hour_counts=hour_counts)

@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    genre_stats = db.session.query(Genre.name, func.count(ListenLog.id))\
        .join(ListenLog, Genre.id == ListenLog.genre_id).group_by(Genre.name).all()
    mood_stats = db.session.query(ListenLog.mood, func.count(ListenLog.id))\
        .group_by(ListenLog.mood).all()
    return jsonify({
        'genres': [{'name': g[0], 'count': g[1]} for g in genre_stats],
        'moods': [{'mood': m[0], 'count': m[1]} for m in mood_stats]
    })