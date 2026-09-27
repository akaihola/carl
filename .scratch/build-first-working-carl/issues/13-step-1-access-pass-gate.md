# Step 1: Access-pass gate

Type: task
Status: open
Blocked by: 12

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md#access-passes) is
the source of truth. drum-transcribe's `gate.py` and the Throttling part of
its `docs/webapp.md` are the model.

## What to build

- scrypt entries (`salt:hash`) in `CARL_PASSWORDS`, comma-separated, one per
  access pass;
- a `carl hash-password` command that makes an entry, and generates a
  four-word passphrase (about 72 bits) when given none;
- the stateless cookie `HMAC(TOKEN_SECRET, salt of the entry)`, HttpOnly,
  Secure, SameSite=Lax, valid for 1 year;
- a wrong pass answered after a 1 s wait, and no lockout;
- everything behind the gate except the health endpoint and the loading page
  (which lives in the Worker), the WebSocket upgrade included. The pass form
  itself is open, since it is the gate.
- The server refuses to start without `CARL_PASSWORDS` and `TOKEN_SECRET`,
  so a missing secret can't leave Carl open.

## Done when

- [ ] pytest covers the entries, the passphrase, the cookie, the 1 s wait,
      revoking by deleting an entry or rotating `TOKEN_SECRET`, and the gate
      on the page, the API and the WebSocket upgrade.
