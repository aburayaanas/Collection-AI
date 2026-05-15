import sys
from pathlib import Path    # noqa
from src.database.connection import db
from src.core.logger import setup_logging, get_logger
from src.core.taxonomy import ErrorAdvisor
from src.core.config import settings
from src.core.validation import validate_training_data, validate_scoring_data, validate_matrix_inputs
from src.database.repository import CollectionRepository
import polars as pl

# ── Modular Pipeline Steps ──────────────────────────────────────────

def run_training_steps(logger):
    """Execute training for configured scopes."""
    from src.models_engine.willingness.trainer import WillingnessTrainer
    from src.models_engine.ability.trainer import AbilityTrainer

    scope = settings.MODEL_SCOPE.upper()
    logger.info(f"=== TRAINING PHASE (Scope: {scope}) ===")
    
    repo = CollectionRepository()

    # 1. Train Willingness
    if scope in ["WILLINGNESS", "BOTH"]:
        logger.info(">> Train Willingness Model")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_willingness_training_data()
            validate_training_data(df, target_col="TARGET_WILLINGNESS", context="Willingness Training")
            logger.info(f"Training on {df.height:,} records")
            trainer = WillingnessTrainer(model_dir="models")
            trainer.train(df)
        except Exception as e:
            logger.error(f"Willingness training failed: {e}")
            raise

    # 2. Train Ability
    if scope in ["ABILITY", "BOTH"]:
        logger.info(">> Train Ability Model")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_ability_training_data()
            validate_training_data(df, target_col="TARGET_ABILITY", context="Ability Training")
            logger.info(f"Training on {df.height:,} records")
            
            trainer = AbilityTrainer(model_dir="models")
            trainer.train(df)
            
        except Exception as e:
            logger.error(f"Ability training failed: {e}")
            raise

def run_scoring_steps(logger) -> dict:
    """
    Execute scoring for configured scopes.
    Returns dictionary of cache paths for matrix integration.
    """
    from src.models_engine.willingness.scorer import WillingnessScorer
    from src.models_engine.ability.scorer import AbilityScorer

    scope = settings.MODEL_SCOPE.upper()
    logger.info(f"=== SCORING PHASE (Scope: {scope}) ===")
    
    repo = CollectionRepository()
    cache_paths = {}

    # 1. Score Willingness
    if scope in ["WILLINGNESS", "BOTH"]:
        logger.info(">> Score Willingness")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_willingness_training_data()
            validate_scoring_data(df, context="Willingness Scoring")
            scorer = WillingnessScorer(model_dir="models", cache_dir="data/cache")
            path = scorer.score(df)
            cache_paths["willingness"] = path
            logger.info(f"Willingness scores cached: {path}")
        except Exception as e:
            logger.error(f"Willingness scoring failed: {e}")
            raise

    # 2. Score Ability
    if scope in ["ABILITY", "BOTH"]:
        logger.info(">> Score Ability")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_ability_training_data()
            validate_scoring_data(df, context="Ability Scoring")
            scorer = AbilityScorer(model_dir="models", cache_dir="data/cache")
            path = scorer.score(df)
            cache_paths["ability"] = path
            logger.info(f"Ability scores cached: {path}")
        except Exception as e:
            logger.error(f"Ability scoring failed: {e}")
            raise
            
    return cache_paths

def run_matrix_integration(logger, cache_paths: dict) -> pl.DataFrame | None:
    """Execute matrix integration if both scores are available.

    Returns:
        pl.DataFrame | None: The fully enriched matrix DataFrame returned
            by MatrixEngine, or None if integration was skipped.
    """
    from src.engine.matrix import MatrixEngine
    
    logger.info("=== MATRIX INTEGRATION PHASE ===")
    
    w_path = cache_paths.get("willingness")
    a_path = cache_paths.get("ability")
    
    if w_path and a_path:
        logger.info("Both scores available. Integrating...")
        
        # Quick validation on the Parquet files before integration
        df_w = pl.read_parquet(w_path)
        df_a = pl.read_parquet(a_path)
        validate_matrix_inputs(df_w, required_cols=["CUST_INFO_ID", "WILLINGNESS_SCORE"], context="Willingness Scores")
        validate_matrix_inputs(df_a, required_cols=["CUST_INFO_ID", "ABILITY_SCORE"], context="Ability Scores")
        
        engine = MatrixEngine()
        return engine.integrate_and_save(w_path, a_path)
    else:
        logger.warning("Skipping Matrix Integration: Missing one or both score files (Check MODEL_SCOPE).")
        return None


