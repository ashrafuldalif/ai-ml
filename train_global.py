"""
Global RL model trainer.

Reads ALL ListenLog rows (joined with User for gender/age) and trains a
single shared Q-table capturing crowd-level preferences across all
demographics, times of day, weather conditions, and genres.

Run manually:
    python train_global.py

Re-run whenever significant new listen data is added.
"""

import os
import pickle
from collections import Counter

import numpy as np

from app import create_app
from extensions import db
from models import ListenLog, User
from rl_engine import UserRLModel, ACTIONS, GLOBAL_MODEL_PATH

app = create_app()


def train_global():
    with app.app_context():
        # Join ListenLog with User to get gender and age per log entry
        rows = (
            db.session.query(ListenLog, User)
            .join(User, ListenLog.user_id == User.id)
            .order_by(ListenLog.user_id, ListenLog.timestamp)
            .all()
        )

        if not rows:
            print("No listen logs found — nothing to train on.")
            return

        print(f"Training global model on {len(rows)} listen logs "
              f"(with gender + age + temp)...")

        model = UserRLModel(user_id=0)
        model.model_path = GLOBAL_MODEL_PATH

        # Resume from existing global model if present, but validate state shape
        if os.path.exists(GLOBAL_MODEL_PATH):
            with open(GLOBAL_MODEL_PATH, 'rb') as f:
                saved = pickle.load(f)
            sample_keys = list(saved.get('q_table', {}).keys())
            if sample_keys and len(sample_keys[0]) == 8:
                model.q_table          = saved.get('q_table', {})
                model.interaction_count = saved.get('interaction_count', 0)
                print(f"  Resuming: {model.interaction_count} prior interactions, "
                      f"{len(model.q_table)} states")
            else:
                print("  Old state shape detected — retraining from scratch.")

        # Global model exploits more than it explores
        model.epsilon     = 0.1
        model.epsilon_min = 0.05

        for i, (log, user) in enumerate(rows):
            next_log  = rows[i + 1][0] if i + 1 < len(rows) else None
            next_user = rows[i + 1][1] if i + 1 < len(rows) else None
            same_user_next = (next_log is not None and
                              next_log.user_id == log.user_id)

            entry = {
                'mood':             log.mood or 'neutral',
                'hour_of_day':      log.hour_of_day or 12,
                'weather_humidity': log.weather_humidity or 50.0,
                'weather_temp':     log.weather_temp or 25.0,
                'genre_id':         log.genre_id or 0,
                'liked':            log.liked or 0,
                'completed':        log.completed or False,
                'session_duration': log.session_duration or 0.0,
                'mood_match':       True,
                'action_idx': (
                    1 if (log.liked or 0) > 0 else
                    2 if (log.liked or 0) < 0 else 0
                ),
                'gender': user.gender,
                'age':    user.age,
            }

            next_entry = None
            if same_user_next:
                next_entry = {
                    'mood':             next_log.mood or 'neutral',
                    'hour_of_day':      next_log.hour_of_day or 12,
                    'weather_humidity': next_log.weather_humidity or 50.0,
                    'weather_temp':     next_log.weather_temp or 25.0,
                    'genre_id':         next_log.genre_id or 0,
                    'liked':            next_log.liked or 0,
                    'gender':           next_user.gender if next_user else None,
                    'age':              next_user.age    if next_user else None,
                }

            model.train_on_log(entry, next_entry)

            if (i + 1) % 1000 == 0:
                print(f"  Processed {i + 1}/{len(rows)} logs...")

        print(f"\n✅ Global model trained!")
        print(f"   Interactions : {model.interaction_count}")
        print(f"   States       : {len(model.q_table)}")
        print(f"   Epsilon      : {round(model.epsilon, 4)}")
        print(f"   Saved to     : {GLOBAL_MODEL_PATH}")

        best = Counter()
        for qvals in model.q_table.values():
            best[ACTIONS[int(np.argmax(qvals))]] += 1
        print("\n   Top actions learned:")
        for action, count in best.most_common():
            print(f"     {action:25s} → {count} states")


if __name__ == '__main__':
    train_global()
