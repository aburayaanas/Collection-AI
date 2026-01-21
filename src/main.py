import sys
from pathlib import Path


file_path = Path(__file__).resolve()
root_dir = file_path.parent.parent

sys.path.insert(0, str(root_dir))

from src.database.connection import db  #noqa
from src.core.logger import setup_logging, get_logger  #noqa
from src.core.taxonomy import ErrorAdvisor  #noqa
from src.database.queries import execute_query, get_query  #noqa


def main():
    # Initialize logging first
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting Collection Batch Job...")
    
    try:
        db.initialize_pool()
        logger.info("Database connection pool initialized successfully")
        
        df = execute_query(get_query("willingness"))
        df2 = 1
        
    except Exception as e:
        # Use ErrorAdvisor to get actionable diagnostic
        diagnostic = ErrorAdvisor.analyze(e)
        logger.critical(f"FATAL ERROR:\n{diagnostic}")
        sys.exit(1)
    finally:
        db.close_pool()
        logger.info("Job Finished. Database pool closed.")




if __name__ == "__main__":
    main()