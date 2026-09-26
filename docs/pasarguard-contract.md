# PasarGuard API contract

Verified against the official `PasarGuard/panel` source at commit
`b56ffe369f542152c52c69733205baeaf3f6e4cd`.

## Authentication

Protected endpoints accept either:

- `Authorization: Bearer <token>`
- `X-Api-Key: pg_key_<uuid-v4>`
- `Authorization: ApiKey pg_key_<uuid-v4>`

PANELPRIMEPASAR defaults to the API-key path because a dedicated key can be granted
only the permissions the sales bot needs.

## Required bot permissions

The intended least-privilege credential needs these permissions:

- `admins.create` — create customer reseller/admin accounts.
- `admins.read` or `admins.read_simple` — reconcile created accounts.
- `admins.update` — quota increases, status changes, renewals, and credential rotation.
- `admin_roles.read_simple` — resolve the configured reseller role safely.

The bot does not need node, core, host, group, template, settings, or user-management
permissions for provisioning reseller/admin accounts.

## Role discovery

Simple role discovery:

`GET /api/admin-roles/simple`

Response shape:

```json
{
  "roles": [
    {"id": 3, "name": "operator", "is_owner": false}
  ],
  "total": 1
}
```

The production bot must resolve the configured reseller role from the live panel.
It must reject any role where `is_owner=true`.

## Admin creation

`POST /api/admin`

The official `AdminCreate` model inherits `AdminModify`, therefore `data_limit`
is valid during creation.

Minimal provisioning payload:

```json
{
  "username": "customer_4821",
  "password": "<generated-secret>",
  "role_id": 3,
  "data_limit": 1000000000000
}
```

The actual production role ID is not hard-coded. It is resolved from the live
PasarGuard role list and validated before provisioning.

`data_limit` is always sent in bytes. A plan entered as `500` GB is therefore
sent as `500000000000`. A value of `0` is sent unchanged and means unlimited
traffic. PasarGuard does not receive or enforce a day-based expiry.

## Admin modification

`PUT /api/admin/by-id/{admin_id}`

Supported fields relevant to the sales bot include:

- `password`
- `status`
- `data_limit`
- `role_id`
- `note`

This endpoint will be used for quota changes, renewals, disabling/enabling accounts,
and credential rotation.
