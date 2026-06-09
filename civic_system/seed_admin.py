import os
import sys

# Add the civic_system directory to the path so we can import shared
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.database import init_database, users_col
from shared.models import make_user
from shared.security import hash_email, encrypt_email, hash_password

def seed_admin():
    init_database()
    
    email = "admin@mail.com"
    username = "Admin"
    password = "Admin1324"
    
    email_h = hash_email(email)
    encrypted_email = encrypt_email(email)
    username_lower = username.lower()
    password_hash = hash_password(password)
    
    admin = users_col().find_one({"email_hash": email_h})
    if not admin:
        users_col().insert_one(make_user(
            email_hash=email_h,
            encrypted_email=encrypted_email,
            username=username,
            username_lower=username_lower,
            password_hash=password_hash,
            role="admin"
        ))
        print("Admin user seeded.")
    else:
        users_col().update_one(
            {"email_hash": email_h},
            {"$set": {
                "encrypted_email": encrypted_email,
                "username": username,
                "username_lower": username_lower,
                "password_hash": password_hash,
                "role": "admin"
            }}
        )
        print("Admin user updated.")

if __name__ == "__main__":
    seed_admin()
