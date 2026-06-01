"""
Adds random ListenLog entries for all non-admin users.
Run with:  python seed_logs.py
"""

import random
from datetime import datetime, timedelta
from app import create_app
from extensions import db
from models import User, Song, ListenLog

app = create_app()

MOODS = ["happy", "sad", "energetic", "calm", "neutral", "romantic", "angry", "focused"]

def rand_date(days_back=180):
    return datetime.utcnow() - timedelta(days=random.randint(0, days_back))

def main():
    with app.app_context():
        users = User.query.filter_by(is_admin=False).all()
        songs = Song.query.all()

        if not users or not songs:
            print("No users or songs found.")
            return

        print(f"Adding listen logs for {len(users)} users across {len(songs)} songs...")

        added = 0
        for user in users:
            # Each user gets between 10–30 random log entries
            for _ in range(random.randint(10, 30)):
                song = random.choice(songs)
                ts   = rand_date(180)
                db.session.add(ListenLog(
                    user_id=user.id,
                    song_id=song.id,
                    timestamp=ts,
                    hour_of_day=ts.hour,
                    day_of_week=ts.weekday(),
                    mood=random.choice(MOODS),
                    weather_humidity=round(random.uniform(30, 90), 1),
                    weather_temp=round(random.uniform(10, 40), 1),
                    session_duration=round(random.uniform(30, 300), 1),
                    liked=random.choice([0, 1]),
                    completed=random.choice([True, False]),
                    genre_id=song.genre_id,
                ))
                added += 1

            # Commit every 50 users to keep memory low
            if added % (50 * 20) == 0:
                db.session.commit()

        db.session.commit()
        print(f"Done! {added} listen logs added.")
        print(f"Total logs in DB: {ListenLog.query.count()}")

if __name__ == "__main__":
    main()
