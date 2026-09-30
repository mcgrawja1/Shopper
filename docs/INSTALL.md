# Installing Shopper on a Linux server

These steps assume a Linux server (Debian/Ubuntu shown; Fedora/RHEL notes
included) that you can SSH into with `sudo` rights. Shopper runs as a single
Docker container and stores all of its data in one Docker volume.

---

## 1. Install Docker Engine and the Compose plugin

Skip this section if `docker compose version` already prints a version.

Paste the commands **one line at a time**. Some terminals and SSH clients join
multi-line pastes into a single line, which makes `apt-get` see later commands
as file names (`E: Unsupported file /etc/apt/keyrings`).

If `sudo apt-get update` already lists `download.docker.com` among its
sources, Docker's repository is configured and you only need the install
line: `sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin`.

**Debian / Ubuntu**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

**Fedora / RHEL / Rocky**

```bash
sudo dnf -y install dnf-plugins-core git
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

**Both:** start Docker and let your user run it without `sudo`.

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker "$USER"
newgrp docker            # or log out and back in
docker compose version   # should print "Docker Compose version v2.x"
```

---

## 2. Get the code

Pick a directory for apps (the examples use `/opt/shopper`).

```bash
sudo mkdir -p /opt/shopper
sudo chown "$USER":"$USER" /opt/shopper
git clone https://github.com/mcgrawja1/Shopper.git /opt/shopper
cd /opt/shopper
git checkout claude/shopper-phase1     # until this branch is merged to main
```

---

## 3. Configure

```bash
cp .env.example .env
nano .env
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `SHOPPER_PORT` | `8080` | Port on the server that the web UI listens on. Change it if 8080 is taken. |
| `KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET` | empty | Optional. Enables live Kroger-family prices (see section 8). Leave empty to start; everything else works without them. |

`.env` is ignored by git, so your keys never get committed.

---

## 4. Build and start

```bash
cd /opt/shopper
docker compose up -d --build
```

The first build downloads the `python:3.12-slim` image and installs four
Python packages; expect one to three minutes. Subsequent starts take seconds.

Check that it is running and healthy:

```bash
docker compose ps
# NAME      IMAGE             STATUS
# shopper   shopper-shopper   Up 30 seconds (healthy)

curl http://localhost:8080/api/health
# {"ok":true,"version":"0.2.0"}
```

Open `http://<server-ip>:8080` from any device on your network.

If the server has a firewall:

```bash
sudo ufw allow 8080/tcp                      # Ubuntu ufw
sudo firewall-cmd --permanent --add-port=8080/tcp && sudo firewall-cmd --reload   # firewalld
```

---

## 5. First-run setup in the browser

1. **Stores** tab: untick the sample Pensacola locations you don't use, tick
   the ones you do, or use **+ Add a location** to enter your own store's name
   and address under the right chain. Only ticked locations are searched.
2. **Settings** tab: set your home ZIP code, default sort and re-price
   strategy.
3. **Home** tab: search, add items, and click **Save** to store your first list.

---

## 6. Day-to-day operations

All commands run from `/opt/shopper`.

| Task | Command |
| --- | --- |
| View logs | `docker compose logs -f` |
| Stop | `docker compose down` (data is kept) |
| Start again | `docker compose up -d` |
| Restart after editing `.env` | `docker compose up -d` (Compose re-reads `.env`) |
| Update to the latest code | `git pull && docker compose up -d --build` |
| Check health | `docker compose ps` or `curl localhost:8080/api/health` |

The container has `restart: unless-stopped`, so it comes back automatically
after a reboot or a Docker restart.

---

## 7. Backing up and restoring your data

Everything (stores, favorites, lists, settings) is one SQLite file inside the
`shopper-data` volume.

**Backup**

```bash
mkdir -p ~/shopper-backups
docker compose exec shopper sh -c 'cd /data && tar czf - shopper.db*' \
  > ~/shopper-backups/shopper-$(date +%F).tar.gz
```

**Restore**

