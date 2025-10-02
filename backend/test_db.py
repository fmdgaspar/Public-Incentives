"""
Quick test script for database setup.
"""

import sys
sys.path.insert(0, '.')

from backend.app.db.init_db import init_db

if __name__ == "__main__":
    print("Testing database initialization...")
    init_db()
    print("✅ Database test successful!")

