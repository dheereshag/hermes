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

## 📂 Project Structure

Click any file below to open it directly in the IDE:

```
hermes/
├── [main.py](file:///Users/d/Downloads/hermes/main.py)                    # Application entry point, setup, and loop
├── config.json                # Runtime hardware & cloud config (gitignored; auto-created on first run)
├── [pyproject.toml](file:///Users/d/Downloads/hermes/pyproject.toml)             # Project definition, dependencies, and test config (uv-managed)
├── [uv.lock](file:///Users/d/Downloads/hermes/uv.lock)                    # Dependency lockfile
├── [README.md](file:///Users/d/Downloads/hermes/README.md)                  # Executive project overview and runbook
├── [AGENTS.md](file:///Users/d/Downloads/hermes/AGENTS.md)                  # Code quality, linting, typing, and architectural rules
├── docs/
│   ├── [ARCHITECTURE.md](file:///Users/d/Downloads/hermes/docs/ARCHITECTURE.md)        # Hardware architecture, protocols, and sequence flows
│   └── [CODEBASE_REFERENCE.md](file:///Users/d/Downloads/hermes/docs/CODEBASE_REFERENCE.md)  # Exhaustive function-by-function developer guide
├── tests/
│   ├── [test_anpr_client.py](file:///Users/d/Downloads/hermes/tests/test_anpr_client.py)    # ANPR client, response schemas, and plate voting tests
│   ├── [test_scale_uart.py](file:///Users/d/Downloads/hermes/tests/test_scale_uart.py)     # Scale UART parser, framing, and silence flush tests
│   ├── [test_session_fallback.py](file:///Users/d/Downloads/hermes/tests/test_session_fallback.py) # Weighbridge session error propagation tests
│   ├── [test_cloud_post.py](file:///Users/d/Downloads/hermes/tests/test_cloud_post.py)     # Gluvok API multipart and Basic Auth tests
│   ├── [test_rgb_led.py](file:///Users/d/Downloads/hermes/tests/test_rgb_led.py)        # RGB LED state indicator driver & transitions tests
│   ├── [test_spool_db.py](file:///Users/d/Downloads/hermes/tests/test_spool_db.py)       # SQLite WAL durable spool, atomic leasing & idempotency tests
│   ├── [test_threading_isolation.py](file:///Users/d/Downloads/hermes/tests/test_threading_isolation.py) # Threading concurrency and non-blocking isolation tests
│   ├── [test_web_server.py](file:///Users/d/Downloads/hermes/tests/test_web_server.py)     # Diagnostics web console & REST API tests
│   └── [test_wifi_manager.py](file:///Users/d/Downloads/hermes/tests/test_wifi_manager.py)   # Wi-Fi watchdog & emergency hotspot fallback tests
└── src/
    ├── config/
    │   ├── [__init__.py](file:///Users/d/Downloads/hermes/src/config/__init__.py)         # Subpackage exports
    │   ├── [config_manager.py](file:///Users/d/Downloads/hermes/src/config/config_manager.py)  # JSON-backed configuration manager singleton (thread-safe RLock)
    │   └── [constants.py](file:///Users/d/Downloads/hermes/src/config/constants.py)       # System timing, timeout constants, buffer sizes & regexes
    ├── core/
    │   ├── [__init__.py](file:///Users/d/Downloads/hermes/src/core/__init__.py)           # Subpackage exports
    │   ├── [db.py](file:///Users/d/Downloads/hermes/src/core/db.py)                       # SQLite WAL durable outbox store with atomic lease locking
    │   ├── [session.py](file:///Users/d/Downloads/hermes/src/core/session.py)             # Weighbridge session lifecycle & multi-camera coordinator
    │   ├── [spool.py](file:///Users/d/Downloads/hermes/src/core/spool.py)                 # Background outbox dispatcher & retry worker with verify-before-retry
    │   ├── [stability.py](file:///Users/d/Downloads/hermes/src/core/stability.py)         # 10s continuous weight stability state machine
    │   └── [telemetry.py](file:///Users/d/Downloads/hermes/src/core/telemetry.py)         # Decoupled thread-safe telemetry and event log buffer
    ├── devices/
    │   ├── [__init__.py](file:///Users/d/Downloads/hermes/src/devices/__init__.py)        # Subpackage exports
    │   ├── [scale.py](file:///Users/d/Downloads/hermes/src/devices/scale.py)              # UART serial stream reader & line buffer parser
    │   ├── [camera.py](file:///Users/d/Downloads/hermes/src/devices/camera.py)            # HTTP snapshot / RTSP frame grabber & parallel aux captures
    │   ├── [wifi.py](file:///Users/d/Downloads/hermes/src/devices/wifi.py)                # Automatic Wi-Fi watchdog & emergency hotspot monitor
    │   └── led/                                        # RGB LED GPIO driver & state machine (Green, Red, Blue)
    ├── integrations/
    │   ├── [__init__.py](file:///Users/d/Downloads/hermes/src/integrations/__init__.py)   # Subpackage exports
    │   ├── [anpr.py](file:///Users/d/Downloads/hermes/src/integrations/anpr.py)           # Argus ANPR server client & plate voting algorithm
    │   └── [gluvok.py](file:///Users/d/Downloads/hermes/src/integrations/gluvok.py)       # Gluvok Cloud API client (Basic Auth, multipart upload, verification)
    └── web/
        ├── [__init__.py](file:///Users/d/Downloads/hermes/src/web/__init__.py)            # Subpackage exports
        ├── [app.py](file:///Users/d/Downloads/hermes/src/web/app.py)                     # Flask application factory (`create_app`)
        ├── [auth.py](file:///Users/d/Downloads/hermes/src/web/auth.py)                   # Superadmin auth, token sliding, rate limiting, and decorators
        ├── [validation.py](file:///Users/d/Downloads/hermes/src/web/validation.py)       # Configuration input sanitization and URL validation utilities
        ├── blueprints/
        │   ├── [api.py](file:///Users/d/Downloads/hermes/src/web/blueprints/api.py)      # REST API endpoints (`/api/status`, `/api/config`, `/api/login`, etc.)
        │   └── [views.py](file:///Users/d/Downloads/hermes/src/web/blueprints/views.py)  # Page routes serving the dashboard UI
        ├── [server.py](file:///Users/d/Downloads/hermes/src/web/server.py)               # Threaded WSGI server runner (:8080) & lifecycle management
        └── templates/
            └── [index.html](file:///Users/d/Downloads/hermes/src/web/templates/index.html) # Real-time Tailwind CSS v4 diagnostics & configuration web UI
```

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
