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
    df = pl.DataFrame(raw_data)
    logger.info(f"Converted to Polars DataFrame: {df.shape[0]:,} rows x {df.shape[1]} columns")
    
    # Train model
    logger.info("Initializing trainer...")
    trainer = WillingnessTrainer(model_dir="models")
    trainer.train(df)
    
    logger.info("Training completed successfully!")


def run_scoring_mode(logger):
    """Execute batch scoring pipeline with SHAP explanation phase."""
    import polars as pl
    from src.models.willingness.scorer import WillingnessScorer
    from src.models.ability.scorer import AbilityScorer
    from src.explainability.shadow_runner import (
        run_shap_phase,
        ExplainabilityConfig,
    )
    
    logger.info("=== SCORING MODE ===")
    
    # ── 1. Score Willingness ─────────────────────────────────────────
    logger.info("Fetching willingness data for scoring...")
    raw_will = execute_query(get_query("willingness"))
    logger.info(f"Retrieved {len(raw_will):,} willingness records")
    df_will = pl.DataFrame(raw_will)
    
    logger.info("Loading willingness model...")
    will_scorer = WillingnessScorer(model_dir="models", cache_dir="data/cache")
    will_cache = will_scorer.score(df_will)
    logger.info(f"Willingness predictions cached to: {will_cache}")
    
    # ── 2. Score Ability ─────────────────────────────────────────────
    logger.info("Fetching ability data for scoring...")
    raw_abi = execute_query(get_query("ability"))
    logger.info(f"Retrieved {len(raw_abi):,} ability records")
    df_abi = pl.DataFrame(raw_abi)
    
    logger.info("Loading ability model...")
    abi_scorer = AbilityScorer(model_dir="models", cache_dir="data/cache")
    abi_cache = abi_scorer.score(df_abi)
    logger.info(f"Ability predictions cached to: {abi_cache}")
    
    # ── 3. SHAP Explanation Phase ────────────────────────────────────
    #    Runs AFTER scoring. Failures never crash the pipeline.
    logger.info("=== SHAP EXPLANATION PHASE ===")
    
    shap_config = ExplainabilityConfig(
        enabled=True,
        top_n=3,
        batch_size=20,
        insert_dwh=True,
    )
    
    # — Willingness SHAP —
    logger.info("Running SHAP for willingness model...")
    will_shap = run_shap_phase(
        scored_data=df_will,
        model=will_scorer.model,
        model_type="willingness",
        model_version=f"willingness_{will_cache.split('_')[-1].replace('.parquet', '')}",
        config=shap_config,
        id_col="CUST_INFO_ID",
    )
    logger.info(
        f"Willingness SHAP: success={will_shap.success}, "
        f"dwh_rows={will_shap.dwh_rows_inserted}, "
        f"time={will_shap.runtime_seconds:.2f}s"
    )
    
    # — Ability SHAP —
    logger.info("Running SHAP for ability model...")
    abi_shap = run_shap_phase(
        scored_data=df_abi,
        model=abi_scorer.model,
        model_type="ability",
        model_version=f"ability_{abi_cache.split('_')[-1].replace('.parquet', '')}",
        config=shap_config,
        id_col="CUST_INFO_ID",
    )
    logger.info(
        f"Ability SHAP: success={abi_shap.success}, "
        f"dwh_rows={abi_shap.dwh_rows_inserted}, "
        f"time={abi_shap.runtime_seconds:.2f}s"
    )
    
    # ── 4. SQL skeleton (legacy reference) ───────────────────────────
    will_scorer.generate_sql_skeleton()
    
    logger.info("Scoring + SHAP explanation completed successfully!")
    logger.info(
        "SHAP results inserted into PIO_COLL_AI_MATRIX_RESULTS on openbi2 DWH."
    )


if __name__ == "__main__":
    main()