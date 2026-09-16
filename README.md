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
│   ├── [test_cloud_post.py](file:///Users/d/Downloads/hermes/tests/test_cloud_post.py)     # Gluvok API device header auth and payload tests
│   ├── [test_web_server.py](file:///Users/d/Downloads/hermes/tests/test_web_server.py)     # Diagnostics web console & REST API tests
│   └── [test_wifi_manager.py](file:///Users/d/Downloads/hermes/tests/test_wifi_manager.py)   # Wi-Fi watchdog & emergency hotspot fallback tests
└── src/
    ├── config/
    │   ├── [config_manager.py](file:///Users/d/Downloads/hermes/src/config/config_manager.py)  # JSON-backed configuration manager singleton
    │   └── [camera_config.py](file:///Users/d/Downloads/hermes/src/config/camera_config.py)   # Dynamic camera getters, ANPR server URL, and timers
    ├── scale/
    │   ├── [scale_uart.py](file:///Users/d/Downloads/hermes/src/scale/scale_uart.py)      # UART serial stream reader & line buffer parser
    │   └── [scale_stability.py](file:///Users/d/Downloads/hermes/src/scale/scale_stability.py) # 10s continuous weight stability state machine
    ├── camera/
    │   ├── [__init__.py](file:///Users/d/Downloads/hermes/src/camera/__init__.py)        # Camera subpackage exports
    │   ├── [camera_manager.py](file:///Users/d/Downloads/hermes/src/camera/camera_manager.py)  # HTTP snapshot / RTSP frame grabber
    │   ├── [anpr_client.py](file:///Users/d/Downloads/hermes/src/camera/anpr_client.py)     # Argus ANPR server client & plate voting algorithm
    │   └── [session_manager.py](file:///Users/d/Downloads/hermes/src/camera/session_manager.py) # Weighbridge session lifecycle & image packaging
    ├── network/
    │   ├── [cloud_client.py](file:///Users/d/Downloads/hermes/src/network/cloud_client.py)    # Gluvok base URL and device auth header helper
    │   ├── [cloud_post.py](file:///Users/d/Downloads/hermes/src/network/cloud_post.py)      # Weighment payload builder & stateless API uploader
    │   └── [wifi_manager.py](file:///Users/d/Downloads/hermes/src/network/wifi_manager.py)    # Automatic Wi-Fi watchdog & emergency hotspot monitor
    └── web/
        ├── [__init__.py](file:///Users/d/Downloads/hermes/src/web/__init__.py)        # Web subpackage exports
        ├── [app.py](file:///Users/d/Downloads/hermes/src/web/app.py)             # Flask application factory (`create_app`)
        ├── [auth.py](file:///Users/d/Downloads/hermes/src/web/auth.py)            # Superadmin auth, token sliding, rate limiting, and decorators
        ├── [state.py](file:///Users/d/Downloads/hermes/src/web/state.py)           # Decoupled thread-safe telemetry and event log buffer
        ├── [validation.py](file:///Users/d/Downloads/hermes/src/web/validation.py)      # Configuration input sanitization and URL validation utilities
        ├── blueprints/
        │   ├── [api.py](file:///Users/d/Downloads/hermes/src/web/blueprints/api.py)         # REST API endpoints (`/api/status`, `/api/config`, `/api/login`, etc.)
        │   └── [views.py](file:///Users/d/Downloads/hermes/src/web/blueprints/views.py)       # Page routes serving the dashboard UI
        ├── [server.py](file:///Users/d/Downloads/hermes/src/web/server.py)          # Threaded WSGI server runner (:8080) & lifecycle management
        └── templates/
            └── [index.html](file:///Users/d/Downloads/hermes/src/web/templates/index.html)     # Real-time Tailwind CSS v4 diagnostics & configuration web UI
```

---

## 🧭 Subsystem Quick Reference

| Subsystem | Primary Responsibilities | Key Components |
| :--- | :--- | :--- |
| **Scale Subsystem** (`src/scale/`) | Reads raw RS-232 serial stream at 1200 baud, extracts numeric weights via regex, tracks 10s continuous stability (±2 kg), locks session to prevent duplicate uploads. | [`ScaleUARTReader`](file:///Users/d/Downloads/hermes/src/scale/scale_uart.py), [`ScaleStabilityMachine`](file:///Users/d/Downloads/hermes/src/scale/scale_stability.py) |
| **Camera & ANPR** (`src/camera/`) | Runs 2s ANPR capture loop on Camera 1 during weighing, submits frames to Argus microservice, executes consensus plate voting, captures auxiliary cameras in parallel. | [`anpr_client.py`](file:///Users/d/Downloads/hermes/src/camera/anpr_client.py), [`camera_manager.py`](file:///Users/d/Downloads/hermes/src/camera/camera_manager.py), [`WeighbridgeSessionManager`](file:///Users/d/Downloads/hermes/src/camera/session_manager.py) |
| **Cloud Network** (`src/network/`) | Stateless IoT device authentication (`x-device-id`, `x-device-key`), validates Indian vehicle registration numbers, and posts weighment data with direct base64 images to Gluvok API (`POST /api/entries`). | [`get_device_headers`](file:///Users/d/Downloads/hermes/src/network/cloud_client.py), [`post_to_cloud`](file:///Users/d/Downloads/hermes/src/network/cloud_post.py) |
| **Wi-Fi Recovery** (`src/network/`) | Monitors upstream facility Wi-Fi with `nmcli`; automatically spins up an emergency AP (`Gluvok-Setup` @ `10.42.0.1`) if connection drops, allowing on-site recovery. | [`wifi_manager.py`](file:///Users/d/Downloads/hermes/src/network/wifi_manager.py) |
| **Web Console** (`src/web/`) | Modular Flask application on port `8080` with Tailwind CSS v4 single-page dashboard for live weight telemetry, system event logs, and password-protected hardware reconfig. | [`create_app`](file:///Users/d/Downloads/hermes/src/web/app.py), [`FallbackWebServer`](file:///Users/d/Downloads/hermes/src/web/server.py), [`index.html`](file:///Users/d/Downloads/hermes/src/web/templates/index.html) |

---

## 🌟 Key Features

- **Weight Scale Serial Parsing**: Reads continuous raw serial stream from UART (`/dev/ttyAMA0` or USB-to-Serial at 1200 Baud 8N1).
- **Weight Stabilization Detection**: 10-second continuous weight stability tracking (`STABILITY_TOLERANCE = 2.0 kg`, `STABILITY_DURATION = 10s`).
- **ANPR Multi-Sample Voting**: Captures Camera 1 frames every 2 seconds during active weighing and selects the highest-frequency plate candidate.
- **Concurrent Auxiliary Camera Snapshots**: Captures overview snapshots from auxiliary cameras in parallel upon weight stabilization.
- **Non-Blocking Real-Time Threading (Python 3.14 & Pi 5)**: Real-time scale serial reading is completely decoupled from slow network I/O; cloud uploads (20s timeout) and auxiliary camera snapshots are dispatched asynchronously in dedicated background workers, with full thread-safety locking across all shared state.
- **Gluvok Cloud API Integration**: Authenticates statelessly with Gluvok edge device headers (`x-device-id`, `x-device-key`) and posts complete weighment records with direct base64 images.
- **Web Diagnostics Dashboard**: Modular Flask application factory on port `8080` (with blueprints for REST APIs and views) for live telemetry, error monitoring, and runtime configuration.
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
