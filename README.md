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
