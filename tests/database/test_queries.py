import unittest
from unittest.mock import MagicMock, patch
from src.database.queries import get_snap_date

class TestGetSnapDate(unittest.TestCase):
    
    @patch('src.database.queries.db')
    def test_get_snap_date_success(self, mock_db):
        """Test successful retrieval of snapshot date."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Setup mock behavior
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ('2026-02-15',) # Return tuple as fetchone does
        
        # Call function
        result = get_snap_date("1", "400")
        
        # Assertions
        mock_cursor.execute.assert_called_with("SELECT TO_CHAR(SNAP_DATE(:1, :2), 'YYYY-MM-DD') FROM DUAL", ['400', '1'])
        self.assertEqual(result, '2026-02-15')

    @patch('src.database.queries.db')
    def test_get_snap_date_none(self, mock_db):
        """Test when query returns no result."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        result = get_snap_date("1", "400")
        
        self.assertIsNone(result)

    @patch('src.database.queries.db')
    def test_get_snap_date_exception(self, mock_db):
        """Test database exception handling."""
        mock_db.get_connection.side_effect = Exception("Database error")
        
        # Should catch exception and return None
        result = get_snap_date("1", "400")
        
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
