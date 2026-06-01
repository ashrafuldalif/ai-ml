import numpy as np
import pickle
import os
from datetime import datetime

MOODS        = ['happy', 'sad', 'energetic', 'calm', 'romantic', 'angry', 'neutral', 'focused']
TIME_SLOTS   = ['morning', 'afternoon', 'evening', 'night']
HUMIDITY_BINS = ['low', 'medium', 'high']           # <40 / 40-70 / >70
TEMP_BINS    = ['cold', 'mild', 'warm', 'hot']      # <10 / 10-20 / 20-30 / >30
GENDER_BINS  = ['male', 'female', 'other']
AGE_BINS     = ['teen', 'young', 'adult', 'senior'] # <18 / 18-30 / 30-50 / >50
ACTIONS      = ['play_same_genre', 'play_liked_genre', 'play_new_genre',
                'play_mood_match', 'play_time_match']

GLOBAL_MODEL_PATH = os.path.join('rl_models', 'global_rl.pkl')

# ── encoding helpers ──────────────────────────────────────────────────────────

def get_time_slot(hour):
    if 5 <= hour < 12:  return 'morning'
    elif 12 <= hour < 17: return 'afternoon'
    elif 17 <= hour < 21: return 'evening'
    else:               return 'night'

def get_humidity_bin(h):
    if h < 40:  return 'low'
    elif h < 70: return 'medium'
    else:       return 'high'

def get_temp_bin(t):
    if t < 10:  return 'cold'
    elif t < 20: return 'mild'
    elif t < 30: return 'warm'
    else:       return 'hot'

def get_gender_idx(gender):
    if gender is None:
        return 2  # 'other'
    g = gender.lower().strip()
    if g == 'male':   return 0
    if g == 'female': return 1
    return 2

def get_age_bin(age):
    if age is None or age <= 0: return 1  # default 'young'
    if age < 18:  return 0  # teen
    elif age < 30: return 1  # young
    elif age < 50: return 2  # adult
    else:         return 3  # senior


def encode_state(mood, hour, humidity, temp, last_genre_id, liked_last,
                 gender=None, age=None):
    """
    State tuple:
      (mood_idx, time_idx, humidity_idx, temp_idx, genre_idx,
       like_idx, gender_idx, age_idx)

    Total state space:
      8 × 4 × 3 × 4 × 20 × 3 × 3 × 4 = 138,240 possible states
    """
    mood_idx   = MOODS.index(mood) if mood in MOODS else 6   # default 'neutral'
    time_idx   = TIME_SLOTS.index(get_time_slot(hour))
    hum_idx    = HUMIDITY_BINS.index(get_humidity_bin(humidity))
    temp_idx   = TEMP_BINS.index(get_temp_bin(temp))
    genre_idx  = (last_genre_id or 0) % 20
    like_idx   = 1 if liked_last > 0 else (2 if liked_last < 0 else 0)
    gender_idx = get_gender_idx(gender)
    age_idx    = get_age_bin(age)
    return (mood_idx, time_idx, hum_idx, temp_idx, genre_idx,
            like_idx, gender_idx, age_idx)


# ── model ─────────────────────────────────────────────────────────────────────

