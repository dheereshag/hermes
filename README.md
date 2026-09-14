# Gluvok Weighment & ANPR Integration System (Hermes)

An industrial weighing bridge integration controller designed to bridge scale serial indicators, automated multi-camera capture, Argus ANPR (Automatic Number Plate Recognition) voting, local emergency Wi-Fi diagnostics, and **Gluvok Cloud API** weighment logging.

---

## 🏗️ Project Architecture & Folder Structure

Detailed architectural diagrams and sequence flows can be found in [`docs/ARCHITECTURE.md`](file:///Users/d/Downloads/hermes/docs/ARCHITECTURE.md).

```
hermes/
├── main.py                    # Application entry point & lifecycle loop
├── config.json                # Local persistent configuration settings
├── pyproject.toml             # Project definition, dependencies, and test config (uv-managed)
├── uv.lock                    # Dependency lockfile
├── README.md                  # Project overview and quickstart
├── AGENTS.md                  # AI agent engineering and code quality guidelines
├── docs/
│   └── ARCHITECTURE.md        # Technical architecture, protocol, and data flow documentation
├── tests/
│   ├── test_anpr_client.py    # ANPR client and plate voting tests
│   ├── test_scale_uart.py     # Scale UART parser unit tests
│   ├── test_session_fallback.py # Weighbridge session fallback and error propagation tests
│   ├── test_cloud_auth.py     # Gluvok API authentication and token refresh tests
│   ├── test_web_server.py     # Fallback web dashboard & REST API tests
│   └── test_wifi_manager.py   # Wi-Fi watchdog & emergency hotspot tests
└── src/
    ├── config/
    │   ├── config_manager.py  # JSON-backed configuration manager
    │   └── camera_config.py   # Dynamic camera getters, ANPR server URL, and timers
    ├── scale/
    │   ├── scale_uart.py      # UART serial stream reader & packet buffer parser
    │   └── scale_stability.py # 10s continuous weight stability state machine
    ├── camera/
    │   ├── __init__.py        # Camera subpackage exports
    │   ├── camera_manager.py  # HTTP snapshot / RTSP frame grabber
    │   ├── anpr_client.py     # ANPR server client & plate voting algorithm
    │   └── session_manager.py # Weighbridge session lifecycle & image packaging
    ├── network/
    │   ├── cloud_client.py    # Gluvok base URL and token state singleton
    │   ├── cloud_auth.py      # Device JWT login & token refresh manager
    │   ├── cloud_post.py      # Weighment payload & base64 image uploader
    │   └── wifi_manager.py    # Automatic Wi-Fi watchdog & emergency hotspot monitor
    └── web/
        ├── __init__.py        # Web subpackage exports
        ├── app.py             # Flask application factory (create_app)
        ├── auth.py            # Superadmin auth, token sliding, rate limiting, and decorators
        ├── state.py           # Decoupled thread-safe telemetry and event log buffer
        ├── validation.py      # Input sanitization and URL validation utilities
        ├── blueprints/
        │   ├── __init__.py    # Blueprint exports
        │   ├── api.py         # REST API endpoints (/api/status, /api/config, /api/login, etc.)
        │   └── views.py       # Page routes serving the dashboard UI
        ├── server.py          # Threaded WSGI server runner (:8080) & lifecycle management
        └── templates/
            └── index.html     # Real-time Tailwind CSS diagnostics & configuration web UI
```

---

## 🌟 Key Features

- **Weight Scale Serial Parsing**: Reads continuous raw serial stream from UART (`/dev/ttyAMA0` or USB-to-Serial at 1200 Baud 8N1).
- **Weight Stabilization Detection**: 10-second continuous weight stability tracking (`STABILITY_TOLERANCE = 2.0 kg`, `STABILITY_DURATION = 10s`).
- **ANPR Multi-Sample Voting**: Captures Camera 1 frames every 2 seconds during active weighing and selects the highest-frequency plate candidate.
- **Concurrent Auxiliary Camera Snapshots**: Captures overview snapshots from auxiliary cameras in parallel upon weight stabilization.
- **Gluvok Cloud API Integration**: Authenticates with Gluvok Auth REST API and posts complete weighment records with base64 images.
- **Web Diagnostics Dashboard**: Modular Flask application factory on port `8080` (with blueprints for REST APIs and views) for live telemetry, error monitoring, and runtime configuration.
- **Emergency Wi-Fi Hotspot Fallback**: Detects network disconnections via NetworkManager (`nmcli`) and automatically starts an emergency AP (`Gluvok-Setup`) for on-site recovery.

---

## 🚀 Running the Application on Raspberry Pi

### 1. Install Dependencies
Ensure [`uv`](https://docs.astral.sh/uv/) is installed, then sync project dependencies:
```bash
uv sync
```

### 2. Configure System Settings
Configuration is stored in `config.json` and can be adjusted directly or via the local web dashboard:
- `anpr_server_url`: URL to Argus FastAPI endpoint (defaults to `http://127.0.0.1:8000/recognize`).
- `anpr_camera_url`: Snapshot URL of IP Camera 1.
- `auxiliary_camera_urls`: List of overview camera snapshot URLs.
- `serial_port`: Path to UART port (default `/dev/ttyAMA0`).
- `serial_baudrate`: Baud rate (default `1200`).
- `min_weight`: Minimum threshold in kg to trigger a weighing session (default `50.0`).

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
