"""
Script to verify the join logic between PIO_CUST_TASK_ALLOCATED, PIO_TASK_ACTIONS, and PIO_ACTIVITY_DEF.
This script demonstrates how to correctly join these tables to understand the relationship 
between assigned tasks and performed actions.
"""

import logging
import sys
import os

# Add src to path if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.connection import db
from src.database.queries import execute_query

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_task_logic():
    """
    Executes a comprehensive join query to verify the relationship between
    customers, allocated tasks, and their corresponding actions.
    """
    
    # This query joins:
    # 1. PIO_CUST_TASK_ALLOCATED (CTA) - The master record of what task is assigned to which customer.
    # 2. PIO_TASK_ACTIONS (TA) - The specific actions/steps taken for that allocation.
    # 3. PIO_ACTIVITY_DEF (AD) - Twice! Once for the assigned task name and once for the action name.
    
    query = """
    SELECT 
        CTA.ID AS ALLOCATION_ID,
        CTA.CUST_INFO_ID,
        CTA.TASK_NO AS ASSIGNED_TASK_ID,
        AD_TASK.DESC_ENG AS ASSIGNED_TASK_NAME,
        TA.ACTION_SEQ,
        TA.ACTIVITY_ID AS PERFORMED_ACTIVITY_ID,
        AD_ACT.DESC_ENG AS PERFORMED_ACTIVITY_NAME
    FROM PIO_CUST_TASK_ALLOCATED CTA
    -- Join to get the definition of the TASK assigned to the customer
    LEFT JOIN PIO_ACTIVITY_DEF AD_TASK ON CTA.TASK_NO = AD_TASK.ID
    -- Join to get the ACTIONS recorded for this task allocation
    LEFT JOIN PIO_TASK_ACTIONS TA ON CTA.ID = TA.CUST_TASK_ALLOC_ID
    -- Join to get the definition of the specific ACTION/ACTIVITY performed
    LEFT JOIN PIO_ACTIVITY_DEF AD_ACT ON TA.ACTIVITY_ID = AD_ACT.ID
    WHERE ROWNUM <= 20
    """
    
    logger.info("Executing task verification query...")
    
    try:
        # Note: This requires the database pool to be initialized
        db.initialize_pool()
        
        cols, rows = execute_query(query)
        
        print("\n" + "="*100)
        print(f"{' | '.join(cols)}")
        print("-" * 100)
        for row in rows:
            print(f"{' | '.join(map(str, row))}")
        print("="*100 + "\n")
        
        logger.info(f"Successfully retrieved {len(rows)} records.")
        
    except Exception as e:
        logger.error(f"Failed to verify task logic: {e}")
        print(f"\n[ERROR] Query failed. Detailed SQL logic check:")
        print(f"Tables involved: PIO_CUST_TASK_ALLOCATED, PIO_TASK_ACTIONS, PIO_ACTIVITY_DEF")
        print(f"Potential Issue in your query: You were joining Actions directly to Definitions,")
        print(f"missing the Allocation context (who the customer is and what task was assigned).")
    finally:
        db.close_pool()

if __name__ == "__main__":
    verify_task_logic()
