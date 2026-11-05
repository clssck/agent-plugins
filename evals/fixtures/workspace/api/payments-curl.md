# Payments API calls I run by hand

    curl -H "Authorization: Bearer $TOKEN" https://payments.internal/v1/charges?limit=20
    curl -X POST -H "Authorization: Bearer $TOKEN" https://payments.internal/v1/charges/$ID/capture
    curl -X POST -H "Authorization: Bearer $TOKEN" https://payments.internal/v1/refunds -d charge=$ID
