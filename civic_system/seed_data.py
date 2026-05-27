"""
Seed script to populate sample civic issues across India.
Run this script to initialize the database with sample data.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from shared.database import SessionLocal, init_database
from shared.models import Base, Issue, Comment, User

# Initialize database
init_database(Base)

# Sample issues across India
SAMPLE_ISSUES = [
    {
        "title": "Massive pothole causing traffic accidents on MG Road",
        "category": "Pothole",
        "description": "A large crater-sized pothole near the intersection of MG Road and Brigade Road has been causing vehicle damage and traffic congestion. Multiple commuters report suspension damage and motorcycle skids.",
        "address": "MG Road, Bangalore, Karnataka",
        "ward": "Bangalore - Cubbon Park",
        "latitude": 13.1939,
        "longitude": 77.5937,
        "location_label": "MG Road & Brigade Road intersection",
        "reporter_email": "rajesh.kumar@gmail.com",
        "image_path": "/uploads/DHpotholesBengaluru.avif",
        "created_at": datetime.utcnow() - timedelta(days=5),
        "status": "In Progress",
    },
    {
        "title": "Overflowing garbage bins contaminating groundwater",
        "category": "Garbage",
        "description": "The waste collection point near residential blocks C and D is overflowing. Garbage bags are scattered, attracting stray animals and contaminating the nearby groundwater source.",
        "address": "JVLR Near Vikhroli Station, Mumbai, Maharashtra",
        "ward": "Mumbai - Vikhroli East",
        "latitude": 19.1136,
        "longitude": 72.9629,
        "location_label": "Residential waste point near Vikhroli",
        "reporter_email": "priya.sharma@yahoo.com",
        "image_path": None,
        "created_at": datetime.utcnow() - timedelta(days=3),
        "status": "Pending",
    },
    {
        "title": "Clogged drainage causing waterlogging during rains",
        "category": "Drainage",
        "description": "Broken drainage pipes on Shah Ali Lane have blocked water flow. During monsoons, the entire street floods, making it impassable for vehicles and pedestrians. Water is stagnating for 2-3 days after rain.",
        "address": "Shah Ali Lane, Old Delhi, New Delhi",
        "ward": "Delhi - Chandni Chowk",
        "latitude": 28.6353,
        "longitude": 77.2300,
        "location_label": "Shah Ali Lane near Jama Masjid",
        "reporter_email": "vikram.singh@outlook.com",
        "image_path": None,
        "created_at": datetime.utcnow() - timedelta(days=7),
        "status": "Pending",
    },
    {
        "title": "Streetlight outages causing safety issues in residential area",
        "category": "Streetlight",
        "description": "Five consecutive streetlights on Whitefield Avenue are non-functional. Residents report increased theft and safety concerns, especially for evening walkers and cyclists. Children cannot play after 6 PM.",
        "address": "Whitefield Avenue, Bangalore, Karnataka",
        "ward": "Bangalore - Whitefield",
        "latitude": 12.9698,
        "longitude": 77.7499,
        "location_label": "Whitefield Avenue near Tech Park",
        "reporter_email": "anjali.reddy@gmail.com",
        "image_path": None,
        "created_at": datetime.utcnow() - timedelta(days=4),
        "status": "Pending",
    },
    {
        "title": "Water leak from municipal pipeline flooding homes",
        "category": "Water",
        "description": "A burst water pipe on Bandra Reclamation has been leaking for weeks. Water accumulates on the road, and nearby residents report water seeping into their ground floors and basements. The leak is visible from Google Street View.",
        "address": "Bandra Reclamation, Mumbai, Maharashtra",
        "ward": "Mumbai - Bandra West",
        "latitude": 19.0594,
        "longitude": 72.8295,
        "location_label": "Bandra Reclamation near Linking Road",
        "reporter_email": "neha.patel@gmail.com",
        "image_path": None,
        "created_at": datetime.utcnow() - timedelta(days=2),
        "status": "In Progress",
    },
]

def seed_database():
    """Populate the database with sample issues."""
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing_count = db.query(Issue).count()
        if existing_count > 0:
            print(f"Database already contains {existing_count} issues. Skipping seed to avoid duplicates.")
            print("To reseed, delete the database and run this script again.")
            return
        
        # Add sample issues
        print("Seeding sample issues...")
        for issue_data in SAMPLE_ISSUES:
            issue = Issue(
                title=issue_data["title"],
                category=issue_data["category"],
                description=issue_data["description"],
                address=issue_data["address"],
                ward=issue_data["ward"],
                latitude=issue_data["latitude"],
                longitude=issue_data["longitude"],
                location_label=issue_data["location_label"],
                reporter_email=issue_data["reporter_email"],
                image_path=issue_data["image_path"],
                is_public=True,
                status=issue_data["status"],
                created_at=issue_data["created_at"],
            )
            db.add(issue)
            print(f"  ✓ Added: {issue.title}")
        
        db.commit()
        
        # Add sample comments to first issue
        first_issue = db.query(Issue).first()
        if first_issue:
            sample_comments = [
                {
                    "name": "Ramesh T.",
                    "email": "ramesh.t@gmail.com",
                    "body": "I hit this pothole yesterday and my bike got damaged. The repair cost me ₹3000. This needs immediate action!",
                },
                {
                    "name": "Deepa S.",
                    "email": "deepa.sharma@yahoo.com",
                    "body": "Yes, I also damaged my car suspension here last week. Multiple people have complained to me about this same spot.",
                },
            ]
            
            for comment_data in sample_comments:
                comment = Comment(
                    issue_id=first_issue.id,
                    commenter_name=comment_data["name"],
                    commenter_email=comment_data["email"],
                    body=comment_data["body"],
                )
                db.add(comment)
                print(f"  ✓ Added comment from {comment_data['name']}")
        
        db.commit()
        
        # Create users for the reporters
        for issue_data in SAMPLE_ISSUES:
            existing_user = db.query(User).filter(User.email == issue_data["reporter_email"]).first()
            if not existing_user:
                user = User(email=issue_data["reporter_email"], role="public")
                db.add(user)
        
        db.commit()
        
        print("\n✅ Database seeding completed successfully!")
        print(f"   Total issues added: {len(SAMPLE_ISSUES)}")
        print("   Sample comments added to first issue")
        print("   Reporter users created\n")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
