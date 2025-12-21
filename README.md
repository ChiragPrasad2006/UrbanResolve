# UrbanResolve
Civic Issue reporting app

structure: 

civic-system/
│
├── shared/
│   ├── database.py
│   ├── models.py
│   ├── email_utils.py
│   └── security.py
│
├── public_app/
│   ├── main.py
│   ├── templates/
│   │   ├── index.html
│   │   ├── login.html
│   │   └── report_new.html
│   └── static/
│       └── styles.css
│
└── admin_app/
    ├── main.py
    ├── templates/
    │   ├── login.html
    │   └── dashboard.html
    └── static/
        └── styles.css


requirement/python libraries:
fastapi
uvicorn[standard]
sqlalchemy
pydantic
jinja2
python-multipart
