import sys
from pathlib import Path    # noqa
from importlib.util import find_spec    # noqa

from src.database.connection import db
from src.core.logger import setup_logging, get_logger
from src.core.taxonomy import ErrorAdvisor
from src.core.config import settings
from src.database.queries import execute_query, get_query


def main():
    """Main entry point for Collection AI batch job."""
    # Initialize logging first
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info(f"Starting Collection Batch Job in {settings.MODE} mode...")
    
    try:
        db.initialize_pool()
        logger.info("Database connection pool initialized successfully")
        
        # Route based on MODE setting
        if settings.MODE.upper() == "TRAIN":
            run_training_mode(logger)
        elif settings.MODE.upper() == "SCORE":
            run_scoring_mode(logger)
        else:
            raise ValueError(f"Invalid MODE: {settings.MODE}. Must be 'TRAIN' or 'SCORE'")
            
    except Exception as e:
        # Use ErrorAdvisor to get actionable diagnostic
        diagnostic = ErrorAdvisor.analyze(e)
        logger.critical(f"FATAL ERROR:\n{diagnostic}")
        sys.exit(1)
    finally:
        db.close_pool()
        logger.info("Job Finished. Database pool closed.")


def run_training_mode(logger):
    """Execute model training pipeline."""
    import polars as pl
    from src.models.willingness.trainer import WillingnessTrainer
    
    logger.info("=== TRAINING MODE ===")
    logger.info("Fetching training data from database...")
    
    # Fetch raw data from database
    raw_data = execute_query(get_query("willingness"))
    logger.info(f"Retrieved {len(raw_data):,} records from database")
    
    # Convert to Polars DataFrame
    # Assuming raw_data is a list of tuples/rows from cursor.fetchall()
    df = pl.DataFrame(raw_data)
    logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
    
    # Train model
    logger.info("Initializing trainer...")
    trainer = WillingnessTrainer(model_dir="models")
    trainer.train(df)
    
    logger.info("Training completed successfully!")


def run_scoring_mode(logger):
    """Execute batch scoring pipeline."""
    import polars as pl
    from src.models.willingness.scorer import WillingnessScorer
    
    logger.info("=== SCORING MODE ===")
    logger.info("Fetching data for scoring...")
    
    # Fetch data to score
    raw_data = execute_query(get_query("willingness"))
    logger.info(f"Retrieved {len(raw_data):,} records for scoring")
    
    # Convert to Polars DataFrame
    df = pl.DataFrame(raw_data)
    logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
    
    # Initialize scorer
    logger.info("Loading trained model...")
    scorer = WillingnessScorer(model_dir="models", cache_dir="data/cache")
    
    # Generate predictions and cache to Parquet
    cache_path = scorer.score(df)
    logger.info(f"Predictions cached to: {cache_path}")
    
    # Print SQL skeleton for reference
    scorer.generate_sql_skeleton()
    
    logger.info("Scoring completed successfully!")
    logger.info("Next step: Load Parquet file into database staging table and execute MERGE")


if __name__ == "__main__":
    main()