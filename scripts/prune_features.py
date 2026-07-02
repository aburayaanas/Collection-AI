import polars as pl
import pandas as pd
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.database.repository import CollectionRepository
from src.database.connection import db
from src.core.config import settings
from src.core.logger import setup_logging

def run_pruning_analysis():
    setup_logging()
    db.initialize_pool()
    repo = CollectionRepository()
    
    print("\n" + "="*50)
    print("XAI MULTICOLLINEARITY PRUNING PASS")
    print("="*50)
    
    # --- Willingness Analysis ---
    print("\n[1/2] Analyzing Willingness Training Data...")
    df_w = repo.get_willingness_training_data()
    features_w = [c for c in df_w.columns if c not in ["CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_WILLINGNESS"]]
    df_w_numeric = df_w.select(features_w)
    
    corr_matrix_w = df_w_numeric.to_pandas().corr()
    
    found_w = False
    for i in range(len(corr_matrix_w.columns)):
        for j in range(i + 1, len(corr_matrix_w.columns)):
            val = corr_matrix_w.iloc[i, j]
            if abs(val) > 0.85:
                print(f"  🚨 HIGH CORR: {corr_matrix_w.columns[i]} <-> {corr_matrix_w.columns[j]} (Pearson: {val:.4f})")
                found_w = True
                
    if not found_w:
        print("  ✅ No redundant features found in Willingness set.")

    # --- Ability Analysis ---
    print("\n[2/2] Analyzing Ability Training Data...")
    df_a = repo.get_ability_training_data()
    features_a = [c for c in df_a.columns if c not in ["CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_ABILITY"]]
    df_a_numeric = df_a.select(features_a)
    
    corr_matrix_a = df_a_numeric.to_pandas().corr()
    
    found_a = False
    for i in range(len(corr_matrix_a.columns)):
        for j in range(i + 1, len(corr_matrix_a.columns)):
            val = corr_matrix_a.iloc[i, j]
            if abs(val) > 0.85:
                print(f"  🚨 HIGH CORR: {corr_matrix_a.columns[i]} <-> {corr_matrix_a.columns[j]} (Pearson: {val:.4f})")
                found_a = True

    if not found_a:
        print("  ✅ No redundant features found in Ability set.")

    print("\n" + "="*50)
    print("ANALYSIS COMPLETE")
    print("="*50)
    
    db.close_pool()

if __name__ == "__main__":
    run_pruning_analysis()
