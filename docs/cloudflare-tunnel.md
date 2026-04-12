# Cloudflare Tunnel Setup — FlowList

This guide covers setting up a Cloudflare Tunnel to expose FlowList at
`taskflowlist.com` from a Windows home machine without opening inbound
firewall ports.

**Architecture:** Browser → Cloudflare Edge (HTTPS) → Tunnel → `cloudflared`
container → Caddy:80 (HTTP, internal Docker network) → backend / frontend.

---

## Prerequisites

- A Cloudflare account with `taskflowlist.com` already added as a zone
- Docker Desktop running on Windows
- The FlowList repo cloned and `.env` configured

---

## Part 1 — Install cloudflared on Windows (one-time setup)

You only need `cloudflared` locally to create the tunnel and get the token.
After that, the Docker container handles everything automatically.

### Option A — winget (recommended)

```powershell
winget install Cloudflare.cloudflared
```

### Option B — Direct download

1. Go to https://github.com/cloudflare/cloudflared/releases/latest
2. Download `cloudflared-windows-amd64.exe`
3. Rename to `cloudflared.exe` and move to a folder on your `PATH`
   (e.g. `C:\Windows\System32` or create `C:\tools` and add it to PATH)

Verify:

```powershell
cloudflared --version
```

---

## Part 2 — Authenticate cloudflared with your Cloudflare account

```powershell
cloudflared tunnel login
```

This opens your browser. Log in and authorize `cloudflared` for your account.
A credentials file is saved at `%USERPROFILE%\.cloudflared\cert.pem`.

---

## Part 3 — Create the tunnel

```powershell
cloudflared tunnel create flowlist
```

Output looks like:

```
Created tunnel flowlist with id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

A credentials JSON file is saved at:
`%USERPROFILE%\.cloudflared\<tunnel-id>.json`

---

## Part 4 — Get the tunnel connector token

The Docker-based setup uses a **connector token** instead of the credentials
file, so you don't need to mount any secrets into the container.

1. Go to [Cloudflare Zero Trust](https://one.cloudflare.com) → **Networks** → **Tunnels**
2. Find the `flowlist` tunnel → click **Manage**
3. Click **Configure** → **Overview** tab
4. Copy the token from the `cloudflared tunnel run --token <TOKEN>` command shown there

Add it to your `.env`:

```
CLOUDFLARE_TUNNEL_TOKEN=eyJh...your-token-here...
```

> **Security:** Never commit this token. It authenticates your cloudflared
> instance — treat it like a password.

---

## Part 5 — Configure DNS routing

Point `taskflowlist.com` at the tunnel:

```powershell
cloudflared tunnel route dns flowlist taskflowlist.com
cloudflared tunnel route dns flowlist www.taskflowlist.com
```

This creates CNAME records in your Cloudflare DNS zone:
`taskflowlist.com → <tunnel-id>.cfargotunnel.com`

Verify in the Cloudflare dashboard under **DNS** that the CNAME records exist
and are proxied (orange cloud icon).

---

## Part 6 — Configure tunnel public hostname in the dashboard

1. **Zero Trust** → **Networks** → **Tunnels** → `flowlist` → **Manage** → **Configure**
2. **Public Hostname** tab → **Add a public hostname**:
   - Subdomain: _(leave blank for root domain)_
   - Domain: `taskflowlist.com`
   - Path: _(leave blank)_
   - Service type: `HTTP`
   - URL: `caddy:80`
3. Repeat for `www.taskflowlist.com` → service: `http://caddy:80`
4. Save

This tells Cloudflare to forward all `taskflowlist.com` traffic through the
tunnel to the `caddy` Docker container on port 80.

---

## Part 7 — Set Cloudflare SSL/TLS mode

In the Cloudflare dashboard for `taskflowlist.com`:

**SSL/TLS** → **Overview** → set encryption mode to **Flexible**

This is correct because Cloudflare terminates TLS and forwards HTTP to your
origin (Caddy). The connection is fully encrypted to the browser; only the
Cloudflare → origin leg is HTTP (inside your home network / tunnel).

---

## Part 8 — Start the stack

The `cloudflared` service is already in `docker-compose.yml` and reads the
token from your `.env`. Start everything:

```powershell
cd C:\Projects\flowlist
docker compose up -d
```

Check the tunnel connected:

```powershell
docker compose logs cloudflared
```

You should see lines like:

```
INF Connection established connIndex=0 location=...
INF Connection established connIndex=1 location=...
```

---

## Part 9 — Verify end-to-end

1. Open `https://taskflowlist.com` in your browser
2. You should see the FlowList login page (or Cloudflare Access gate if
   Access is configured — see `docs/cloudflare-access.md`)
3. Sign in and confirm the app works normally
4. Check backend logs — requests should show the real client IP (not a
   Cloudflare datacenter IP):
   ```powershell
   docker compose logs backend --tail 30
   ```

---

## Keeping Cloudflare IP ranges up to date

`caddy/Caddyfile` lists Cloudflare's published IP ranges for `trusted_proxies`
so logs show real client IPs. Cloudflare rarely changes these, but you can
check the current list at:

- IPv4: https://www.cloudflare.com/ips-v4
- IPv6: https://www.cloudflare.com/ips-v6

If they change, update the Caddyfile and restart:

```powershell
docker compose restart caddy
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `cloudflared` logs show auth error | Re-run `cloudflared tunnel login` and update the token |
| Browser shows "Tunnel is not connected" | Confirm `docker compose ps cloudflared` is running |
| Site unreachable but tunnel is up | Check Caddy is healthy: `docker compose logs caddy` |
| OAuth redirect fails with `redirect_uri_mismatch` | Update `GOOGLE_*_REDIRECT_URI` in `.env` to `https://taskflowlist.com/api/auth/callback/*` |
| 526 SSL error from Cloudflare | Set SSL/TLS mode to **Flexible** in Cloudflare dashboard |
| Logs show Cloudflare IP instead of real client IP | Verify Caddy's `trusted_proxies` matches current CF IP ranges |
