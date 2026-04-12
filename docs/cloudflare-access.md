# Cloudflare Access Setup — FlowList

Cloudflare Access acts as an outer authentication layer in front of the entire
`taskflowlist.com` domain. Anyone who tries to reach the site must first pass
an email verification step before they ever hit the FlowList login screen.

**Two-layer auth model:**
1. **Cloudflare Access** — verifies the visitor's email via OTP (one-time PIN)
2. **FlowList Google OAuth** — signs the user into the app with their Google account

---

## Prerequisites

- Cloudflare Tunnel is working (`docs/cloudflare-tunnel.md`)
- You're signed in to [Cloudflare Zero Trust](https://one.cloudflare.com)

---

## Part 1 — Enable Cloudflare Zero Trust

If you haven't already:

1. Go to https://one.cloudflare.com
2. Choose your account and select a plan (the **Free** plan covers this use case)
3. Follow the onboarding steps to set up your Zero Trust organization

---

## Part 2 — Configure One-Time PIN as an identity provider

One-Time PIN lets users verify their email without connecting an external IdP
(no Okta, Azure AD, or Google Workspace required).

1. **Settings** → **Authentication** → **Login methods**
2. Click **Add new** → select **One-time PIN**
3. Save — no extra configuration needed

This provider sends a 6-digit PIN to the user's email address when they try
to access the app.

---

## Part 3 — Create an Access Application

1. **Access** → **Applications** → **Add an application**
2. Select **Self-hosted**
3. Configure the application:
   - **Application name:** `FlowList`
   - **Session duration:** `24 hours` (or your preference)
   - **Application domain:** `taskflowlist.com` (leave path blank to protect the entire domain)
4. Click **Next**

---

## Part 4 — Add an email whitelist policy

1. Policy name: `Invited Users`
2. **Action:** Allow
3. **Include rule:**
   - Selector: **Emails**
   - Value: add each allowed email address on a separate line, e.g.:
     ```
     you@yourcompany.com
     teammate@example.com
     friend@gmail.com
     ```
4. Click **Next** → **Add application**

Only the listed email addresses can pass the Access gate. Anyone else sees a
"You don't have access" page from Cloudflare — they never reach the FlowList
server.

---

## Part 5 — Bypass Access for the health check endpoint

The `/health` endpoint is used by Docker healthchecks and Cloudflare's own
tunnel health monitoring. It must be reachable without authentication.

1. Open the `FlowList` application in Access → **Edit**
2. Go to the **Policies** tab → **Add a policy**
3. Configure:
   - **Policy name:** `Health Check Bypass`
   - **Action:** Bypass
   - **Path:** `/health`
   - **Include rule:** Everyone (or leave empty)
4. Save

Repeat for `/api/healthz` if you want to expose the original health endpoint
too (optional).

---

## Part 6 — Test the Access gate

1. Open a private/incognito browser window
2. Navigate to `https://taskflowlist.com`
3. You should see the Cloudflare Access login page (not the FlowList app)
4. Enter an email address that is on the whitelist
5. Check that email for the OTP PIN
6. Enter the PIN → you're redirected to the FlowList login page
7. Complete Google OAuth login as normal

---

## Part 7 — Adding new users

When you invite a new user to FlowList:

1. Generate an invite link in FlowList Settings → Invites (admin only)
2. **Also** add their email to the Cloudflare Access whitelist:
   - **Access** → **Applications** → `FlowList` → **Edit**
   - **Policies** → `Invited Users` → **Edit**
   - Add their email to the **Emails** selector
   - Save
3. Share both:
   - The FlowList invite link (for account creation)
   - Instructions to expect a Cloudflare OTP email when first visiting the site

The user flow on first access:
1. Click the FlowList invite link → Cloudflare Access gate appears
2. Enter their email → receive OTP PIN → enter PIN → pass Access
3. FlowList invite page loads → click "Sign in with Google"
4. Complete Google OAuth → FlowList account is created (invite is consumed)

---

## Part 8 — Removing users

To revoke access for a user:

1. **FlowList Settings → Invites** → Revoke their invite (prevents new logins
   via the app's own auth layer, but doesn't affect Cloudflare Access)
2. **Cloudflare Access** → `FlowList` → **Policies** → `Invited Users` →
   remove their email from the list

Both steps together ensure the user can't reach the app at all.

---

## Notes

- The Cloudflare Access cookie (`CF_Authorization`) expires per the session
  duration set on the application. Users will need to re-verify via OTP after
  it expires.
- If a user has already passed Cloudflare Access but their FlowList session
  expired, they'll go directly to the FlowList Google OAuth screen (no OTP
  needed again until the Access session also expires).
- Cloudflare Access logs all authentication events in **Zero Trust** →
  **Logs** → **Access** — useful for auditing who accessed the app and when.
