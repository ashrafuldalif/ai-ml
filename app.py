from flask import Flask
from extensions import db, login_manager
from models import User
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'supersecretkey123'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///musicapp.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join('static', 'music')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.user import user_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    with app.app_context():
        db.create_all()
        # Migrate existing DB: add gender and age columns if missing
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        existing_cols = [c['name'] for c in inspector.get_columns('users')]
        with db.engine.connect() as conn:
            if 'gender' not in existing_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN gender VARCHAR(20)'))
                conn.commit()
            if 'age' not in existing_cols:
                conn.execute(text('ALTER TABLE users ADD COLUMN age INTEGER'))
                conn.commit()
        from werkzeug.security import generate_password_hash
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@music.com',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)