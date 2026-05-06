{{
    config(
        materialized='table',
    )
}}

select
    status,
    count(*) as order_count,
    sum(amount) as total_amount
from {{ ref('silver_clean') }}
group by status
