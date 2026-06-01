"""
Seed script — copies songs from temp_songs/ into static/music/ and
populates the database with genres, songs, users, and listen logs.

Run with:
    python seed.py
"""

import os
import re
import shutil
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from app import create_app
from extensions import db
from models import User, Genre, Song, ListenLog

app = create_app()

# ── paths ─────────────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TEMP_SONGS  = os.path.join(BASE_DIR, "temp_songs")   # source
DEST_MUSIC  = os.path.join(BASE_DIR, "static", "music")  # where Flask serves from

# ── genre map  (subfolder name → DB genre name) ───────────────────────────────

GENRE_MAP = {
    "classical": "Classical",
    "metal":     "Metal",
    "hiphop":    "Hip-Hop",
    "jazz":      "Jazz",
    "country":   "Country",
}

# ── user data ─────────────────────────────────────────────────────────────────

MOODS = ["happy", "sad", "energetic", "calm", "neutral", "romantic", "angry", "focused"]

FIRST_NAMES_M = [
    "James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles",
    "Daniel","Matthew","Anthony","Mark","Donald","Steven","Paul","Andrew","Joshua","Kenneth",
    "Kevin","Brian","George","Timothy","Ronald","Edward","Jason","Jeffrey","Ryan","Jacob",
    "Gary","Nicholas","Eric","Jonathan","Stephen","Larry","Justin","Scott","Brandon","Benjamin",
    "Samuel","Raymond","Gregory","Frank","Alexander","Patrick","Jack","Dennis","Jerry","Tyler",
    "Aaron","Jose","Adam","Henry","Nathan","Douglas","Zachary","Peter","Kyle","Walter",
    "Ethan","Jeremy","Harold","Terry","Sean","Austin","Gerald","Carl","Keith","Roger",
    "Arthur","Lawrence","Dylan","Jesse","Bryan","Joe","Jordan","Billy","Albert","Willie",
    "Gabriel","Logan","Alan","Juan","Wayne","Roy","Ralph","Randy","Eugene","Vincent",
    "Russell","Louis","Philip","Bobby","Johnny","Bradley","Carlos","Chris","Caleb","Mason",
]

FIRST_NAMES_F = [
    "Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen",
    "Lisa","Nancy","Betty","Margaret","Sandra","Ashley","Dorothy","Kimberly","Emily","Donna",
    "Michelle","Carol","Amanda","Melissa","Deborah","Stephanie","Rebecca","Sharon","Laura","Cynthia",
    "Kathleen","Amy","Angela","Shirley","Anna","Brenda","Pamela","Emma","Nicole","Helen",
    "Samantha","Katherine","Christine","Debra","Rachel","Carolyn","Janet","Catherine","Maria","Heather",
    "Diane","Julie","Joyce","Victoria","Kelly","Christina","Lauren","Joan","Evelyn","Olivia",
    "Judith","Megan","Cheryl","Martha","Andrea","Frances","Hannah","Jacqueline","Ann","Gloria",
    "Jean","Kathryn","Alice","Teresa","Sara","Janice","Doris","Madison","Julia","Grace",
    "Judy","Abigail","Marie","Denise","Beverly","Amber","Theresa","Marilyn","Danielle","Diana",
    "Brittany","Natalie","Sophia","Rose","Isabella","Alexis","Kayla","Charlotte","Avery","Ella",
]

LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
    "Ahmed","Khan","Ali","Hassan","Islam","Rahman","Chowdhury","Hossain","Akter","Begum",
    "Karim","Rahim","Uddin","Miah","Patel","Shah","Sharma","Gupta","Singh","Kumar",
]

# ── helpers ───────────────────────────────────────────────────────────────────

def rand_date(days_back=730):
    return datetime.utcnow() - timedelta(days=random.randint(0, days_back))


def make_title(filename: str, genre_name: str) -> str:
    """
    Turn  'classical.00042.wav'  →  'Classical 42'
    Strips the genre prefix and dots, converts the number to an int so
    there are no leading zeros.
    """
    stem = os.path.splitext(filename)[0]          # 'classical.00042'
    # Remove the genre prefix (letters only) and any leading dots/spaces
    number_part = re.sub(r'^[a-zA-Z]+\.?', '', stem).strip('. ')
    try:
        number = str(int(number_part))            # '00042' → '42'
    except ValueError:
        number = number_part
    return f"{genre_name} {number}"

