import sys
from pathlib import Path    # noqa
from importlib.util import find_spec    # noqa

from src.database.connection import db
from src.core.logger import setup_logging, get_logger
from src.core.taxonomy import ErrorAdvisor
from src.core.config import settings


def run_pipeline(logger):
    """
    Execute the full end-to-end pipeline.
    
    Sequence:
    1. Train Willingness Model
    2. Train Ability Model
    3. Score Willingness (using latest model)
    4. Score Ability (using latest model)
    5. Matrix Integration (Combine scores -> Database)
    """
    from src.database.repository import CollectionRepository
    from src.models.willingness.trainer import WillingnessTrainer
    from src.models.ability.trainer import AbilityTrainer
    from src.models.willingness.scorer import WillingnessScorer
    from src.models.ability.scorer import AbilityScorer
    from src.engine.matrix import MatrixEngine
    
    repository = CollectionRepository()
    
    # --- Step 1: Train Willingness Model ---
    if settings.MODE == "TRAIN" or settings.MODE == "FULL":
        logger.info(">>> STEP 1/5: Training Willingness Model")
        df_will = repository.get_willingness_training_data()
        will_trainer = WillingnessTrainer()
        will_trainer.train(df_will)
    
    # --- Step 2: Train Ability Model ---
    if settings.MODE == "TRAIN" or settings.MODE == "FULL":
        logger.info(">>> STEP 2/5: Training Ability Model")
        df_abil = repository.get_ability_training_data()
        abil_trainer = AbilityTrainer()
        abil_trainer.train(df_abil)
        
    # --- Step 3: Score Willingness ---
    logger.info(">>> STEP 3/5: Scoring Willingness")
    # Note: In production, scoring data might be different from training data
    # For now, we reuse the training data fetcher but in real life this would be a separate method
    df_score_will = repository.get_willingness_training_data() 
    will_scorer = WillingnessScorer()
    will_cache_path = will_scorer.score(df_score_will)
    
    # --- Step 4: Score Ability ---
    logger.info(">>> STEP 4/5: Scoring Ability")
    df_score_abil = repository.get_ability_training_data()
    abil_scorer = AbilityScorer()
    abil_cache_path = abil_scorer.score(df_score_abil)
    
    # --- Step 5: Matrix Integration ---
    logger.info(">>> STEP 5/5: Matrix Integration & Persistence")
    matrix_engine = MatrixEngine()
    
    # This loads both parquet files, joins them, calculates quadrants, and upserts to DB
    matrix_engine.integrate_and_save(will_cache_path, abil_cache_path)
    
    logger.info("Pipeline completed successfully!")


def main():
    """Main entry point for Collection AI batch job."""
    # Initialize logging first
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info(f"Starting Collection Batch Job in {settings.MODE} mode...")
    
    try:
        db.initialize_pool()
        logger.info("Database connection pool initialized successfully")
        
        # Execute full pipeline
        run_pipeline(logger)
            
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