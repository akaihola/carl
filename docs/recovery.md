# Secrets and recovery

The cloud container keeps running without the owner's computer: it holds its
own copies of its secrets. What the owner's computer holds is the ability to
maintain it. This page lists every secret, where each one lives, and how to
get working again. It follows drum-transcribe's `docs/recovery.md`.

Nothing secret goes into the page, the image or the repo. Locally, the
secrets live in gitignored `.secrets.*` files at the repo root.

## Every secret

| Secret | File | What it is |
| --- | --- | --- |
| `CARL_PASSWORDS` | `.secrets.carl.env` | One scrypt entry (`salt:hash`) per access pass, comma-separated, from `carl hash-password` |
| `TOKEN_SECRET` | `.secrets.carl.env` | Signs the access-pass cookies. **It can't be recreated:** a new one logs every browser out |
| The access passes themselves | `.secrets.access-passes.txt` | The passphrases, one per browser. Only their entries are on the server |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `.secrets.bucket.env` | The scoped bucket key: IAM application `carl-server`, object storage in the project AI app prototypes only. **Expires on 2027-09-27** |
| `SONIOX_API_KEY` | `.secrets.providers.env` | Speech-to-text (Soniox), from step 2. Prepaid credits, automatic top-up off |
| Scaleway API key (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, organisation and project ids) | the cloud environment's variables, or `~/.config/scw/config.yaml` | The owner's own key ("Carl prototype"): pushes images, updates the container, makes bucket keys. Expires on 2027-09-27 |
| Cloudflare (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`) | the cloud environment's variables, or `.secrets.cloudflare.env` | A token for the `vempai.men` zone: deploys the Worker, sets its routes and flips the `faktat` record |

The container's secret variables are `CARL_PASSWORDS`, `TOKEN_SECRET`,
`S3_ACCESS_KEY`, `S3_SECRET_KEY` and `SONIOX_API_KEY`. Each provider's key
joins them with the build step that first calls the provider, and gets a
row here: `OPENAI_API_KEY` (step 3), `PERPLEXITY_API_KEY` and
`OPENROUTER_API_KEY` (step 4). The provider keys are also in the cloud
environment's variables, where step 0 put them.

Why keep all of them, not just the irreplaceable one: Scaleway replaces the
container's whole set of secrets on every update, so changing any one of
them needs every other value at hand ([operations.md](operations.md#secrets)).

## For the owner

- **Copy every secret above into the password manager,** each file as its
  own secure note named by its path, together with the Scaleway and
  Cloudflare credentials. Also keep the logins for Scaleway, Cloudflare,
  GitHub and each provider there.
- **Put them in the cloud environment's variables too,** so that a Claude
  Code session can redeploy. A session's own files are gone when it ends.
- **Buy provider credits in small prepaid batches, with automatic top-up
  off,** so spending stops when a balance runs out. Until launch this is
  the spending limit.
- **At launch, set a hard monthly spend limit** in every provider dashboard
  that offers one. It is the backstop while the monthly budget waits for
  the next version.
- Before 2027-09-27, make a new bucket key and a new Scaleway API key, and
  update the container with `deploy/secrets.py`.

## Adding or revoking an access pass

- Add: `uv run carl hash-password` prints a new passphrase and its entry.
  Append the entry to `CARL_PASSWORDS` in `.secrets.carl.env`, keep the
  passphrase in `.secrets.access-passes.txt` and the password manager, and
  run `python3 deploy/secrets.py`.
- Revoke one browser: delete its entry and run `deploy/secrets.py`. That
  pass's cookies stop working at once.
- Revoke every browser: set a new `TOKEN_SECRET` (for example
  `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`) and run
  `deploy/secrets.py`.

## Recovery on a new computer

1. `git clone git@github.com:akaihola/carl.git`.
2. Restore the `.secrets.*` files from the password manager to the repo
   root, with `chmod 600`, and the Scaleway configuration to
   `~/.config/scw/config.yaml`.
3. Install [uv](https://docs.astral.sh/uv/) and run `uv sync`.
4. `python3 deploy/secrets.py --check` says whether every secret is back.

The container, the bucket, the domain and the Worker are all in the cloud
and unaffected: nothing there needs rebuilding.