# ── seed steps ────────────────────────────────────────────────────────────────

def seed_genres():
    """Insert the 5 genres and return {name: id} map."""
    print("Seeding genres...")
    genre_id_map = {}
    for genre_name in GENRE_MAP.values():
        g = Genre.query.filter_by(name=genre_name).first()
        if not g:
            g = Genre(name=genre_name)
            db.session.add(g)
            db.session.flush()
        genre_id_map[genre_name] = g.id
    db.session.commit()
    print(f"  {len(genre_id_map)} genres ready.")
    return genre_id_map


def seed_songs(genre_id_map: dict):
    """Copy audio files from temp_songs/ → static/music/ and insert Song rows."""
    print("Seeding songs...")
    os.makedirs(DEST_MUSIC, exist_ok=True)

    added = skipped = errors = 0

    for subfolder, genre_name in GENRE_MAP.items():
        src_dir = os.path.join(TEMP_SONGS, subfolder)
        if not os.path.isdir(src_dir):
            print(f"  ⚠  Subfolder not found: {src_dir}")
            continue

        genre_id = genre_id_map[genre_name]
        files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith('.wav'))

        for filename in files:
            # Skip if already in DB
            if Song.query.filter_by(filename=filename).first():
                skipped += 1
                continue

            src_path  = os.path.join(src_dir, filename)
            dest_path = os.path.join(DEST_MUSIC, filename)

            # Copy file (skip if already copied)
            try:
                if not os.path.exists(dest_path):
                    shutil.copy2(src_path, dest_path)
            except OSError as e:
                print(f"  ✗  Could not copy {filename}: {e}")
                errors += 1
                continue

            title = make_title(filename, genre_name)

            db.session.add(Song(
                title=title,
                artist=f"{genre_name} Artist",
                genre_id=genre_id,
                filename=filename,
                cover_image="default_cover.png",
                duration=round(random.uniform(120, 360), 1),
                upload_date=rand_date(500),
                play_count=random.randint(0, 5000),
            ))
            added += 1

        # Commit per genre to avoid one giant transaction
        db.session.commit()
        print(f"  [{genre_name}] {added} added so far...")

    print(f"  Songs done — {added} added, {skipped} skipped, {errors} errors.")


def seed_users(target=210):
    print("Seeding users...")
    hashed_pw = generate_password_hash("password123")
    added = 0

    combos_m = [(fn, ln) for fn in FIRST_NAMES_M for ln in LAST_NAMES]
    combos_f = [(fn, ln) for fn in FIRST_NAMES_F for ln in LAST_NAMES]
    random.shuffle(combos_m)
    random.shuffle(combos_f)

    for i in range(target):
        gender = "Male" if i % 2 == 0 else "Female"
        fn, ln = (combos_m if gender == "Male" else combos_f)[i // 2]
        username = f"{fn.lower()}.{ln.lower()}{i}"
        email    = f"{username}@example.com"
        if User.query.filter_by(username=username).first():
            continue
        db.session.add(User(
            username=username,
            email=email,
            password=hashed_pw,
            gender=gender,
            age=random.randint(16, 60),
            is_admin=False,
            created_at=rand_date(365),
        ))
        added += 1

    db.session.commit()
    print(f"  {added} users added.")


def seed_listen_logs():
    print("Seeding listen logs...")
    all_users = User.query.filter_by(is_admin=False).all()
    all_songs = Song.query.all()

    if not all_users or not all_songs:
        print("  ⚠  No users or songs found — skipping logs.")
        return

    added = 0
    sample = random.sample(all_users, min(50, len(all_users)))

    for user in sample:
        for _ in range(random.randint(5, 20)):
            song = random.choice(all_songs)
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

    db.session.commit()
    print(f"  {added} listen logs added.")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.isdir(TEMP_SONGS):
        print(f"ERROR: temp_songs folder not found at {TEMP_SONGS}")
        return

    with app.app_context():
        genre_id_map = seed_genres()
        seed_songs(genre_id_map)
        seed_users()
        seed_listen_logs()

        print("\n✅ Seeding complete!")
        print(f"   Genres : {Genre.query.count()}")
        print(f"   Songs  : {Song.query.count()}")
        print(f"   Users  : {User.query.count()}")
        print(f"   Logs   : {ListenLog.query.count()}")


if __name__ == "__main__":
    main()
