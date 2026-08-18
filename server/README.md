# d2diag community contribution endpoint

A tiny, dependency-free service (`server/endpoint.py`, stdlib `http.server` +
`sqlite3`) that receives **anonymous, PII-free** contributions from the diagnostic
app and shows a maintainer admin view. Runs on the maintainer's own host behind
**Caddy** at `https://www.driftwoodstudios.se/d2diag`.

## What it stores (and what it never does)

- **Never PII.** Payloads are whitelisted to protocol/reading fields; any known
  personal key (`vin`, `registration`, `ip`, `gps`, `email`, …) makes the request
  fail with 400. The **client IP is never recorded**.
- **Anonymous install ID** (a random UUID the app generates when the user opts in)
  → lets us count *unique installs* and separate *registered* from *contributing*,
  without any identity.
- Optional **coarse vehicle descriptor** only: `model / year / engine / market`
  (not personal data).

## Routes

| Method | Path (as the service sees it) | Body / result |
|---|---|---|
| POST | `/register` | `{install_id, tool_version, vehicle?}` → `{ok}` (opt-in) |
| POST | `/contribute` | reading + our mapping + structured answer → `{ok}` |
| GET | `/admin` | HTML stats (protect with Caddy basic_auth) |
| GET | `/health` | `{ok:true}` |

Public URLs are prefixed with `/d2diag` (Caddy strips it — see below).

## Run

```bash
python3 server/endpoint.py --db data/d2diag.sqlite --host 127.0.0.1 --port 8090
```

Bind to `127.0.0.1` so only Caddy can reach it. For production, run it as a systemd
service (or in tmux). SQLite needs no server.

## Caddy

Add to the `www.driftwoodstudios.se` site block. `handle_path` strips the `/d2diag`
prefix, so the service sees `/register`, `/contribute`, `/admin`:

```caddy
www.driftwoodstudios.se {
    # ... your existing site ...

    # protect the admin view (generate the hash with: caddy hash-password)
    @d2admin path /d2diag/admin*
    basic_auth @d2admin {
        maggie JDJhJDE0J...your-bcrypt-hash...
    }

    # d2diag community endpoint
    handle_path /d2diag/* {
        reverse_proxy 127.0.0.1:8090
    }
}
```

The app then POSTs to `https://www.driftwoodstudios.se/d2diag/contribute`.

**Admin auth (defense in depth):** basic_auth in Caddy is enough. Optionally also set
`ADMIN_TOKEN=<secret>` in the service's environment — then `/admin` additionally
requires `?token=<secret>` (or an `X-Admin-Token` header).

## Data model (SQLite)

- `installs(install_id PK, first_seen, last_seen, tool_version, vehicle)`
- `contributions(id, install_id, received_at, tool_version, vehicle, module, lid,
  offset, kind, raw, our_name, our_value, our_confidence, answer_type, answer_value,
  answer_unit)`

## Maintainer loop

1. Review incoming contributions at `/d2diag/admin` (or query the SQLite directly).
2. When several installs agree on a candidate field, promote it
   `kandidat → belagt` in the app's `src/d2diag/signals/*.json`.
3. Ship it in the next release. Nothing is auto-published — you stay in control of
   what becomes "Verified".

## Privacy note (for the consent screen)

> Sharing is opt-in. We store an anonymous ID and the protocol readings you choose
> to share — never your VIN, registration, location or any personal data, and we do
> not record your IP address.
