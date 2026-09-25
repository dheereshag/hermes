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

# Run verification gates
uv run ruff check --fix && uv run ty check && uv run pytest

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

### 3. Production Deployment (Raspberry Pi)

Compiles Hermes into a native binary, stages artifacts in the root directory, and **permanently purges `.git/` and all `.py` source code**:

```bash
# 1. On Pi: Clone repo & configure client credentials
git clone <repo-url> hermes && cd hermes
nano src/config/client_config.py

# 2. Run single deployment command (compiles, purges source & .git, starts Hermes)
uv run python scripts/deploy.py
# (Or bypass confirmation prompt for unattended setups: uv run python scripts/deploy.py --yes)
```

> **Auto-Start on Boot:** For unattended field deployment, configure systemd to run `/home/pi/hermes/hermes.sh`.

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`

---

> For detailed hardware topologies, sequence flows, and system architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
