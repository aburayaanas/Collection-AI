###general questions

- does the collection system logic lies behind account number or cus_num if account is their a specifc condition on it like most active account for this specifc customer? why beacuse a customer may have more than account which one should i pick? and how on which criteria?

TABLE: PIO_COLL.PIO_PTP_COLLECTOR
- PTP_STATUS: is thier a lookup table for this column? what does each value mean? and what is their scope?
- PTP_DATE, DAY_DATE: is PTP_DATE - DAY_DATE = number of days between the promise date and the day the customer made the promise? in no how can i achive this condition?

TABLE: PIO_COLL.PIO_CONTACT_MANUAL_INFO
- COMMUNICATION_TYPE: is thier a lookup table for this column? what does each value mean?
- UPDATED_DATE: what does this column represent?
- MODULE_TYPE: what does this column represent?

TABLE: PIO_INWARD_CENTRAL_TRANSFERS
- how is this table structured? is it a granular table or aggregated? (1 record per transaction or aggregated?)
- why cus_num is null, should i join it with PIO_CUSTOMERS table to get the cus_num?
- if i want the customer whole cashflow for a ceratin period of time does this table contain all the information i need?


Questions:
1. how to knwo is a cusotmer transactions is being declined due to insufficient funds or any other reason?
(this will help me filling the SPENDING_STATS CTE in ability sql query).
2.



###=================================================================================
### ask abuhamzeh/ nadier.
- account to use: most dpd account

- PIO_CONTACT_MANUAL_INFO thier is no date column on when did we called him

- payment methods collection: how to know if a customer has paid his loan without doing a promiss, is their a table that stores the payment methods of the customers? and value and if its full or not?

- is using PIO_COLL.PIO_ACCOUNT_DEALS_INFO with the willingness query is correct joined with the PTP tables.