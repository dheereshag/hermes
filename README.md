# Gluvok Weighment & ANPR Integration System (Hermes)

An industrial weighing bridge integration controller bridging scale serial indicators, multi-camera capture, Argus ANPR plate recognition, emergency Wi-Fi diagnostics, and Gluvok Cloud API logging.

---

## 📚 Documentation

- 🏗️ **[System Architecture Guide (`docs/ARCHITECTURE.md`)](docs/ARCHITECTURE.md)**: Hardware topologies, sequence flows, threading, local durable spooling, configuration schema, and Nuitka compilation architecture.
- 📖 **[Codebase Reference (`docs/CODEBASE_REFERENCE.md`)](docs/CODEBASE_REFERENCE.md)**: Exhaustive function-by-function, class-by-class developer guide.
- 📐 **[Engineering Guidelines (`AGENTS.md`)](AGENTS.md)**: Code standards, linting, typing, and verification gates.

---

## ⚡ Prerequisites

- **Python ≥ 3.14** (managed via `.python-version` / `pyproject.toml`)
- **[uv](https://docs.astral.sh/uv/)** package manager

---

## 🚀 Running the Application

### 1. Direct Run (Source Code / Development)

Use this mode for local development, testing, and debugging directly from Python source:

```bash
# 1. Install dependencies
uv sync

# 2. Run verification gates
uv run ruff check --fix
uv run ty check
uv run pytest

# 3. Start controller (config.json is auto-created on first run)
uv run python main.py
```

---

### 2. Nuitka Run (Compiled ARM64 / Production)

Use this mode for edge deployment on Raspberry Pi with core logic compiled into a native C-extension (`src.*.so`):

#### Option A: Pull Pre-Compiled Release (Raspberry Pi Edge Deployment)
The automated CI pipeline compiles and pushes production-ready ARM64 binaries to the `release-arm64` orphan branch:

```bash
git clone -b release-arm64 https://github.com/dheereshag/hermes.git
cd hermes
uv sync
uv run python main.py
```

#### Option B: Compile Locally with Nuitka
To compile the `src/` package locally into a shared object:

```bash
# Compile core package into native shared library
uv run python -m nuitka \
  --module \
  --include-package=src \
  --nofollow-imports \
  --remove-output \
  --lto=yes \
  --python-flag=no_docstrings \
  --output-dir=. \
  src

# Run application using compiled binary
uv run python main.py
```

---

## 🖥️ Web Diagnostics Dashboard

- **URL**: `http://localhost:8080` (or `http://<pi-ip>:8080`)
- **Default Superadmin User**: `superadmin`
- **Default Superadmin Password**: `Gluvok@241821`
- **Offline Resilient**: Self-hosted Tailwind CSS v4 and Lucide icon assets (no internet or CDN required).
