# Checkout outage notes (raw)

- 14:02 alerts: checkout 5xx > 40%
- 14:10 on-call paged, rolled back web deploy, no change
- 14:55 found payments API connection pool exhausted after config change lowering max connections to 5
- 15:40 config reverted, error rate back to normal
- 16:05 incident closed