```bash
docker compose down
docker run --rm -v shopper_shopper-data:/data -v ~/shopper-backups:/backup alpine \
  sh -c 'cd /data && rm -f shopper.db* && tar xzf /backup/shopper-2026-09-30.tar.gz'
docker compose up -d
```

(The volume is named `shopper_shopper-data` because Compose prefixes it with
the project folder name. Confirm with `docker volume ls`.)

A nightly cron entry for the backup:

```bash
crontab -e
# add:
0 3 * * * cd /opt/shopper && docker compose exec -T shopper sh -c 'cd /data && tar czf - shopper.db*' > $HOME/shopper-backups/shopper-$(date +\%F).tar.gz
```

---

## 8. Optional: live Kroger-family prices

Kroger, Fred Meyer, Ralphs, King Soopers, Fry's, Harris Teeter, Smith's, QFC,
Dillons and Mariano's share one free public API.

1. Go to <https://developer.kroger.com>, sign in with (or create) a Kroger
   account, and click **Create App** (any name; environment **Production**).
2. Enable the **Products** and **Locations** APIs. Copy the **Client ID** and
   **Client Secret**.
3. Add them to `/opt/shopper/.env`:
   ```
   KROGER_CLIENT_ID=your-client-id
   KROGER_CLIENT_SECRET=your-client-secret
   ```
4. Restart: `docker compose up -d`.
5. In the app, **Stores → Kroger → Find nearby**: enter your ZIP and tick the
   real stores that appear. Searches at those stores now return live prices,
   promos and aisle locations.

**Settings → Live price providers** shows "Connected" when the keys are picked
up.

---

## 9. Optional: HTTPS and a hostname with a reverse proxy

If you already run Nginx Proxy Manager, Caddy, Traefik or similar, point it at
`http://<server-ip>:8080`. Shopper serves everything from `/` and needs no
special headers or WebSockets.

Minimal Caddy example (`/etc/caddy/Caddyfile`):

```
shopper.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

If you put a proxy in front, you can stop exposing the port on all
interfaces by changing the `ports:` line in `docker-compose.yml` to
`"127.0.0.1:${SHOPPER_PORT:-8080}:8000"`.

Shopper has no login of its own. Keep it on your LAN or VPN, or add
authentication at the proxy (basic auth, Authelia, Cloudflare Access) before
exposing it to the internet.

---

## 10. Troubleshooting

| Symptom | What to check |
| --- | --- |
| `permission denied while trying to connect to the Docker daemon` | You didn't re-login after `usermod -aG docker`. Run `newgrp docker` or log out and back in. |
| `port is already allocated` | Something else uses 8080. Set `SHOPPER_PORT=8090` in `.env` and run `docker compose up -d`. |
| Page loads but says "Could not reach the Shopper API" | `docker compose logs shopper` for a Python traceback; `docker compose ps` should show `healthy`. |
| Search returns "No store locations selected" | Tick at least one location on the Stores tab. |
| Kroger shows "sample catalog prices" banner | Keys aren't set or the container wasn't restarted after editing `.env`. Check Settings → Live price providers. |
| `Find nearby` fails with 401/403 | Client ID/secret wrong, or the app on developer.kroger.com doesn't have the Products and Locations APIs enabled. |
| Want to start over with a clean database | `docker compose down -v` (deletes the volume and all lists) then `docker compose up -d`. |
| Sample products or stores changed after an update | Seed data reloads when `SEED_VERSION` changes; your selections, custom locations, lists and favorites are preserved. |

---

## 11. Running without Docker (fallback)

If you would rather run it directly:

```bash
sudo apt-get install -y python3 python3-venv
cd /opt/shopper
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
DATA_DIR=/opt/shopper/data uvicorn app.main:app --host 0.0.0.0 --port 8080
```

A systemd unit (`/etc/systemd/system/shopper.service`) to keep it running:

```
[Unit]
Description=Shopper
After=network.target

[Service]
User=youruser
WorkingDirectory=/opt/shopper/backend
Environment=DATA_DIR=/opt/shopper/data
EnvironmentFile=-/opt/shopper/.env
ExecStart=/opt/shopper/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now shopper
```
