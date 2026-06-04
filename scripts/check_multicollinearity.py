import polars as pl
import pandas as pd
import numpy as np
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.database.repository import CollectionRepository
from src.database.connection import db
from src.core.config import settings

def main():
    print("\n" + "="*60)
    print("MANUAL MULTICOLLINEARITY SCAN (Pearson Correlation > 0.85)")
    print("="*60)

    try:
        db.initialize_pool()
        repo = CollectionRepository()

        print("\n[1/2] Analyzing Willingness Features...")
        df_w = repo.get_willingness_training_data()
        print(f"  Data Rows: {df_w.height}")
        
        exclude_w = {"CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_WILLINGNESS", "IS_WILLING"}
        features_w = [c for c in df_w.columns if c not in exclude_w]
        print(f"  Features: {features_w}")
        
        if df_w.is_empty():
            print("  ⚠️ Willingness Data is EMPTY!")
            return

        corr_matrix_w = df_w.select(features_w).to_pandas().corr().abs()
        print("\n--- Willingness Correlation Matrix (First 5x5) ---")
        print(corr_matrix_w.iloc[:5, :5])
        
        upper_w = corr_matrix_w.where(np.triu(np.ones(corr_matrix_w.shape), k=1).astype(bool))
        
        redundant_w = []
        for col in upper_w.columns:
            high_corr = upper_w[col][upper_w[col] > 0.10]
            for other_col, val in high_corr.items():
                redundant_w.append((col, other_col, val))

        if redundant_w:
            for f1, f2, val in redundant_w:
                print(f"  🚨 REDUNDANT: {f1} <───> {f2} (Corr: {val:.4f})")
        else:
            print("  ✅ No high correlations in Willingness.")

        # Ability
        print("\n[2/2] Analyzing Ability Features...")
        df_a = repo.get_ability_training_data()
        exclude_a = {"CUST_INFO_ID", "SNAPSHOT_DATE", "TARGET_ABILITY", "IS_STABLE"}
        features_a = [c for c in df_a.columns if c not in exclude_a]
        
        corr_matrix_a = df_a.select(features_a).to_pandas().corr().abs()
        upper_a = corr_matrix_a.where(np.triu(np.ones(corr_matrix_a.shape), k=1).astype(bool))
        
        redundant_a = []
        for col in upper_a.columns:
            high_corr = upper_a[col][upper_a[col] > 0.70]
            for other_col, val in high_corr.items():
                redundant_a.append((col, other_col, val))

        if redundant_a:
            for f1, f2, val in redundant_a:
                print(f"  🚨 REDUNDANT: {f1} <───> {f2} (Corr: {val:.4f})")
        else:
            print("  ✅ No high correlations in Ability.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close_pool()
        print("\n" + "="*60)

if __name__ == "__main__":
    main()
