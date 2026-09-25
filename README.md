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

#### Step 1: Generate Signed Client License (Per Client)
```bash
uv run python scripts/keygen.py \
    --device-id pi1 \
    --device-key hardware123 \
    --center-id 5 \
    --min-weight 70.0 \
    --output data/client.lic
```

#### Step 2: 1-Command Deploy to Raspberry Pi 5

##### How to find your Pi Hostname or IP:
- **From your Mac on same Wi-Fi**: You can use the mDNS hostname directly (e.g. `hermes.local` or `raspberrypi.local`):
  ```bash
  ping -c 1 hermes.local
  ```
- **Directly on the Pi**: Run `hostname -I` in the Pi terminal.

##### Run Deployment from Mac:
Transfers code, compiles the native binary on the Pi, sets up dependencies, installs `client.lic`, and **automatically purges all `.py` source code**:
```bash
# Using mDNS hostname (e.g. user 'gluvok' on 'hermes.local'):
uv run python scripts/deploy.py --host gluvok@hermes.local

# Or using numeric IP:
uv run python scripts/deploy.py --host gluvok@192.168.1.41
```

> **What this does:**
> 1. Syncs source code into `/opt/hermes/` via `rsync`.
> 2. Sets up Python dependencies in `/opt/hermes/.venv` via `uv sync`.
> 3. Compiles native machine-code binary `/opt/hermes/hermes` and runner `/opt/hermes/hermes.sh` using GCC via Nuitka.
> 4. Uploads `data/client.lic` into `/opt/hermes/data/client.lic`.
> 5. **Purges all `.py` source files, tests, and documentation from the Pi** (leaving 0 `.py` files on client hardware).

---

#### Step 3: Run Hermes on the Pi

##### Interactive Run (Live Terminal Logs):
```bash
ssh gluvok@hermes.local "cd /opt/hermes && ./hermes.sh"
```

##### 24/7 Production Background Service (Auto-Start on Boot):
To ensure Hermes runs continuously and restarts automatically on reboot:

```bash
ssh gluvok@hermes.local "sudo tee /etc/systemd/system/hermes.service > /dev/null << 'EOF'
[Unit]
Description=Hermes Weighment & ANPR Controller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=gluvok
WorkingDirectory=/opt/hermes
ExecStart=/opt/hermes/hermes.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now hermes
"
```

To monitor the background service:
```bash
# Check service status:
ssh gluvok@hermes.local "sudo systemctl status hermes"

# Follow live systemd logs:
ssh gluvok@hermes.local "sudo journalctl -u hermes -f"
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
cd /opt/hermes && ./hermes.sh
```

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`

---

> For detailed hardware topologies, sequence flows, and system architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
