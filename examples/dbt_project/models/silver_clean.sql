{{
    config(
        materialized='table',
    )
}}

select
    id,
    amount,
    status
from {{ ref('bronze_raw') }}
where amount > 0
