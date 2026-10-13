# Payments API Specification

Version 1.2.0 — internal draft.

## Overview

This API allows clients to create, retrieve, and refund payments. All requests must be authenticated.

## Authentication

Supports **OAuth2** with the `client_credentials` grant. Tokens expire after 3600 seconds.

> Note: API keys are legacy and will be removed in v2.0.

### Required Headers

- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- `Idempotency-Key` (optional, recommended for `POST /payments`)

## Rate Limits

| Tier | Requests/min | Burst |
|------|--------------|-------|
| Free | 100 | 150 |
| Pro | 1000 | 1500 |
| Enterprise | 10000 | 12000 |

Exceeding the limit returns a `429 Too Many Requests` response.

## Endpoints

### Create a Payment

```http
POST /v1/payments
```

Request body:

```json
{
  "amount": 5000,
  "currency": "usd",
  "customer_id": "cus_123"
}
```

Response:

```json
{
  "id": "pay_abc",
  "status": "pending"
}
```

### List Payments

```http
GET /v1/payments?limit=20&starting_after=pay_abc
```

Returns a paginated list. See [pagination guide](https://example.com/docs/pagination) for details.

### Refund a Payment

1. Verify the payment is in `succeeded` state.
2. Submit a refund request:
   - Full refund: omit `amount`.
   - Partial refund: include `amount` in cents.
3. Poll `GET /v1/refunds/{id}` until `status` is `succeeded` or `failed`.

```http
POST /v1/refunds
```

## Error Codes

- `400` — malformed request body
- `401` — missing or invalid token
- `404` — resource not found
- `429` — rate limit exceeded
- `500` — internal server error

## Changelog

- 1.2.0 — added Idempotency-Key support
- 1.1.0 — added refund partial-amount support
- 1.0.0 — initial release
