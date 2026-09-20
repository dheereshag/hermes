# Gluvok Weighment & ANPR Integration System (Hermes)

An industrial weighing bridge integration controller designed to bridge scale serial indicators, automated multi-camera capture, Argus ANPR (Automatic Number Plate Recognition) voting, local emergency Wi-Fi diagnostics, and **Gluvok Cloud API** weighment logging.

---

## 📚 Essential Documentation

For deep technical details and onboarding, refer to our comprehensive documentation:
- 📖 **[Detailed Codebase Reference (`docs/CODEBASE_REFERENCE.md`)](file:///Users/d/Downloads/hermes/docs/CODEBASE_REFERENCE.md)**: Exhaustive, function-by-function, class-by-class guide covering every file, parameter, return type, and hardware lifecycle timing.
- 🏗️ **[System Architecture Guide (`docs/ARCHITECTURE.md`)](file:///Users/d/Downloads/hermes/docs/ARCHITECTURE.md)**: Hardware layer topologies, sequence diagrams, and inter-subsystem data flows.
- 📐 **[AI Engineering Guidelines (`AGENTS.md`)](file:///Users/d/Downloads/hermes/AGENTS.md)**: Coding rules, verification gates, and architectural constraints.

---

## 🏗️ Project Architecture & File Directory

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
    │   └── [wifi.py](file:///Users/d/Downloads/hermes/src/devices/wifi.py)                # Automatic Wi-Fi watchdog & emergency hotspot monitor
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

## 🧭 Subsystem Quick Reference

| Subsystem | Primary Responsibilities | Key Components |
| :--- | :--- | :--- |
| **Core Business Logic & Durable Spool** (`src/core/`) | Orchestrates weighbridge sessions, 10s continuous weight stability (±2 kg), WAL SQLite outbox storage, background FIFO retry dispatcher, and telemetry store. | [`db.py`](file:///Users/d/Downloads/hermes/src/core/db.py), [`spool.py`](file:///Users/d/Downloads/hermes/src/core/spool.py), [`session.py`](file:///Users/d/Downloads/hermes/src/core/session.py), [`stability.py`](file:///Users/d/Downloads/hermes/src/core/stability.py), [`telemetry.py`](file:///Users/d/Downloads/hermes/src/core/telemetry.py) |
| **Physical Hardware Devices** (`src/devices/`) | Direct drivers: reads RS-232 serial stream at 1200 baud, HTTP/RTSP camera snapshot grabbers, and Linux NetworkManager (`nmcli`) Wi-Fi watchdog. | [`scale.py`](file:///Users/d/Downloads/hermes/src/devices/scale.py), [`camera.py`](file:///Users/d/Downloads/hermes/src/devices/camera.py), [`wifi.py`](file:///Users/d/Downloads/hermes/src/devices/wifi.py) |
| **External Integrations** (`src/integrations/`) | Integrates external networks: Argus ANPR microservice with consensus voting, and Gluvok Cloud API with Basic Auth (`-u`), multipart form uploads, and anti-duplicate verification. | [`anpr.py`](file:///Users/d/Downloads/hermes/src/integrations/anpr.py), [`gluvok.py`](file:///Users/d/Downloads/hermes/src/integrations/gluvok.py) |
| **Diagnostics Web Console** (`src/web/`) | Modular Flask application factory on port `8080` with Tailwind CSS v4 single-page dashboard for live telemetry, spool queue state, system logs, and authenticated configuration. | [`create_app`](file:///Users/d/Downloads/hermes/src/web/app.py), [`FallbackWebServer`](file:///Users/d/Downloads/hermes/src/web/server.py), [`index.html`](file:///Users/d/Downloads/hermes/src/web/templates/index.html) |
| **System Configuration** (`src/config/`) | Thread-safe JSON-backed configuration manager (`RLock`), centralized timing/timeout constants, and fallback defaults. | [`config_manager.py`](file:///Users/d/Downloads/hermes/src/config/config_manager.py), [`constants.py`](file:///Users/d/Downloads/hermes/src/config/constants.py) |

---

## 🌟 Key Features

- **Write-Ahead SQLite Local Durability**: Weighments and camera frames are committed to a local SQLite database (`data/hermes.db`) in WAL mode *before* any upload is attempted, guaranteeing zero data loss during power outages or extended network downtime.
- **Edge Anti-Duplication & Idempotency**: Sequential single-flight FIFO dispatcher with atomic task leases (`lease_until`) and a **verify-before-retry** protocol for ambiguous read timeouts, preventing duplicate cloud entries when retrying offline weighments.
- **Weight Scale Serial Parsing**: Reads continuous raw serial stream from UART (`/dev/ttyAMA0` or USB-to-Serial at 1200 Baud 8N1).
- **Weight Stabilization Detection**: 10-second continuous weight stability tracking (`STABILITY_TOLERANCE = 2.0 kg`, `STABILITY_DURATION = 10s`).
- **ANPR Multi-Sample Voting**: Captures Camera 1 frames every 2 seconds during active weighing and selects the highest-frequency plate candidate.
- **Concurrent Auxiliary Camera Snapshots**: Captures overview snapshots from auxiliary cameras in parallel upon weight stabilization.
- **Non-Blocking Real-Time Threading**: Scale serial reading is completely decoupled from disk spooling and network I/O; cloud uploads and camera captures are dispatched in dedicated background threads.
- **Gluvok Cloud API Multipart Integration**: Matches curl specification (`curl -X POST ... -u "pi1:hardware123" -F "center_id=..." -F "detected_vehicle_number=..." -F "weight=..." -F "file=@..."`).
- **Web Diagnostics Dashboard**: Modular Flask application factory on port `8080` displaying live scale weight, ANPR status, cloud spool queue counts, error monitoring, and configuration.
- **Emergency Wi-Fi Hotspot Fallback**: Detects network disconnections via NetworkManager (`nmcli`) and automatically starts an emergency AP (`Gluvok-Setup`) for on-site recovery.


---

## 🚀 Running the Application on Raspberry Pi

Requires **Python ≥ 3.14** (see `.python-version` / `pyproject.toml`).

### 1. Install Dependencies
Ensure [`uv`](https://docs.astral.sh/uv/) is installed, then sync project dependencies:
```bash
uv sync
```

### 2. Configure System Settings
Runtime settings live in `config.json`, which is **gitignored** and **auto-created** with defaults on first run if missing. Adjust it directly or via the local web dashboard:
- `anpr_server_url`: URL to Argus FastAPI endpoint (defaults to `http://127.0.0.1:8000/recognize`).
- `anpr_camera_url`: Snapshot URL of IP Camera 1.
- `auxiliary_camera_urls`: List of overview camera snapshot URLs.
- `serial_port`: Path to UART port (default `/dev/ttyAMA0`).
- `serial_baudrate`: Serial baud rate (default `1200`).
- `ssid` / `password`: Facility Wi-Fi credentials (used by the Wi-Fi watchdog / connect APIs).
- `device_id`: Integer primary key of the edge device from Gluvok's `devices` table (default `1`).
- `device_key`: Pre-shared secret key for stateless header authentication.
- `center_id`: Collection center identifier (default `1`).
- `min_weight`: Minimum threshold in kg to trigger a weighing session (default `50.0`).

Optional environment variables:
- `SUPERADMIN_USER` / `SUPERADMIN_PASS`: Web dashboard credentials (defaults: `superadmin` / `Gluvok@241821`).
- `FLASK_SECRET_KEY`: Flask session secret (defaults to an insecure placeholder; set in production).

### 3. Run Quality Gates & Tests
Run all verification suites:
```bash
uv run ruff check --fix
uv run ty check
uv run pytest
```

### 4. Start Application
```bash
uv run python main.py
```
