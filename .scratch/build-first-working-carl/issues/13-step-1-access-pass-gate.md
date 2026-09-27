# Step 1: Access-pass gate

Type: task
Status: resolved
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

- [x] pytest covers the entries, the passphrase, the cookie, the 1 s wait,
      revoking by deleting an entry or rotating `TOKEN_SECRET`, and the gate
      on the page, the API and the WebSocket upgrade.

## Answer

Built on 2026-09-27 in `src/carl/gate.py`, from drum-transcribe's
`gate.py`.

- Entries are `salt:hash` with scrypt (n 2^14, r 8, p 1) and a 16-hex-digit
  salt. `carl hash-password [pass]` prints the entry, and generates a
  four-word passphrase of 3 syllables a word (65^12, about 72 bits) when
  given none. A pass must be at least 12 characters.
- The cookie `carl_pass` is `HMAC-SHA256(TOKEN_SECRET, salt)`, HttpOnly,
  Secure, SameSite=Lax, Path=/, Max-Age one year. `TOKEN_SECRET` must be at
  least 32 characters.
- The pass form is served in place of any page without a valid cookie
  (401), and posts to `/api/unlock`. A correct pass sets the cookie and
  redirects to `/`. A wrong one is answered after 1 s, with no lockout, and
  wrong passes don't wait behind each other. The scrypt check runs off the
  event loop, so it never stalls a live WebSocket.
- Open without the cookie: only `/api/health` and `/api/unlock`. Everything
  else answers 401, the WebSocket upgrade included.
- `carl serve` refuses to start without `CARL_PASSWORDS` and
  `TOKEN_SECRET`, or with an entry that isn't `salt:hash`.
- Checked in Chromium: a wrong pass was answered after 1.1–1.3 s, and the
  right one opened the page.
