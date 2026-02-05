"""
This module is used to execute queries to the database.
"""
from src.database.connection import db
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURES_DIR = BASE_DIR / "database/features"

def execute_query(query: str) -> tuple[list[str], list]:
    """
    Execute a SQL query and return column names and results.
    
    Args:
        query: SQL query string to execute
        
    Returns:
        Tuple of (column_names, rows) where:
        - column_names: List of column names from cursor.description
        - rows: List of tuples containing row data
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        
        # Extract column names from cursor metadata
        column_names = [col[0] for col in cursor.description]
        
        # Fetch all rows
        rows = cursor.fetchall()
        
        return column_names, rows

def get_query(query_name: str) -> str:
    with open(FEATURES_DIR / f"{query_name}.sql", "r", encoding="utf-8") as f:
        return f.read()