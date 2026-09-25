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

Hermes uses a **build-once, deploy-everywhere** architecture with Ed25519 digital signatures. Source code never touches client hardware.

#### Step 1: Build Generic Release Package (Run once on Dev Machine)
```bash
uv run python scripts/package.py
# Produces dist/hermes-release.tar.gz (0 .py files)
```

#### Step 2: Generate Signed Client License (Per Client)
```bash
uv run python scripts/keygen.py \
    --device-id pi1 \
    --device-key hardware123 \
    --center-id 5 \
    --min-weight 70.0 \
    --anpr-url http://127.0.0.1:8000/recognize \
    --output client.lic
```

#### Step 3: Deploy to Raspberry Pi (< 5 Seconds)
```bash
# 1. Unpack release package to /opt/hermes
tar -xzf hermes-release.tar.gz -C /opt/hermes

# 2. Place client license
cp client.lic /opt/hermes/data/client.lic

# 3. Start Hermes
cd /opt/hermes && ./hermes.sh
```

> **Auto-Start on Boot:** For unattended field deployment, configure systemd to run `/opt/hermes/hermes.sh`.

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`

---

> For detailed hardware topologies, sequence flows, and system architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