def run_nba_steps(logger, matrix_df: pl.DataFrame | None) -> None:
    """Execute the NBA engine on the matrix output and persist recommendations.

    Isolated from the outer try/except in main() so a NBA failure never
    rolls back or corrupts the already-committed Matrix results.

    Args:
        logger: Pipeline logger instance.
        matrix_df (pl.DataFrame | None): Enriched matrix DataFrame returned
            by run_matrix_integration(). If None, this step is skipped.
    """
    from src.engine.nba.orchestrator import NBAOrchestrator

    logger.info("=== NBA PHASE ===")

    if matrix_df is None or matrix_df.height == 0:
        logger.warning("NBA phase skipped: no matrix output available.")
        return

    repo = CollectionRepository()

    # ── Step 1: Convert quadrant int → string ────────────────────────
    # CURRENT_QUADRANT is stored as int (1-4) in the matrix output;
    # CustomerState expects the string literal "Q1"–"Q4".
    df_matrix = matrix_df.with_columns(
        (pl.lit("Q") + pl.col("CURRENT_QUADRANT").cast(pl.Utf8)).alias("CURRENT_QUADRANT")
    )

    # ── Step 2: Fetch NBA context from the dedicated context mart ─────
    # Completely isolated from the ML feature marts. The DB team fills
    # PIO_COLL_AI_NBA_CONTEXT_MART daily from source systems.
    # In development, the seed script populates it.
    try:
        df_context = repo.get_nba_context_data()
    except Exception as ctx_exc:
        logger.warning(
            f"Could not fetch NBA context mart: {ctx_exc}. "
            f"Proceeding with safe defaults (guardrail ceilings will not fire)."
        )
        # Build an empty context frame so the left join degrades gracefully
        df_context = pl.DataFrame(schema={
            "CUST_INFO_ID":       pl.String,
            "ACCOUNT_STATUS":     pl.String,
            "TOTAL_DUE":          pl.Float64,
            "SMS_SENT_THIS_WEEK": pl.Int64,
            "CALLS_MADE_TODAY":   pl.Int64,
        })

    # ── Step 3: Join context onto matrix (left join — matrix is leading) ─
    # Customers missing from the context mart get safe defaults:
    #   ACCOUNT_STATUS = "Active" (no exclusion fires)
    #   TOTAL_DUE = 0 (field-visit / dunning blocked — conservative)
    #   SMS/CALLS = 0 (no frequency caps fire)
    df_nba_input = df_matrix.join(df_context, on="CUST_INFO_ID", how="left").with_columns([
        pl.col("ACCOUNT_STATUS").fill_null("Active"),
        pl.col("TOTAL_DUE").fill_null(0.0),
        pl.col("SMS_SENT_THIS_WEEK").fill_null(0),
        pl.col("CALLS_MADE_TODAY").fill_null(0),
    ])

    logger.info(
        f"NBA input prepared | {df_nba_input.height:,} customers | "
        f"context_matched={df_context.height:,}"
    )

    # ── Run the orchestrator ──────────────────────────────────────────
    orchestrator = NBAOrchestrator()
    df_nba_output = orchestrator.process_batch(df_nba_input)

    # ── Add tenant + date context required by the DB MERGE ───────────
    day_date = matrix_df["DAY_DATE"][0]
    df_nba_output = df_nba_output.with_columns([
        pl.lit(day_date).alias("DAY_DATE"),
        pl.lit(settings.INST_CODE).alias("INST_CODE"),
        pl.lit(settings.COUNTRY_CODE).alias("COUNTRY_CODE"),
    ])

    # ── Log summary ───────────────────────────────────────────────────
    total = df_nba_output.height
    error_rows = df_nba_output.filter(
        pl.col("REASON_CODE").str.starts_with("ERROR:")
    ).height
    logger.info(
        f"NBA results | total={total:,}, "
        f"success={total - error_rows:,}, errors={error_rows:,}"
    )

    # ── Persist ───────────────────────────────────────────────────────
    repo.upsert_nba_results(df_nba_output)


