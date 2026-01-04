from app import app, db
import os

if __name__ == '__main__':
    # Ensure the instance folder exists
    os.makedirs('instance', exist_ok=True)
    
    # Initialize the database
    with app.app_context():
        db.create_all()
        print("Baza podatkov je bila uspešno inicializirana.")