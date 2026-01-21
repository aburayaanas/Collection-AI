WITH PTP AS (
    SELECT 
        CUST_INFO_ID,
        
        -- FEATURE 1: PTP Behaviour
        COUNT(*) AS TOTAL_PTP_COUNT,
        SUM(CASE WHEN PTP_STATUS = '2' THEN 1 ELSE 0 END) AS PTP_BROKEN_COUNT,
        SUM(CASE WHEN PTP_STATUS = '1' THEN 1 ELSE 0 END) AS PTP_KEPT_COUNT,

        ROUND(
            SUM(CASE WHEN PTP_STATUS = '2' THEN 1 ELSE 0 END) 
            / NULLIF(COUNT(*), 0),
            4
        ) AS PTP_BROKEN_RATIO,

        ROUND(
            SYSDATE - MAX(CASE WHEN PTP_STATUS = '2' THEN PTP_DATE END),
            0
        ) AS DAYS_SINCE_LAST_BROKEN_PTP

    FROM PIO_COLL.PIO_PTP_COLLECTOR
    GROUP BY CUST_INFO_ID
),

CONTACTS AS (
    SELECT
        CUST_INFO_ID,

        -----------------------------------------------------------------
        -- FEATURE 2: Reachability (RPC Rate)
        -----------------------------------------------------------------
        COUNT(*) AS TOTAL_ATTEMPTS_LIFETIME,

        SUM(CASE WHEN STATUS = 1 THEN 1 ELSE 0 END) AS SUCCESSFUL_CONTACTS,

        ROUND(
            SUM(CASE WHEN STATUS = 1 THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0),
            4
        ) AS RPC_RATE,


        -----------------------------------------------------------------
        -- FEATURE 3: “Ostrich Signal” (Recency)
        -----------------------------------------------------------------
        ROUND(
            SYSDATE - MAX(CASE WHEN STATUS = 1 THEN UPDATED_DATE END),
            0
        ) AS DAYS_SINCE_LAST_RPC,


        -----------------------------------------------------------------
        -- FEATURE 4: Intensity (Harassment Check)
        -----------------------------------------------------------------
        SUM(
            CASE 
                WHEN UPDATED_DATE > SYSDATE - 30 THEN 1 
                ELSE 0 
            END
        ) AS ATTEMPTS_LAST_30D,


        -----------------------------------------------------------------
        -- FEATURE 5: Channel Preference
        -----------------------------------------------------------------
        SUM(
            CASE 
                WHEN CONTACT_TYPE = 1 AND STATUS = 1 THEN 1 
                ELSE 0 
            END
        ) AS SMS_DELIVERED_COUNT,

        SUM(
            CASE 
                WHEN CONTACT_TYPE = 2 AND STATUS = 1 THEN 1 
                ELSE 0 
            END
        ) AS CALL_ANSWERED_COUNT

    FROM PIO_COLL.PIO_CONTACT_MANUAL_INFO
    GROUP BY CUST_INFO_ID
)

SELECT
    COALESCE(PTP.CUST_INFO_ID, CONTACTS.CUST_INFO_ID) AS CUST_INFO_ID,

    -----------------------------------------------------------------
    -- FEATURE 1
    -----------------------------------------------------------------
    PTP.TOTAL_PTP_COUNT,
    PTP.PTP_BROKEN_COUNT,
    PTP.PTP_KEPT_COUNT,
    PTP.PTP_BROKEN_RATIO,
    PTP.DAYS_SINCE_LAST_BROKEN_PTP,

    -----------------------------------------------------------------
    -- FEATURE 2 → 5
    -----------------------------------------------------------------
    CONTACTS.TOTAL_ATTEMPTS_LIFETIME,
    CONTACTS.SUCCESSFUL_CONTACTS,
    CONTACTS.RPC_RATE,
    CONTACTS.DAYS_SINCE_LAST_RPC,
    CONTACTS.ATTEMPTS_LAST_30D,
    CONTACTS.SMS_DELIVERED_COUNT,
    CONTACTS.CALL_ANSWERED_COUNT

FROM PTP
FULL OUTER JOIN CONTACTS
    ON PTP.CUST_INFO_ID = CONTACTS.CUST_INFO_ID

ORDER BY 1