def run_shap_steps(logger):
    """Execute SHAP explanations for configured scopes (Reads from DB/Cache re-scoring)."""
    from src.models_engine.willingness.scorer import WillingnessScorer
    from src.models_engine.ability.scorer import AbilityScorer
    from src.explainability.shadow_runner import run_shap_phase, ExplainabilityConfig

    scope = settings.SHAP_SCOPE.upper()
    if scope == "NONE":
        logger.info("SHAP phase skipped (SHAP_SCOPE=NONE)")
        return

    logger.info(f"=== SHAP PHASE (Scope: {scope}) ===")
    
    repo = CollectionRepository()
    shap_config = ExplainabilityConfig(
        enabled=True,
        top_n=3,
        batch_size=20,
        insert_dwh=True
    )

    # 1. SHAP Willingness
    if scope in ["WILLINGNESS", "BOTH"]:
        logger.info(">> Explain Willingness")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_willingness_training_data()
            
            # We need the model object
            scorer = WillingnessScorer(model_dir="models", cache_dir="data/cache")
            # We assume scorer loads the model on init or we force it
            if not hasattr(scorer, 'model') or scorer.model is None:
                 scorer.load_model()
            
            run_shap_phase(
                scored_data=df, 
                model=scorer.model, 
                model_type="willingness",
                config=shap_config
            )
        except Exception as e:
            logger.error(f"Willingness SHAP failed: {e}")

    # 2. SHAP Ability
    if scope in ["ABILITY", "BOTH"]:
        logger.info(">> Explain Ability")
        try:
            # Use repository to fetch data with date filter
            df = repo.get_ability_training_data()
            
            scorer = AbilityScorer(model_dir="models", cache_dir="data/cache")
            if not hasattr(scorer, 'model') or scorer.model is None:
                 scorer.load_model()

            run_shap_phase(
                scored_data=df, 
                model=scorer.model, 
                model_type="ability",
                config=shap_config
            )
        except Exception as e:
            logger.error(f"Ability SHAP failed: {e}")

# ── Main Entry Point ────────────────────────────────────────────────

def main():
    """Main orchestrator."""
    setup_logging()
    logger = get_logger(__name__)
    
    mode = settings.MODE.upper()
    logger.info(f"Starting Pipeline | Mode: {mode} | Scope: {settings.MODEL_SCOPE} | SHAP: {settings.SHAP_SCOPE}")
    
    try:
        db.initialize_pool()
        
        # 1. Training (if TRAIN or FULL)
        if mode in ["TRAIN", "FULL"]:
            run_training_steps(logger)

        # 2. Scoring + Matrix + SHAP (if SCORE or FULL)
        if mode in ["SCORE", "FULL"]:
            # A. Scoring
            cache_paths = run_scoring_steps(logger)
            
            # B. Matrix Integration (ONLY if both are trained/scored)
            matrix_df = run_matrix_integration(logger, cache_paths)
            
            # C. SHAP (After Matrix, so rows exist for UPDATE)
            run_shap_steps(logger)

            # D. NBA (After Matrix; isolated so failure doesn't corrupt Matrix)
            try:
                run_nba_steps(logger, matrix_df)
            except Exception as nba_exc:
                logger.error(
                    f"NBA phase failed — Matrix results are safe: {nba_exc}"
                )
            
    except Exception as e:
        diagnostic = ErrorAdvisor.analyze(e)
        logger.critical(f"FATAL PIPELINE ERROR:\n{diagnostic}")
        sys.exit(1)
    finally:
        db.close_pool()
        logger.info("Pipeline Finished.")

if __name__ == "__main__":
    main()