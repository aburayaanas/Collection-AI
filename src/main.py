import sys
from pathlib import Path    # noqa
from importlib.util import find_spec    # noqa

from src.database.connection import db
from src.core.logger import setup_logging, get_logger
from src.core.taxonomy import ErrorAdvisor
from src.core.config import settings


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
    """Execute model training pipeline for willingness or ability model."""
    from src.database.repository import CollectionRepository
    
    logger.info("=== TRAINING MODE ===")
    logger.info(f"Model Type: {settings.MODEL_TYPE}")
    
    # Initialize repository
    repository = CollectionRepository()
    
    # Route based on MODEL_TYPE
    if settings.MODEL_TYPE.upper() == "WILLINGNESS":
        from src.models.willingness.trainer import WillingnessTrainer
        
        # Fetch willingness training data
        df = repository.get_willingness_training_data()
        
        # Train willingness model
        logger.info("Initializing Willingness trainer...")
        trainer = WillingnessTrainer(model_dir="models")
        trainer.train(df)
        
    elif settings.MODEL_TYPE.upper() == "ABILITY":
        from src.models.ability.trainer import AbilityTrainer
        
        # Fetch ability training data
        df = repository.get_ability_training_data()
        
        # Train ability model
        logger.info("Initializing Ability trainer...")
        trainer = AbilityTrainer(model_dir="models")
        trainer.train(df)
        
    else:
        raise ValueError(f"Invalid MODEL_TYPE: {settings.MODEL_TYPE}. Must be 'WILLINGNESS' or 'ABILITY'")
    
    logger.info("Training completed successfully!")


def run_scoring_mode(logger):
    """Execute batch scoring pipeline for willingness or ability model."""
    from src.database.repository import CollectionRepository
    
    logger.info("=== SCORING MODE ===")
    logger.info(f"Model Type: {settings.MODEL_TYPE}")
    
    # Initialize repository
    repository = CollectionRepository()
    
    # Route based on MODEL_TYPE
    if settings.MODEL_TYPE.upper() == "WILLINGNESS":
        from src.models.willingness.scorer import WillingnessScorer
        
        # Fetch data
        df = repository.get_willingness_training_data()
        
        # Score with willingness model
        logger.info("Loading Willingness model...")
        scorer = WillingnessScorer(model_dir="models", cache_dir="data/cache")
        cache_path = scorer.score(df)
        logger.info(f"Predictions cached to: {cache_path}")
        scorer.generate_sql_skeleton()
        
    elif settings.MODEL_TYPE.upper() == "ABILITY":
        from src.models.ability.scorer import AbilityScorer
        
        # Fetch data
        df = repository.get_ability_training_data()
        
        # Score with ability model
        logger.info("Loading Ability model...")
        scorer = AbilityScorer(model_dir="models", cache_dir="data/cache")
        cache_path = scorer.score(df)
        logger.info(f"Predictions cached to: {cache_path}")
        scorer.generate_sql_skeleton()
        
    else:
        raise ValueError(f"Invalid MODEL_TYPE: {settings.MODEL_TYPE}. Must be 'WILLINGNESS' or 'ABILITY'")
    
    logger.info("Scoring completed successfully!")
    logger.info("Next step: Load Parquet file into database staging table and execute MERGE")


if __name__ == "__main__":
    main()