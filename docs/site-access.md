# Home page and password access

The application root `/` opens the new NIKA home at `/beta/`. Match Analysis is
the primary feature, with a prominent hero and entry button. The original tool
is still available at `/legacy/`.

To enable the shared site password, add this Vercel environment variable:

| Setting | Enter |
| --- | --- |
| Name | `NIKA_SITE_PASSWORD` |
| Value | A strong site password of your choice; share it only with intended visitors |
| Type | Secret |
| Environment | Production (and Preview too if previews should be locked) |

Redeploy after saving it. No additional signing-key environment variable is
needed. The site's access cookie is signed using a key derived from this
password. Keep the password server-side; do not use a public-prefixed variable,
commit it, or paste it into a support issue.

When the variable is absent or empty, the gate is disabled. This lets the
existing deployment continue to work until the owner configures the password.
Setting it and redeploying enables the lock across old and new routes, API
responses, exports and OAuth entry/callback routes. Static assets remain public
so the lock screen can render its blurred, inert preview. The preview contains
no account or report data, and page/API handlers do not run before unlock.

Visitors enter this shared password first, then use their own BuzzerBeater OAuth
connection as before. Successful access lasts 12 hours in that browser via a
signed HttpOnly cookie (Secure on Vercel, SameSite=Lax). Gate forms use a CSRF
cookie/token. Protected responses use private/no-store caching. Changing the
password and redeploying invalidates existing gate cookies.

The site password is separate from the BuzzerBeater client secret, token
storage encryption key, personal API tokens and the legacy analyzer password.
