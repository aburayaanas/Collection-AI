# Business Logic Documentation

## Table and Column Definitions

### PIO_COLL.PIO_PTP_COLLECTOR
Stores customer promises (Promise-To-Pay) and their fulfillment status.
- **PTP_STATUS**: 
    - `1`: Kept
    - `2`: Broken

### PIO_COLL.PIO_CUSTOMERS_INFO
The central fact table for customer information.
- **ID**: Unique customer identifier used across all modules in the collection system. This is the primary key for identifying specific individuals.

### PIO_ACCOUNT_DEALS_INFO
The central fact table for customer accounts, containing all accounts associated with a customer.

### PIO_COLL.PIO_CUST_TASK_ALLOCATED
Contains customer task assignments.
- **ID**: Unique identifier for the allocation record (linked to the customer).
- **TASK_NO**: The task number representing the action to be performed (e.g., call, SMS, email). Tasks can change on a daily, weekly, or monthly basis. Once a task is completed, a new one may be assigned. 
    - *Note: It is assumed that a customer has only one active task at any given time.*
- **CUST_INFO_ID**: Customer information identifier (Usage details currently under investigation).

### PIO_TASK_ACTIONS
Records specific actions taken regarding a customer's assigned task.
- **ID**: Primary key for the action record.
- **CUST_TASK_ALLOC_ID**: Link to the task allocation record.
- **ACTION_SEQ**: Sequence number corresponding to a predefined action defined in the `PIO_ACTIVITY_DEF` lookup table.

### PIO_ACTIVITY_DEF
Lookup table for task and activity definitions.

---

## General Logic Rules

- **Joins**: Most tables in the collection module are joined using the `ID` (customer identifier).
- **Account Selection**: When multiple accounts exist, the "Most DPD" (Days Past Due) account is typically used.
- **Status Lookups**:
    - `PTP_STATUS` is mapped using `PIO_PTP_STATUS`.
    - Communication types are mapped using `PIO_COMMUNICATE_TYPE` (Note: This table exists in both the `PIO_COLL` schema and `BI_DWH`).

---

## Stakeholder Clarifications (Abu Hamzeh / Nadier / Meyad)

- **Customer Income**: This data is currently being constructed by the DB team and is not yet available.
- **Activity Tracking**: Actions such as calls, SMS, and emails are managed via the Activity/Actions logic.
- **Delinquency Without Promise**: For delinquent customers without an active promise, information (such as overdue amounts) is retrieved from the accounts table.
- **Transactions**: All transactions for delinquent customers are stored in the `TRANCT_COLL_INFO` table.
- **Configurations**: System configured values can be found in `PIO_PTP_PARAM_DEF`.
- **History Retention**: There is conflicting information regarding history; Nadier suggests the actions table is reset/deleted (no history), while Meyad suggests history is maintained.

---

## Table Dictionary & Classification
A dictionary exists for each module (e.g., Meyad for Collection). The classification logic is as follows:

- **Red Tables**: Core data imported directly from the bank as-is.
- **Blue Tables**: Internal tables created for system actions (buttons) on the interface.
- **Info Tables**: Classified as Red (Core).
- **Manual Tables**: Classified as Blue (Internal).
- **Collection Tables**: Contain the core logic of the collection system.

### Core Logic Tables:
- `PIO_ACCOUNT_DEALS`
- `PIO_CUSTOMER_DEALS`
