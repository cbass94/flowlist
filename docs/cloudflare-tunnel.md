# Cloudflare Tunnel Setup

FlowList is designed to run on a home server behind a Cloudflare Tunnel — no port forwarding required.

## Prerequisites

- A domain managed by Cloudflare
- `cloudflared` installed on the host machine
- FlowList stack running locally (`docker compose up -d`)

## Steps

### 1. Authenticate cloudflared

```bash
cloudflared tunnel login
```

This opens a browser and stores credentials at `~/.cloudflared/cert.pem`.

### 2. Create a named tunnel

```bash
cloudflared tunnel create flowlist
```

Note the tunnel ID printed (e.g. `abc123...`). It's also stored in `~/.cloudflared/<tunnel-id>.json`.

### 3. Create DNS record

```bash
cloudflared tunnel route dns flowlist tasks.yourdomain.com
```

Replace `tasks.yourdomain.com` with your desired hostname.

### 4. Configure the tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: flowlist
credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: tasks.yourdomain.com
    service: http://localhost:80
  - service: http_status:404
```

This routes HTTPS traffic on your domain to Caddy on port 80. Caddy handles the internal routing between frontend and backend.

### 5. Run the tunnel

**Ad-hoc (for testing):**
```bash
cloudflared tunnel run flowlist
```

**As a systemd service (recommended):**
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

### 6. Update Caddyfile for production

Switch the Caddyfile from `:80` to your domain to enable Caddy auto-TLS (optional — Cloudflare already handles TLS, but Caddy TLS adds defense in depth):

```
tasks.yourdomain.com {
    # ...existing config...
}
```

Or keep `:80` and let Cloudflare terminate TLS at the edge (simpler).

## Security notes

- Cloudflare Tunnel never exposes any ports to the public internet
- The tunnel only allows HTTPS traffic via Cloudflare's network
- Cloudflare's WAF and DDoS protection apply automatically
- Set `Access` policies in Cloudflare Zero Trust if you want an extra auth layer

## Updating

When the FlowList stack is updated, just `docker compose pull && docker compose up -d`. The tunnel continues running automatically.
