""" files have to be named:
1. flags.csv with columns:
    - flag_id
    - type
    - severity
    - txn_count
    - amount_usd
    - owner
    - opened_date
    - age_days
    - status
2. coverage_daily.csv with columns:
    - date
    - core_volume
    - monitored_volume
3. entity_check.csv with columns:
    - booking_entity_id
    - booking_entity_name
    - authorised

* in flags.csv, severity must be "Red" "Amber" "Green"
* in flags.csv, status must be "Open" "Escalated" "Resolved"
* in flags.csv, age_days must be a number
* in entity_check.csv, authorised must be "True" "False"

* once reconcile works, Batrisyiya to remove fallback_from_raw() and simplify load
"""

