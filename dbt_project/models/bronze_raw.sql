{{
    config(
        materialized='table',
    )
}}

select
    id,
    amount,
    status
from {{ ref('orders') }}
