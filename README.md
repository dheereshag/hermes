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

##### How to find your Pi IP or Hostname:
- **From your Mac on same Wi-Fi**: You can use the mDNS hostname `raspberrypi.local` directly (no IP needed!), or find the numeric IP via:
  ```bash
  ping -c 1 raspberrypi.local
  ```
- **Directly on the Pi**: Run `hostname -I` in the Pi terminal.

##### Run Deployment:
Transfers code, compiles the native binary on the Pi, installs into `/opt/hermes`, and **automatically purges all `.py` source code**:
```bash
# Using mDNS hostname (easiest):
uv run python scripts/deploy.py --host pi@raspberrypi.local

# Or using numeric IP:
uv run python scripts/deploy.py --host pi@192.168.1.50
```

> **What this does:**
> 1. Syncs source to `/tmp/hermes_build` on the Pi via `rsync`.
> 2. Compiles native binary and installs to `/opt/hermes` (0 `.py` files).
> 3. Installs `data/client.lic` into `/opt/hermes/data/client.lic`.
> 4. **Deletes `/tmp/hermes_build` completely** from the Pi.
> 5. Restarts the `hermes` systemd service.

#### Manual / Offline Deployment (Air-Gapped)
If deploying without network access, compile and install directly on the Pi:
```bash
# 1. On Pi: compile and install directly to /opt/hermes
uv run python scripts/package.py --install /opt/hermes

# 2. Place client license
cp client.lic /opt/hermes/data/client.lic

# 3. Start Hermes
cd /opt/hermes && uv run ./hermes
```

> **Auto-Start on Boot:** For unattended field deployment, configure systemd to run `/opt/hermes/hermes`.

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`

---

> For detailed hardware topologies, sequence flows, and system architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
