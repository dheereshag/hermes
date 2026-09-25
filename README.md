# Hermes — Weighment & ANPR Integration System

Industrial weighing bridge integration controller bridging scale serial indicators, multi-camera capture, Argus ANPR, emergency Wi-Fi diagnostics, and Gluvok Cloud sync.

---

## ⚡ Prerequisites

- **Python ≥ 3.14** (managed via `.python-version` / `pyproject.toml`)
- **[uv](https://docs.astral.sh/uv/)** package manager

---

## 🚀 How to Run

### 1. Local Development (Source Code)

Use this mode for local development, testing, and debugging directly from Python source:

```bash
# Install dependencies
uv sync

# Start controller
uv run python main.py
```

---

### 2. Native Binary Build (Local Test)

Compiles Hermes into a standalone native machine-code binary without exposing Python source:

```bash
# Compile and immediately launch:
uv run python scripts/build.py --run

# Or compile only into dist/hermes:
uv run python scripts/build.py
```

---

### 3. Production Release & Client Provisioning

Hermes uses native binary compilation with Ed25519 digital signatures. **Source code never remains on client hardware.**

#### 🚀 Single-Command Deployment (Zero Touch)
Deploys from your Mac to the Raspberry Pi in one single command — generates the signed license on the fly, compiles the native C binary on the Pi, purges all `.py` files, configures `systemd`, and starts Hermes 24/7:

```bash
uv run python scripts/deploy.py \
    --host gluvok@hermes.local \
    --device-id pi1 \
    --device-key hardware123 \
    --center-id 5 \
    --min-weight 70.0
```

> **What this does automatically:**
> 1. Generates the Ed25519 digitally signed license `data/client.lic`.
> 2. Syncs source code to `/opt/hermes/` via `rsync`.
> 3. Installs dependencies in `/opt/hermes/.venv` via `uv sync`.
> 4. Compiles native machine-code binary into `/opt/hermes/bin/hermes` and creates clean launcher `/opt/hermes/run.sh`.
> 5. Uploads `data/client.lic` to `/opt/hermes/data/client.lic`.
> 6. **Purges all `.py` source files, tests, and documentation from the Pi** (0 `.py` files on client hardware).
> 7. Automatically installs `/etc/systemd/system/hermes.service` and starts Hermes in the background with auto-restart on boot!

*(If you already have `data/client.lic`, you can simply run `uv run python scripts/deploy.py --host gluvok@hermes.local`)*

---

#### 🔍 Monitoring & Service Control
Hermes runs continuously in the background as a systemd service:

```bash
# Check service status:
ssh gluvok@hermes.local "sudo systemctl status hermes"

# Follow live streaming logs:
ssh gluvok@hermes.local "sudo journalctl -u hermes -f"

# Restart or stop service:
ssh gluvok@hermes.local "sudo systemctl restart hermes"
ssh gluvok@hermes.local "sudo systemctl stop hermes"

# Run manually/interactively in foreground:
ssh gluvok@hermes.local "cd /opt/hermes && ./run.sh"
```

---

#### Manual / Offline Deployment (Air-Gapped)
If deploying without network access, compile and install directly on the Pi:
```bash
# 1. On Pi: compile and install directly to /opt/hermes
uv run python scripts/package.py --install /opt/hermes

# 2. Place client license
cp client.lic /opt/hermes/data/client.lic

# 3. Start Hermes
cd /opt/hermes && ./run.sh
```

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Emergency Hotspot AP**: `hermes` (Password: `12345678` | Fallback Portal: `http://10.42.0.1:8080`)
  - *Self-Healing Hotspot*: Automatically re-creates and activates `hermes` Access Point if deleted from NetworkManager.
  - *Persistent Wi-Fi Vault*: Remembers all known networks in local SQLite DB for 1-click reconnection without re-entering passwords.
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`

---

> For detailed hardware topologies, sequence flows, and system architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
