# Hermes Codebase Technical Reference & Maintainer Handover Guide

Welcome to the **Hermes Weighbridge & ANPR Integration Controller** maintainer manual. This document provides an exhaustive, function-by-function, file-by-file technical reference for developers maintaining, extending, or debugging this codebase.

---

## Table of Contents

1. [System Overview & Physical Hardware Context](#1-system-overview--physical-hardware-context)
2. [Root Configuration & Entry Point](#2-root-configuration--entry-point)
   - [`main.py`](#mainpy)
   - [`config.json`](#configjson)
   - [`pyproject.toml` & `uv.lock`](#pyprojecttoml--uvlock)
3. [Configuration Subsystem (`src/config/`)](#3-configuration-subsystem-srcconfig)
   - [`config_manager.py`](#srcconfigconfig_managerpy)
   - [`constants.py`](#srcconfigconstantspy)
4. [Core Logic Subsystem (`src/core/`)](#4-core-logic-subsystem-srccore)
   - [`session.py`](#srccoresessionpy)
   - [`stability.py`](#srccorestabilitypy)
   - [`telemetry.py`](#srccoretelemetrypy)
5. [Devices Subsystem (`src/devices/`)](#5-devices-subsystem-srcdevices)
   - [`scale.py`](#srcdevicesscalepy)
   - [`camera.py`](#srcdevicescamerapy)
   - [`wifi.py`](#srcdeviceswifipy)
6. [Integrations Subsystem (`src/integrations/`)](#6-integrations-subsystem-srcintegrations)
   - [`anpr.py`](#srcintegrationsanprpy)
   - [`gluvok.py`](#srcintegrationsgluvokpy)
7. [Web Diagnostics Subsystem (`src/web/`)](#7-web-diagnostics-subsystem-srcweb)
   - [`app.py`](#srcwebapppy)
   - [`blueprints/api.py`](#srcwebblueprintsapipy)
   - [`blueprints/views.py`](#srcwebblueprintsviewspy)
   - [`auth.py`](#srcwebauthpy)
   - [`validation.py`](#srcwebvalidationpy)
   - [`server.py`](#srcwebserverpy)
   - [`static/`](#srcwebstatic)
   - [`templates/index.html`](#srcwebtemplatesindexhtml)
8. [Test Suites (`tests/`)](#8-test-suites-tests)
9. [Operational Timings & Design Tradeoffs](#9-operational-timings--design-tradeoffs)

---

## 1. System Overview & Physical Hardware Context

`hermes` runs on an industrial edge computer (typically a **Raspberry Pi 4B/5**) located directly at a truck weighing bridge. It orchestrates four external physical and network entities:

```
                          ┌───────────────────────────┐
                          │   Weighing Indicator      │
                          │   (RS-232 / UART Stream)  │
                          └─────────────┬─────────────┘
                                        │ Raw Serial Bytes
                                        ▼
┌─────────────────────────┐       ┌───────────┐       ┌───────────────────────────┐
│ Camera 1 (License Plate)│◄──────┤  Hermes   ├──────►│ Cameras 2..N (Overview)   │
│ HTTP / RTSP Snapshot    │       │Controller │       │ HTTP / RTSP Snapshots     │
└───────────┬─────────────┘       └─────┬─────┘       └─────────────┬─────────────┘
            │ JPEG                      │                           │ JPEGs
            ▼                           │ Weighment Record          │
┌─────────────────────────┐             ▼                           │
│ Argus ANPR (:8000)      │       ┌───────────┐                     │
│ FastAPI Microservice    │       │Gluvok API ├─────────────────────┘
└─────────────────────────┘       │Cloud / API│
                                  └───────────┘
```

1. **Weight Indicator (Hardware Serial)**: Transmits continuous ASCII weight readings via an RS-232 serial cable connected to `/dev/ttyAMA0` (GPIO UART) or `/dev/ttyUSB0` at **1200 Baud 8N1**.
2. **Camera 1 (ANPR Angle)**: High-resolution IP camera aimed squarely at the vehicle license plate mounting area.
3. **Cameras 2..N (Overview Angles)**: Auxiliary cameras capturing top-down, side, and rear views of the truck on the platform for visual load verification.
4. **Argus Microservice**: A local or network FastAPI server (`:8000/recognize`) running OCR (YOLO + Docling) on submitted JPEG frames.
5. **Gluvok Cloud API**: Central enterprise weighment database endpoint (`https://gluvok.vercel.app`) receiving signed JSON payloads with base64 images.

---

## 2. Root Configuration & Entry Point

### `main.py`
Application lifecycle entry point and process daemon runner.

- **`shutdown(signum, frame) -> None`**:
  Signal handler for `SIGINT` (Ctrl+C) and `SIGTERM`. Gracefully stops background threads in priority order:
  1. Closes UART serial port and reader thread via `get_uart_reader().stop()`.
  2. Stops the Flask diagnostics web server via `stop_web_server()`.
  3. Stops the Wi-Fi watchdog thread via `stop_wifi_watchdog()`.
  4. Exits with status code `0`.
- **`setup() -> None`**:
  Initializes the runtime environment:
  1. Starts `ScaleUARTReader` background thread listening on configured port/baud.
  2. Launches `FallbackWebServer` on port `8080` serving the diagnostics UI.
  3. Starts `start_wifi_watchdog(interval=30.0)` for emergency hotspot failover.
  4. Validates edge device credentials (`device_id`, `device_key`) in `config.json`.
- **`loop() -> None`**:
  Main execution tick running every 1 second:
  - Invokes `session_manager.check_session_progress()`. If a post-stabilization countdown has elapsed, dispatches `scale_state_machine._trigger_upload(completed_package)`.
  - Ensures timely finalization even if the scale UART pauses transmission.

### `config.json`
Local JSON file storing persistent configuration. Managed automatically by `ConfigManager`:
```json
{
  "ssid": "Facility_WiFi_SSID",
  "password": "WiFi_WPA_Password",
  "center_id": 1,
  "min_weight": 50.0,
  "device_id": 1,
  "device_key": "hardware123",
  "anpr_server_url": "http://127.0.0.1:8000/recognize",
  "serial_port": "/dev/ttyAMA0",
  "serial_baudrate": 1200,
  "anpr_camera_url": "http://192.168.1.101/cgi-bin/snapshot.cgi",
  "auxiliary_camera_urls": [
    "http://192.168.1.102/cgi-bin/snapshot.cgi"
  ]
}
```

### `pyproject.toml` & `uv.lock`
Defines project dependencies managed via Astral [`uv`](https://docs.astral.sh/uv/):
- `opencv-python`: Image capture fallback for RTSP camera streams.
- `pyserial`: Cross-platform RS-232/UART communications.
- `requests`: HTTP client for Argus ANPR and Gluvok Cloud API.
- `flask`: Application factory and REST API for local diagnostics.
- `python-periphery`: Pure-Python Linux GPIO/cdev control for RGB LED state indicator.
- `pytest`, `ruff`, `ty`: Development verification gates.

---

## 3. Configuration Subsystem (`src/config/`)

### `src/config/config_manager.py`
Singleton managing configuration loading, fallback defaults, thread-safe access (`threading.RLock`), dynamic camera getters, and JSON disk persistence (`load_settings` / `_persist`).

#### Class: `ConfigManager`
- **Attributes**:
  - `file_path`: Absolute path to `config.json`.
  - `wifi_ssid`: Stored facility Wi-Fi network SSID.
  - `wifi_password`: WPA/WPA2 passphrase.
  - `center_id`: Numeric identifier for the physical weighing center.
  - `weight_threshold`: Minimum weight (kg) required to trigger a weighing session (default: `50.0 kg`).
  - `device_id`: Integer primary key of the edge device from Gluvok's `devices` table (default: `1`).
  - `device_key`: Pre-shared secret key string for stateless header authentication.
  - `anpr_server_url`: Override URL for Argus ANPR (default: `""`).
  - `serial_port`: Path to UART character device (default: `"/dev/ttyAMA0"`).
  - `serial_baudrate`: Serial communication speed (default: `1200`).
  - `anpr_camera_url`: Snapshot URL for Camera 1.
  - `auxiliary_camera_urls`: List of snapshot URLs for Cameras 2..N.
- **Methods**:
  - **`__init__(file_path=CONFIG_FILE_PATH)`**: Initializes default values, creates recursive lock, and calls `load_settings()`.
  - **`load_settings() -> None`**: Reads `config.json`. If missing, creates a default template.
  - **`_build_data_dict() -> dict[str, Any]`**: Assembles current in-memory fields into a clean dictionary.
  - **`_persist() -> None`**: Writes data dictionary to `config.json` with 2-space indentation under lock.
  - **`save_settings(...) -> None`**: High-level method to update Wi-Fi, Center ID, weight threshold, and device credentials.
  - **`update_system_config(...) -> None`**: Live reconfiguration of hardware parameters (threshold, port, baud, camera URLs).
  - **`update_device_credentials(device_id: int, device_key: str) -> None`**: Updates edge device credentials.
  - **`update_wifi_credentials(ssid: str, password: str) -> None`**: Updates network credentials.
  - **`clear_wifi_credentials() -> None`**: Clears Wi-Fi credentials to trigger emergency AP mode.
  - **`get_anpr_camera_url() -> str`**: Returns active ANPR camera snapshot URL.
  - **`get_auxiliary_camera_urls() -> list[str]`**: Returns list of active auxiliary camera URLs.
  - **`get_anpr_server_url() -> str`**: Returns configured ANPR endpoint or default (`http://127.0.0.1:8000/recognize`).
- **Global**: `config = ConfigManager()` (Singleton used across all modules).

### `src/config/constants.py`
Centralized repository of timing windows, timeouts, buffer boundaries, NetworkManager names, and regex patterns.

- **Scale & UART Timings**:
  - `SCALE_TIMEOUT = 0.05`: 50ms read timeout for non-blocking serial character polling.
  - `INTER_CHAR_TIMEOUT_S = 0.3`: 300ms silence flush threshold.
  - `MAX_BUFFER_LEN = 256`: Safety cap on byte buffer length.
  - `STABILITY_DURATION = 10.0`: Continuous stability requirement (seconds).
  - `STABILITY_TOLERANCE = 2.0`: Maximum allowable variance (±2.0 kg).
- **Camera & ANPR Timings**:
  - `ANPR_CAPTURE_INTERVAL = 2.0`: Interval (seconds) between plate capture attempts.
  - `POST_STABILITY_DURATION = 10.0`: Buffer time (seconds) after scale confirms stable weight before closing session.
  - `CAMERA_TIMEOUT = 3.0`: HTTP snapshot request timeout.
  - `ANPR_SERVER_TIMEOUT = 15.0`: Argus ANPR REST query timeout.
  - `MAX_PARALLEL_CAMERA_WORKERS = 4`: Auxiliary camera snapshot thread pool worker cap.
- **Cloud & Network Timings**:
  - `CLOUD_POST_TIMEOUT = 20.0`: Maximum timeout for Gluvok cloud JSON payload upload.
  - `HOTSPOT_CON_NAME = "Gluvok-Hotspot"`: NetworkManager emergency profile name.
  - `DEFAULT_HOTSPOT_SSID = "Gluvok-Setup"`: Default hotspot SSID.
  - `DEFAULT_HOTSPOT_PASS = "gluvok1234"`: Default hotspot WPA2 passphrase.
  - `WIFI_WATCHDOG_INTERVAL = 30.0`: Wi-Fi connectivity poll interval.
- **Regexes & URLs**:
  - `GLUVOK_BASE_URL = "https://gluvok.vercel.app"`: Production cloud backend endpoint.
  - `INDIAN_PLATE_REGEX`: Standard state and Bharat Series vehicle plate pattern.

---

## 4. Core Logic Subsystem (`src/core/`)

### `src/core/session.py`
Coordinates weighbridge session lifecycle, multi-camera coordination, consensus plate voting, and payload packaging.

- **Enum `SessionPhase`**:
  - `PHASE_IDLE (0)`: No vehicle active.
  - `PHASE_STABILIZING (1)`: Vehicle detected (>50kg); 2-second Camera 1 ANPR capture loop running.
  - `PHASE_POST_STABILITY (2)`: Weight stable; auxiliary cameras captured; +10s timer running.
  - `PHASE_COMPLETED (3)`: Package assembled and dispatched; waiting for truck to exit platform.
- **Class: `WeighbridgeSessionManager`**:
  - **`start_session() -> None`**: Generates unique `session_id` (`SESS_<epoch>_<uuid>`), transitions to `PHASE_STABILIZING`, and spawns daemon thread `_anpr_loop`.
  - **`_anpr_loop() -> None`**: Background worker capturing Camera 1 every 2.0 seconds and sending frames to Argus ANPR. Retains only the last 5 frames in memory to prevent RAM bloat on edge devices.
  - **`on_weight_stabilized(weight: float) -> None`**: Transitions to `PHASE_POST_STABILITY`, triggers parallel auxiliary camera snapshots (`capture_auxiliary_snapshots`), and starts the 10-second post-stability countdown.
  - **`check_session_progress() -> dict[str, Any] | None`**: Checks if the 10-second post-stability duration has completed. If expired, transitions to `PHASE_COMPLETED`, stops the ANPR loop, and calls `_finalize_session_package()`.
  - **`_finalize_session_package() -> dict[str, Any]`**: Assembles final payload: stable weight, highest-voted plate (or fallback error code), Camera 1 final JPEG, auxiliary camera JPEGs, sample statistics, and logs telemetry. Immediately releases raw frame buffers from memory.
  - **`reset_session() -> None`**: Resets all state variables when weight returns to zero.
- **Global**: `session_manager = WeighbridgeSessionManager()`

### `src/core/stability.py`
Continuous weight stability state machine.

- **Enums & Constants**:
  - `ScaleState.SCALE_IDLE (0)`: Platform empty (weight <= threshold).
  - `ScaleState.SCALE_STABILIZING (1)`: Vehicle on platform; stability countdown in progress.
  - `ScaleState.SCALE_STABLE_RECORDED (2)`: Weight stable for 10.0s; session locked until truck leaves.
- **Class: `ScaleStabilityMachine`**:
  - **`process_new_weight(parsed_weight: float) -> None`**:
    1. Checks if an active session package is ready for upload.
    2. If weight <= 0.0 kg, resets machine to `SCALE_IDLE` and resets session manager.
    3. If weight < `weight_threshold` (e.g. 50 kg), resets candidate.
    4. If in `SCALE_IDLE`, transitions to `SCALE_STABILIZING` and calls `session_manager.start_session()`.
    5. Evaluates stability window: if weight stays within ±2.0 kg for 10.0s, locks to `SCALE_STABLE_RECORDED` and invokes `session_manager.on_weight_stabilized()`.
  - **`_trigger_upload(package: dict[str, Any]) -> None`**: Dispatches background worker thread `CloudUpload_<session_id>` to invoke `post_to_cloud` without stalling the scale serial reader.
  - **`reset() -> None`**: Manually resets state machine to `SCALE_IDLE`.
- **Functions**:
  - **`get_scale_state() -> ScaleState`**: Returns active enum state.
  - **`get_current_weight() -> float`**: Returns latest parsed numeric weight.
- **Global**: `scale_state_machine = ScaleStabilityMachine()`

### `src/core/telemetry.py`
Decoupled, thread-safe in-memory telemetry buffer.

- **`record_system_event(source: str, message: str) -> None`**: Appends timestamped entry to circular log (max 20 items) under `_events_lock`.
- **`record_weighment_result(...) -> None`**: Records latest session outcome and updates live error counters under `_live_lock`.
- **`record_error_event(error_code: str, message: str = "") -> None`**: Increments occurrence count for error codes.
- **`get_latest_weighment() -> dict`**: Returns thread-safe snapshot of latest weighment.
- **`get_error_counts() -> dict`**: Returns thread-safe snapshot of error histogram.
- **`get_system_events() -> list`**: Returns copy of recent event list.
- **`reset_telemetry() -> None`**: Resets all in-memory buffers (also aliased as `reset_state`).

---

## 5. Devices Subsystem (`src/devices/`)

### `src/devices/scale.py`
UART serial reader and low-level byte packet parser.

- **Class: `ScaleUARTReader`**:
  - **`__init__()`**: Initializes thread handles, byte buffer (`bytearray`), locks, and active settings.
  - **`start(port=None, baudrate=None) -> None`**: Spawns daemon thread `_read_loop`.
  - **`restart(port=None, baudrate=None) -> None`**: Re-opens connection when port or baud rate is changed in the web dashboard.
  - **`stop() -> None`**: Sets `_running = False` and closes the serial descriptor.
  - **`_open_serial() -> bool`**: Opens `serial.Serial` with configured port, baudrate, 8 data bits, no parity, 1 stop bit (8N1).
  - **`_reconnect_if_needed(last_attempt: float) -> float`**: Attempts auto-reconnect every 5 seconds if connection is lost.
  - **`_read_incoming_bytes() -> None`**: Reads available bytes from serial port and passes them to `handle_scale_char`.
  - **`_read_loop() -> None`**: Core daemon loop delegating to reconnect and read helpers.
  - **`handle_scale_char(c) -> None`**: Appends bytes to `_line_buffer`. Triggers packet parsing on terminators: CR (`\r` = 13), LF (`\n` = 10), STX (`\x02` = 2), ETX (`\x03` = 3), or buffer fullness.
  - **`_check_timeout_flush() -> None`**: Flushes unparsed buffer if 300ms silence elapsed.
  - **`_parse_raw_buffer(buf: bytes) -> None`**:
    1. Primary extraction: Searches for regex `rb"([0-9]{3,6})MN"` (e.g. `26500MN`).
    2. Fallback extraction: Searches for signed decimal strings `r"([-+]?\d+(?:\.\d+)?)"` (e.g. `+05000.5kg` or `-12.5`).
    3. Forwards extracted float to `handle_scale_char_processed(weight)`.
- **Functions**:
  - **`handle_scale_char_processed(weight: float) -> None`**: Bridge invoking `scale_stability.process_new_weight(weight)`.
  - **`get_uart_reader() -> ScaleUARTReader`**: Returns singleton instance `_uart_reader`.

### `src/devices/camera.py`
Concurrent IP camera frame capture module.

- **`fetch_image_bytes(camera_url: str, timeout: float = CAMERA_TIMEOUT) -> bytes | None`**:
  Fetches JPEG frame. Uses HTTP snapshot for speed and low CPU/RAM footprint. If URL scheme is `rtsp://`, delegates to OpenCV RTSP single-frame capture.
- **`_fetch_http_snapshot(url: str, timeout: float) -> bytes | None`**:
  Requests HTTP snapshot with `verify=False` to support self-signed IP camera SSL certificates.
- **`_fetch_rtsp_frame(rtsp_url: str, timeout: float) -> bytes | None`**:
  Opens `cv2.VideoCapture` with `CAP_PROP_BUFFERSIZE = 1`, grabs a single frame, encodes to JPEG (`imencode`), and releases the stream handle immediately.
- **`capture_auxiliary_snapshots(camera_urls: list[str] | None = None) -> dict[int, bytes | None]`**:
  Concurrently captures overview snapshots from all configured auxiliary cameras (Cameras 2..N) using `ThreadPoolExecutor(max_workers=4)`. Returns dictionary mapping camera index (`2, 3, ...`) to JPEG bytes.

### `src/devices/wifi.py`
Linux NetworkManager (`nmcli`) watchdog and automatic emergency AP recovery.

- **Functions**:
  - **`is_nmcli_available() -> bool`**: Verifies `nmcli` binary exists on the system.
  - **`is_wifi_connected() -> bool`**: Inspects `nmcli dev` status. Returns `True` only if `wlan0` is connected to an upstream router (excluding our emergency hotspot).
  - **`is_hotspot_active() -> bool`**: Returns boolean indicating if emergency hotspot is active.
  - **`start_emergency_hotspot(ssid, password) -> bool`**: Configures `wlan0` in AP mode with shared IPv4 routing (`10.42.0.1`). Allows technicians to connect on-site and configure Wi-Fi via `http://10.42.0.1:8080`.
  - **`stop_emergency_hotspot() -> bool`**: Tears down emergency AP connection.
  - **`connect_to_wifi(ssid: str, password: str) -> tuple[bool, str]`**: Attempts connection to facility router. If connection fails, immediately re-engages the emergency hotspot so technician connectivity is not lost.
  - **`_watchdog_loop(interval: float) -> None`**: Background thread monitoring connection state every 30 seconds, automatically activating or deactivating the hotspot.
  - **`start_wifi_watchdog(interval=30.0) -> None`**: Starts watchdog thread.
  - **`stop_wifi_watchdog() -> None`**: Stops watchdog thread.

### `src/devices/led/`
RGB LED hardware driver and operational state indicator on Raspberry Pi GPIO.

- **Pins & Polarity**: GPIO 17 (Red), GPIO 27 (Green), GPIO 22 (Blue), Common Anode (`active_high=False`).
- **States & Visual Indicators**:
  - 🟢 **Green (Idle / Completed)**: Scale idle and ready for next vehicle; also turns Green after cloud success to signal completion even if the vehicle is still on the platform.
  - 🔴 **Red (Active Session)**: First weight encountered above threshold; indicates weighment / capture is in progress.
  - 🔵 **Blue (Cloud Transfer Success)**: Triggered for 10 seconds upon verified weighment transmission to Gluvok Cloud, then transitions to Green.
- **Classes & Modules**:
  - **`colors.py`**: `LEDColor` enum (`OFF`, `GREEN`, `RED`, `BLUE`).
  - **`driver.py` (`LEDHardwareDriver`)**: Controls GPIO pins using `python-periphery` (pure-Python Linux `/dev/gpiochip*` / sysfs) with automatic mock fallback on non-Pi platforms.
  - **`controller.py` (`RGBLedController`)**: High-level state manager coordinating Green (idle/done), Red (active session), and 10s Blue (cloud success) transitions.
- **Global**: `led_controller = RGBLedController()` (Singleton exported via `src.devices`).

---

## 6. Integrations Subsystem (`src/integrations/`)

### `src/integrations/anpr.py`
Argus ANPR microservice client and consensus voting algorithm.

- **`resolve_anpr_endpoint(url: str | None = None) -> str`**:
  Sanitizes ANPR URL, normalizes `0.0.0.0` to `127.0.0.1`, and appends `/recognize` if omitted.
- **`_extract_plate_from_dict(data: dict) -> tuple[str | None, str | None]`**:
  Parses Argus JSON response. Evaluates `results[]` sequentially from index 0 without sorting. Selects the first valid, non-null plate encountered. If index 0 is invalid/null, advances sequentially to index 1, 2, etc. If no valid plate exists across all items, returns `(None, "NO_PLATE_DETECTED")`. Detects pre-screening rejections:
  - `REJECTED_HUMAN_DETECTED`: Safety policy rejected frame due to person standing on platform.
  - `NO_PLATE_DETECTED`: Frame readable but no plate characters recognized.
- **`_parse_anpr_response(response: requests.Response) -> tuple[str | None, str]`**:
  Extracts plate text and status code from HTTP 200/201 responses.
- **`send_frame_to_anpr_server(image_bytes: bytes | None, server_url: str | None = None, timeout: float = ANPR_SERVER_TIMEOUT) -> tuple[str | None, str]`**:
  Submits multipart form (`file: frame.jpg`) to `/recognize` (default timeout 15.0s). Handles `Timeout` and `ConnectionError` cleanly.
- **`get_highest_frequency_plate(plate_list: Sequence[str | None]) -> str`**:
  Consensus voting: computes frequency histogram across all samples collected during the session. Returns the most frequent plate candidate, filtering out intermittent OCR noise.

### `src/integrations/gluvok.py`
Gluvok Cloud API client, device headers authentication, Indian plate regex validation, weighment payload builder, and direct Base64 uploader.

- **`GLUVOK_BASE_URL = "https://gluvok.vercel.app"`**: Base URL for cloud persistence.
- **`get_device_headers() -> dict[str, str]`**: Generates custom HTTP headers (`x-device-id`, `x-device-key`) for stateless edge device authentication.
- **`sanitize_vehicle_number(raw_plate: str) -> tuple[str, str]`**:
  Returns `(detected_vehicle_number, vehicle_number)`. The second value is a sanitized Indian-format candidate (or placeholder `MH00XX0000`).
- **`_build_entry_payload(session_payload: dict[str, Any]) -> dict[str, Any]`**:
  Converts raw camera JPEG byte arrays into RFC 2397 Data URIs (`data:image/jpeg;base64,...`) and structures the JSON payload.
- **`post_to_cloud(session_payload: dict[str, Any]) -> None`**:
  Transmits weighment payload to `POST /api/entries` with custom device headers. Treats HTTP `200` and `201` as success; also handles `401 Unauthorized`, `403 Forbidden`, `400 Bad Request`, and other non-success statuses. Clears raw image memory in caller `session_payload` upon completion.

---

## 7. Web Diagnostics Subsystem (`src/web/`)

### `src/web/app.py`
Flask application factory.

- **`create_app(test_config=None) -> Flask`**:
  Initializes Flask with template directory set to `src/web/templates`. Registers `views_bp` and `api_bp`. Sets `SECRET_KEY` from `FLASK_SECRET_KEY` (falls back to an insecure placeholder if unset).
- **`_register_security_headers(app) -> None`**:
  Appends `@app.after_request` headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Access-Control-Allow-Origin: *`
  - `Access-Control-Allow-Headers: Content-Type, Authorization, X-Auth-Token`
  - `Access-Control-Allow-Methods: GET, POST, OPTIONS`
- **`_register_error_handlers(app) -> None`**:
  Maps HTTP 400, 404, and 500 exceptions to structured JSON responses for `/api/*` endpoints.

### `src/web/blueprints/views.py`
Frontend page routes.

- **`PAGE_ROUTES`**: `("/", "/index", "/scale", "/anpr", "/cloud", "/wifi", "/telemetry", "/errors", "/config", "/admin")`.
- All routes render `index.html`, allowing the client-side JavaScript tab manager to navigate without full page reloads.

### `src/web/blueprints/api.py`
REST API endpoints.

- **`POST /api/login`**:
  Verifies superadmin credentials with constant-time matching. Enforces rate limiting (max 5 failed attempts/60s) and returns HTTP `429` when limited. Returns session token on success.
- **`GET /api/status`**:
  Returns sanitized operational telemetry JSON:
  - `scale`: `ScaleState` and live weight in kg.
  - `argus`: Live health check (`online` boolean).
  - `cloud`: `center_id` and `configured` boolean.
  - `wifi`: Upstream connection status and hotspot active boolean.
  - `config`: Public display fields (`min_weight`, `center_id`, `wifi_ssid`). Sensitive camera RTSP URLs and serial port parameters are excluded from unauthenticated telemetry.
  - `latest_weighment`: Recent weighment record with timestamp and error flag.
  - `error_counts`: Live error counters from the telemetry store.
  - `events`: Circular buffer of recent system events.
- **`GET /api/config`** *(Protected: `@auth_required`)*:
  Returns active threshold weight, serial settings, and camera URLs. Requires superadmin session token.
- **`POST /api/config`** *(Protected: `@auth_required`)*:
  Validates payload via `validate_config_payload`. Updates `config.json`. Dynamically restarts UART serial reader if port or baudrate was modified.
- **`POST /api/wifi`** *(Protected: `@auth_required`)*:
  Saves SSID and password to configuration, then attempts immediate connection via `wifi.connect_to_wifi()`.
- **`POST /api/wifi/clear`** *(Protected: `@auth_required`)*:
  Clears stored credentials from `config.json`.

### `src/web/auth.py`
Authentication and security middleware.

- **Constants**:
  - `SUPERADMIN_USER = os.getenv("SUPERADMIN_USER", "superadmin")`
  - `SUPERADMIN_PASS = os.getenv("SUPERADMIN_PASS", "Gluvok@241821")`
  - `SESSION_LIFETIME_SECONDS = 7200.0` (2-hour sliding window).
  - `RATE_LIMIT_WINDOW_SECONDS = 60.0`
  - `MAX_FAILED_LOGIN_ATTEMPTS = 5`
- **Functions**:
  - **`create_session_token() -> str`**: Generates 32-byte hex token.
  - **`validate_session_token(token: str | None) -> bool`**: Validates active token and slides the expiration window.
  - **`is_rate_limited() -> bool`**: Returns `True` if 5+ failed attempts occurred in the last 60 seconds.
  - **`record_failed_login() -> None`**: Records failed attempt timestamp.
  - **`verify_credentials(userid, password) -> bool`**: Constant-time comparison preventing timing attacks.
  - **`extract_auth_token() -> str`**: Extracts token from `Authorization: Bearer <token>` or `X-Auth-Token` header.
  - **`auth_required(func)`**: View decorator returning HTTP 401 if token is invalid or missing.

### `src/web/validation.py`
Input sanitization and guard clauses.

- **`is_valid_url(url: str, allowed_schemes) -> bool`**: Verifies URL starts with `http://`, `https://`, or `rtsp://` and contains no whitespace or control characters.
- **`validate_config_payload(data: dict) -> tuple[bool, str | None]`**:
  Validates weight threshold (0 to 100,000 kg), serial baudrate (in allowed standard set: `300..115200`), serial port regex (`^[a-zA-Z0-9_\-/\.]{1,64}$`), and camera URLs.

### `src/web/server.py`
WSGI server background daemon runner.

- **Class: `FallbackWebServer`**:
  - `__init__(host="0.0.0.0", port=8080)`
  - **`start() -> None`**: Uses Werkzeug's `make_server` to launch the Flask WSGI app in a background daemon thread.
  - **`stop() -> None`**: Calls `_server.shutdown()` and `server_close()` cleanly.
- **Functions**: `start_web_server()`, `stop_web_server()`.

### `src/web/static/`
Contains offline-ready client-side vendor JavaScript libraries served via Flask's built-in `/static/` route:
- `tailwindcss.js`: Tailwind CSS v4 standalone browser runtime bundle (compiled JIT).
- `lucide.min.js`: Lucide Icons standalone UMD browser bundle (`window.lucide`).

### `src/web/templates/index.html`
Single-page web application featuring:
- **Tailwind CSS v4** styling via `@tailwindcss/browser@4` runtime.
- **Lucide Icons** integration.
- Navigation tabs: Overview, Scale Indicator, ANPR & Cameras, Cloud Transfer, Wi-Fi Setup, Telemetry Logs, System Config.
- Real-time client-side polling every 1,000ms against `/api/status`.
- Unified modal lock overlay with superadmin authentication protecting hardware configuration and Wi-Fi management under the Admin Panel.

---

## 8. Test Suites (`tests/`)

Hermes contains a comprehensive suite of unit and integration tests executing under `pytest`:

| Test File | Test Class / Scope | What It Verifies |
| :--- | :--- | :--- |
| [`tests/test_scale_uart.py`](file:///Users/d/Downloads/hermes/tests/test_scale_uart.py) | `TestScaleUARTReader` | Packet parsing (`26500MN\r\n`), split/chunked serial frames, 300ms inter-character silence timeout flush, STX/ETX framing (`\x02...\x03`), and signed float decimals (`+05000.5kg`, `-12.5`). |
| [`tests/test_anpr_client.py`](file:///Users/d/Downloads/hermes/tests/test_anpr_client.py) | `TestANPRClient` | Empty byte handling, Argus recognition schema parsing (`results[].plate`), pre-screening rejection parsing (`REJECTED_HUMAN_DETECTED`, `NO_PLATE_DETECTED`), flat JSON parsing, network timeout & connection error codes, and highest-frequency consensus plate voting algorithm. |
| [`tests/test_session_fallback.py`](file:///Users/d/Downloads/hermes/tests/test_session_fallback.py) | `TestSessionErrorFallback` | Weighbridge session error propagation (confirming rejected Argus status is forwarded as plate value while still packaging the truck overview image), and consensus preference for valid plates over transient errors. |
| [`tests/test_cloud_post.py`](file:///Users/d/Downloads/hermes/tests/test_cloud_post.py) | `TestCloudPost` | Stateless device authentication headers (`x-device-id`, `x-device-key`), payload construction, Base64 URI generation, HTTP 200/201 success flow, and error handling (401, 403, 400, 500, network exceptions). |
| [`tests/test_threading_isolation.py`](file:///Users/d/Downloads/hermes/tests/test_threading_isolation.py) | `TestThreadingIsolation` | Concurrency safety: non-blocking auxiliary camera captures on weight stability, non-blocking cloud upload dispatches, and thread-safe concurrent access across `ConfigManager`. |
| [`tests/test_web_server.py`](file:///Users/d/Downloads/hermes/tests/test_web_server.py) | `TestFlaskDiagnosticsApp` | Flask web application routes (`/`, `/scale`, `/anpr`, `/cloud`, etc.), `/api/status` schema, Wi-Fi provisioning (`/api/wifi`, `/api/wifi/clear`), configuration updates (`POST /api/config`), input validation, 401 Unauthorized handling, 404 responses, and `FallbackWebServer` thread lifecycle (`start`/`stop`). |
| [`tests/test_wifi_manager.py`](file:///Users/d/Downloads/hermes/tests/test_wifi_manager.py) | `TestWiFiManager` | NetworkManager `nmcli` parsing, active connection detection, exclusion of emergency hotspot from external Wi-Fi status, AP start and stop commands, connection failure recovery, and watchdog background thread control. |

Run all tests:
```bash
uv run pytest -v
```

---

## 9. Operational Timings & Design Tradeoffs

### Why 1200 Baud?
Most industrial weighbridge indicators (e.g. Avery Weigh-Tronix, Cardinal, Rice Lake) output continuous ASCII weight strings over legacy RS-232 interfaces at 1200 or 2400 baud. 1200 baud offers maximum immunity against electrical noise in harsh industrial environments with long cable runs.

### Why 10-Second Stability Window?
Trucks pulling onto a weighbridge cause suspension bounce and load cell oscillation. Requiring weight to remain strictly within **±2.0 kg for 10.0 continuous seconds** guarantees that:
1. The vehicle has fully come to rest.
2. The driver has not stepped out (or is fully stationary).
3. Transient motion artifacts do not trigger premature recordings.

### Why 2-Second ANPR Sample Loop?
Trucks approach the scale slowly. Sampling Camera 1 every 2.0 seconds while the scale is stabilizing yields 4–8 license plate candidates. The consensus voting algorithm (`get_highest_frequency_plate`) selects the winner, eliminating single-frame optical distortions (sun glare, exhaust smoke, headlight reflection).

### Why +10-Second Post-Stability Buffer?
Once weight is verified stable, overview snapshots of the truck bed (Cameras 2..N) are triggered in parallel. Waiting an additional 10 seconds before finalizing ensures the overview snapshots are fully encoded, memory buffers are synced, and the vehicle has not immediately altered position before transmission.
