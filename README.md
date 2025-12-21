# UrbanResolve
Civic Issue reporting app

requirement/python libraries:
fastapi
uvicorn[standard]
sqlalchemy
pydantic
jinja2
python-multipart

To Run: 
-> open terminal in the folder
->uvicorn public_app.main:app --reload --port 8000 (for public)
->uvicorn admin_app.main:app --reload --port 9000  (for Admin)

To make a user Admin:
->open python on terminal by typing "python"
->from shared.database import SessionLocal
->from shared.models import User
->db = SessionLocal()
->db.add(User(email="admin@example.com", role="admin"))
->db.commit()
->db.close()