class UserRLModel:
    def __init__(self, user_id, model_dir='rl_models'):
        self.user_id         = user_id
        self.model_dir       = model_dir
        self.model_path      = os.path.join(model_dir, f'user_{user_id}_rl.pkl')
        self.q_table         = {}
        self.epsilon         = 1.0
        self.epsilon_min     = 0.1
        self.epsilon_decay   = 0.995
        self.alpha           = 0.1
        self.gamma           = 0.9
        self.n_actions       = len(ACTIONS)
        self.interaction_count = 0
        self.load()

    # ── Q-table ops ───────────────────────────────────────────────────────────

    def get_q_values(self, state):
        if state not in self.q_table:
            self.q_table[state] = np.zeros(self.n_actions)
        return self.q_table[state]

    def choose_action(self, state):
        if np.random.random() < self.epsilon:
            return np.random.randint(self.n_actions)
        return int(np.argmax(self.get_q_values(state)))

    def get_action_name(self, state):
        idx = self.choose_action(state)
        return ACTIONS[idx], idx

    def update(self, state, action, reward, next_state):
        q  = self.get_q_values(state)
        nq = np.max(self.get_q_values(next_state))
        q[action] = q[action] + self.alpha * (reward + self.gamma * nq - q[action])
        self.q_table[state] = q
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        self.interaction_count += 1
        self.save()

    # ── reward ────────────────────────────────────────────────────────────────

    def compute_reward(self, liked, completed, session_duration, is_mood_match):
        r = 0.0
        if liked == 1:   r += 2.0
        elif liked == -1: r -= 1.5
        if completed:    r += 1.0
        r += min(session_duration / 60.0, 1.0)
        if is_mood_match: r += 0.5
        return r

    # ── public API ────────────────────────────────────────────────────────────

    def suggest_strategy(self, mood, hour, humidity, temp,
                         last_genre_id, liked_last,
                         gender=None, age=None):
        state = encode_state(mood, hour, humidity, temp,
                             last_genre_id, liked_last, gender, age)
        action_name, action_idx = self.get_action_name(state)
        return action_name, state, action_idx

    def train_on_log(self, log_entry, next_log_entry=None):
        mood        = log_entry.get('mood', 'neutral')
        hour        = log_entry.get('hour_of_day', 12)
        humidity    = log_entry.get('weather_humidity', 50.0)
        temp        = log_entry.get('weather_temp', 25.0)
        genre_id    = log_entry.get('genre_id', 0)
        liked       = log_entry.get('liked', 0)
        completed   = log_entry.get('completed', False)
        session_dur = log_entry.get('session_duration', 0.0)
        is_mood_match = log_entry.get('mood_match', False)
        action_idx  = log_entry.get('action_idx', 0)
        gender      = log_entry.get('gender', None)
        age         = log_entry.get('age', None)

        state  = encode_state(mood, hour, humidity, temp,
                              genre_id, liked, gender, age)
        reward = self.compute_reward(liked, completed, session_dur, is_mood_match)

        if next_log_entry:
            next_state = encode_state(
                next_log_entry.get('mood', 'neutral'),
                next_log_entry.get('hour_of_day', 12),
                next_log_entry.get('weather_humidity', 50.0),
                next_log_entry.get('weather_temp', 25.0),
                next_log_entry.get('genre_id', 0),
                next_log_entry.get('liked', 0),
                next_log_entry.get('gender', None),
                next_log_entry.get('age', None),
            )
        else:
            next_state = state

        self.update(state, action_idx, reward, next_state)
        return reward

    def get_stats(self):
        avg_q = float(np.mean([np.mean(v) for v in self.q_table.values()])) \
                if self.q_table else 0
        best_actions = {}
        for qvals in self.q_table.values():
            a = ACTIONS[int(np.argmax(qvals))]
            best_actions[a] = best_actions.get(a, 0) + 1
        return {
            'total_states':              len(self.q_table),
            'avg_q_value':               round(avg_q, 4),
            'epsilon':                   round(self.epsilon, 4),
            'interactions':              self.interaction_count,
            'best_actions_distribution': best_actions,
        }

    # ── persistence ───────────────────────────────────────────────────────────

    def save(self):
        os.makedirs(self.model_dir, exist_ok=True)
        with open(self.model_path, 'wb') as f:
            pickle.dump({
                'q_table':           self.q_table,
                'epsilon':           self.epsilon,
                'interaction_count': self.interaction_count,
            }, f)

    def load(self):
        if os.path.exists(self.model_path):
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
            # Validate state shape — old models had 5-tuples, new ones have 8-tuples.
            # If shape mismatch, discard and start fresh (or from global).
            sample_keys = list(data.get('q_table', {}).keys())
            if sample_keys and len(sample_keys[0]) != 8:
                print(f"[RL] Model {self.model_path} has old state shape "
                      f"({len(sample_keys[0])}D) — rebuilding.")
                os.remove(self.model_path)
                self._bootstrap_from_global()
                return
            self.q_table           = data.get('q_table', {})
            self.epsilon           = data.get('epsilon', 1.0)
            self.interaction_count = data.get('interaction_count', 0)
        else:
            self._bootstrap_from_global()

    def _bootstrap_from_global(self):
        if os.path.exists(GLOBAL_MODEL_PATH):
            with open(GLOBAL_MODEL_PATH, 'rb') as f:
                data = pickle.load(f)
            self.q_table           = {k: v.copy() for k, v in data.get('q_table', {}).items()}
            self.epsilon           = 0.5   # half exploit global, half explore personally
            self.interaction_count = 0


# ── suggestion retrieval ──────────────────────────────────────────────────────

def get_suggestion_songs(action_name, user_id, current_song,
                         db_session, Song, ListenLog, Genre):
    from sqlalchemy import func
    suggestions = []

    if action_name == 'play_liked_genre':
        liked_genres = (
            db_session.query(ListenLog.genre_id,
                             func.sum(ListenLog.liked).label('tl'))
            .filter(ListenLog.user_id == user_id, ListenLog.liked == 1)
            .group_by(ListenLog.genre_id)
            .order_by(func.sum(ListenLog.liked).desc())
            .limit(3).all()
        )
        gids = [g.genre_id for g in liked_genres]
        if gids:
            suggestions = (Song.query
                           .filter(Song.genre_id.in_(gids))
                           .order_by(func.random()).limit(5).all())

    elif action_name == 'play_same_genre' and current_song:
        suggestions = (Song.query
                       .filter(Song.genre_id == current_song.genre_id,
                               Song.id != current_song.id)
                       .order_by(func.random()).limit(5).all())

    elif action_name == 'play_mood_match':
        recent = (db_session.query(ListenLog.genre_id)
                  .filter(ListenLog.user_id == user_id)
                  .order_by(ListenLog.timestamp.desc()).limit(10).all())
        gids = list({g.genre_id for g in recent if g.genre_id})
        if gids:
            suggestions = (Song.query
                           .filter(Song.genre_id.in_(gids))
                           .order_by(func.random()).limit(5).all())

    elif action_name == 'play_time_match':
        hour = datetime.now().hour
        freq = (
            db_session.query(ListenLog.song_id,
                             func.count(ListenLog.id).label('cnt'))
            .filter(ListenLog.user_id == user_id,
                    ListenLog.hour_of_day.between(max(0, hour - 2),
                                                  min(23, hour + 2)))
            .group_by(ListenLog.song_id)
            .order_by(func.count(ListenLog.id).desc()).limit(5).all()
        )
        sids = [s.song_id for s in freq]
        if sids:
            suggestions = Song.query.filter(Song.id.in_(sids)).all()

    elif action_name == 'play_new_genre' and current_song:
        suggestions = (Song.query
                       .filter(Song.genre_id != current_song.genre_id)
                       .order_by(func.random()).limit(5).all())

    if not suggestions:
        suggestions = Song.query.order_by(func.random()).limit(5).all()

    return suggestions
