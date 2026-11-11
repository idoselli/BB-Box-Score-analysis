# Enable public NIKA sign-in

Status: OAuth routes, PKCE, encrypted server-side sessions and refresh-token locking
are implemented. Production activation is blocked by account configuration.
The connected Vercel app returned HTTP 403 when creating production variables
and listing integrations. No authenticated Vercel CLI credentials are available.
No production configuration was changed by these failed requests.

## 1. Register NIKA in BuzzerBeater

In your game account, go to **Settings → API & third-party apps → My applications → Register**.
If NIKA is already registered, use that application instead of creating a duplicate.

| Field | Value |
| --- | --- |
| Name | NIKA — BuzzerBeater Box Score Analysis |
| Description | Analyze completed matches, player statistics, shooting profiles and national squads using each manager's authorized BuzzerBeater data. Optional club training, national staff and market access are requested separately. |
| Website | https://box-score-analysis.vercel.app/ |
| Kind | Confidential |
| Redirect URI (exact) | https://box-score-analysis.vercel.app/beta/oauth/callback |

Save the client ID (`bbc_…`) and the once-shown client secret (`bbcs_…`) directly
in Vercel's environment settings below. Do not paste the secret into chat, issues
or source files. The personal `bbpat_…` token is not an OAuth client credential.

New BuzzerBeater apps are development-only and only their owner can sign in.
**Request BuzzerBeater staff review/approval to allow other managers.** Merely
configuring OAuth or deploying the site does not remove this restriction.

## 2. Provision encrypted session storage

In the existing Vercel project's Storage / Marketplace, connect a Redis database
that supports the Redis protocol over TLS (for example Upstash Redis). An HTTPS
REST URL alone does not work with this application's Python Redis client.
Choose the plan explicitly; check its price before provisioning. Use an existing
suitable Redis database when available. Set its TLS connection URL (`rediss://…`)
as `BB_V1_REDIS_URL`. It must be shared across serverless instances for session
storage and distributed refresh-token locks.

## 3. Set Production environment variables

Open https://vercel.com/idosellis-projects/box-score-analysis/settings/environment-variables

| Variable | Value | Secret? |
| --- | --- | --- |
| BB_V1_CLIENT_ID | Registered BuzzerBeater application ID | No |
| BB_V1_CLIENT_SECRET | Registered application's client secret | Yes |
| BB_V1_REDIRECT_URI | https://box-score-analysis.vercel.app/beta/oauth/callback | No |
| BB_V1_REDIS_URL | TLS Redis connection URL | Yes |
| BB_V1_TOKEN_ENCRYPTION_KEY | A generated Fernet key | Yes |

Generate the encryption key **on your own computer**, then save it directly as a
Vercel Production Secret. With Python and cryptography installed:

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep the key stable; replacing it invalidates existing encrypted sessions. Do not
set the localhost-only `BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN` to true in production.
Do not expose any of these values through browser/public-prefixed variables.
If existing API/OAuth URL overrides still use sb1, replace them with:

- `BB_V1_API_BASE=https://next-api.buzzerbeater.com/v1`
- `BB_V1_AUTHORIZE_URL=https://play.buzzerbeater.com/oauth/authorize`

Production secrets should stay in Vercel. If testing separately with development
credentials in a secure shell, `python -m beta_v1.check_auth` validates required
settings, the production callback, Fernet format and an encrypted Redis write/read.
It prints no credentials and does not prove OAuth application approval.

## 4. Redeploy and verify

Redeploy the current production commit so it receives the new settings. Visit
https://box-score-analysis.vercel.app/beta/ and click **Sign in with BuzzerBeater**.
Verify the consent page names NIKA and initially asks only for Public access.
After consent, verify the callback returns signed in, a live match report works,
and Disconnect removes access. Test a second manager after staff approval.
Optional scope upgrades are available as **Connect club training**, **Connect
national squad**, and **Connect market** on the home page. Personal API token
entry is restricted to owner localhost previews.
