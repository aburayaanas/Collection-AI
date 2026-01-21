"""
This module is used to execute queries to the database.
"""
from src.database.connection import db
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURES_DIR = BASE_DIR / "database/features"

def execute_query(query: str) -> list:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

def get_query(query_name: str) -> str:
    with open(FEATURES_DIR / f"{query_name}.sql", "r", encoding="utf-8") as f:
        return f.read()