### TABLES/CLOUMNS DEFINTION

PIO\_COLL.PIO\_PTP\_COLLECTOR: stores the promises of the customers and the status of the promises.
PTP\_STATUS = 1: Kept, 2: Broken



### general

* account to use: most dpd account
* PTO\_STATUS lookup -> PIO\_PTP\_STATUS
* communication type lookup -> PIO\_COMMUNICATE\_TYPE thier is two of this table one under the PIO\_COLL schema and the other under BI\_DWH



### abu hamzeh answers

* Customer income will be constructed by the db team we dont have this info yet.
* calls/sms/email etc -> Activity table its an actions job.
* if a customer is deliquent but doesnt has a promise then you can find this information in the accounts table. under over due amount column.
* all transactions for deliqunt customer under the colletion system is tranct\_coll\_info table.
* to know configred values use this table -> PIO\_PTP\_PARAM\_DEF




### tables dictonary excel
Their exist a table dictonary excel file for each modul in the company construted by indivals e.g. meyad for collection beacuse hes the one who built the collection system.

these files logic lies as the following:
red  tables = core data from bank as is 
blue tables = ones we created for actions(buttoms ) on oour interface
info tables =  red 
manual = blue
collection = core logic of the collection system


### 
most of the job basket logic lies under 2 tables:
PIO_account_deals
pio_customer_deals

### notes
nadier confirmed that any actions table get rest/deleted it doesn not hold history of actions
while meyad confirmed the opposite 