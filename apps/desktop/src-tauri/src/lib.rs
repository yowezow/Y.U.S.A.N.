use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    path::PathBuf,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use serde::Serialize;
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const CORE_HOST: &str = "127.0.0.1";
const CORE_SIDECAR_NAME: &str = "yusan-core";
// A one-file PyInstaller sidecar can need several seconds to extract on a cold start.
const STARTUP_ATTEMPTS: u8 = 90;
const STARTUP_RETRY_DELAY: Duration = Duration::from_millis(200);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CoreStatus {
    state: String,
    endpoint: String,
    message: String,
}

struct CoreRuntime {
    child: Mutex<Option<CommandChild>>,
    status: Arc<Mutex<CoreStatus>>,
    endpoint: String,
    log_path: PathBuf,
}

#[tauri::command]
fn core_status(core: State<CoreRuntime>) -> CoreStatus {
    core.status
        .lock()
        .map(|status| status.clone())
        .unwrap_or_else(|_| CoreStatus {
            state: "error".into(),
            endpoint: String::new(),
            message: "YUSAN Core durumu okunamadı".into(),
        })
}

fn log_path(app: &AppHandle) -> PathBuf {
    let directory = app
        .path()
        .app_log_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("YUSAN").join("logs"));
    let _ = fs::create_dir_all(&directory);
    directory.join("core-sidecar.log")
}

fn write_log(path: &PathBuf, message: impl AsRef<str>) {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default();
    let line = format!("{timestamp} {}\n", message.as_ref());
    if let Ok(mut log) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = log.write_all(line.as_bytes());
    }
}

fn sanitize_process_output(bytes: &[u8]) -> String {
    let compact = String::from_utf8_lossy(bytes)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let mut safe = compact.replace("Authorization:", "Authorization: <redacted>");
    if safe.len() > 1_000 {
        safe.truncate(1_000);
        safe.push_str("…");
    }
    safe
}

fn select_port() -> Result<u16, String> {
    let listener = TcpListener::bind((CORE_HOST, 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

fn healthcheck(endpoint: &str) -> bool {
    let address = endpoint.trim_start_matches("http://");
    let Ok(socket) = address.parse::<SocketAddr>() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&socket, Duration::from_millis(150)) else {
        return false;
    };
    let request = format!("GET /health HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let _ = stream.set_read_timeout(Some(Duration::from_millis(300)));
    let mut response = String::new();
    stream.read_to_string(&mut response).is_ok()
        && response.starts_with("HTTP/1.1 200")
        && response.contains("\"status\":\"ok\"")
}

fn request_core_shutdown(endpoint: &str) {
    let address = endpoint.trim_start_matches("http://");
    let Ok(socket) = address.parse::<SocketAddr>() else {
        return;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&socket, Duration::from_millis(300)) else {
        return;
    };
    let request = format!("POST /shutdown HTTP/1.1\r\nHost: {address}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    let _ = stream.write_all(request.as_bytes());
}

fn update_status(status: &Arc<Mutex<CoreStatus>>, state: &str, message: impl Into<String>) {
    if let Ok(mut current) = status.lock() {
        current.state = state.into();
        current.message = message.into();
    }
}

fn wait_for_core(status: Arc<Mutex<CoreStatus>>, endpoint: String, log_path: PathBuf) {
    thread::spawn(move || {
        write_log(&log_path, format!("[Startup] Waiting for /health at {endpoint}"));
        for attempt in 1..=STARTUP_ATTEMPTS {
            if healthcheck(&endpoint) {
                write_log(&log_path, format!("[Startup] Health attempt {attempt} succeeded"));
                update_status(&status, "online", "YUSAN Core hazır");
                write_log(&log_path, "[Startup] State -> CORE_READY");
                return;
            }
            if attempt == 1 || attempt % 10 == 0 {
                write_log(&log_path, format!("[Startup] Health attempt {attempt} pending"));
            }
            thread::sleep(STARTUP_RETRY_DELAY);
        }
        write_log(
            &log_path,
            "[Tauri ERROR] Core health check timed out after sidecar spawn",
        );
        update_status(&status, "error", "YUSAN Core'a bağlanılamadı");
    });
}

fn monitor_core_output(
    mut events: tauri::async_runtime::Receiver<CommandEvent>,
    status: Arc<Mutex<CoreStatus>>,
    log_path: PathBuf,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    write_log(&log_path, format!("[Core STDOUT] {}", sanitize_process_output(&line)));
                }
                CommandEvent::Stderr(line) => {
                    write_log(&log_path, format!("[Core STDERR] {}", sanitize_process_output(&line)));
                }
                CommandEvent::Error(error) => {
                    write_log(&log_path, format!("[Tauri ERROR] Core process error: {error}"));
                    update_status(&status, "error", "YUSAN Core başlatılamadı");
                }
                CommandEvent::Terminated(exit) => {
                    let message = format!(
                        "[Tauri ERROR] Core exited: code={:?} signal={:?}",
                        exit.code, exit.signal
                    );
                    write_log(&log_path, message);
                    let is_online = status.lock().map(|current| current.state == "online").unwrap_or(false);
                    if !is_online {
                        update_status(&status, "error", "YUSAN Core başlatılamadı");
                    }
                }
                _ => {}
            }
        }
    });
}

fn start_core(app: &AppHandle) {
    let log_path = log_path(app);
    write_log(&log_path, "[Startup] INITIALIZING");
    write_log(&log_path, "[Startup] Starting YUSAN Core");

    let port = match select_port() {
        Ok(port) => port,
        Err(error) => {
            write_log(&log_path, format!("[Tauri ERROR] Could not reserve a Core port: {error}"));
            let status = Arc::new(Mutex::new(CoreStatus {
                state: "error".into(),
                endpoint: String::new(),
                message: "YUSAN Core için yerel bağlantı noktası açılamadı".into(),
            }));
            app.manage(CoreRuntime { child: Mutex::new(None), status, endpoint: String::new(), log_path });
            return;
        }
    };

    let endpoint = format!("http://{CORE_HOST}:{port}");
    write_log(&log_path, format!("[Startup] Core endpoint: {endpoint}"));
    let status = Arc::new(Mutex::new(CoreStatus {
        state: "starting".into(),
        endpoint: endpoint.clone(),
        message: "YUSAN Core başlatılıyor...".into(),
    }));
    app.manage(CoreRuntime {
        child: Mutex::new(None),
        status: status.clone(),
        endpoint: endpoint.clone(),
        log_path: log_path.clone(),
    });

    match std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.join(CORE_SIDECAR_NAME)))
    {
        Some(path) if path.is_file() => write_log(&log_path, format!("[Tauri] Core executable located: {}", path.display())),
        Some(path) => {
            write_log(&log_path, format!("[Tauri ERROR] Core executable missing: {}", path.display()));
            update_status(&status, "error", "YUSAN Core dosyası bulunamadı");
            return;
        }
        None => {
            write_log(&log_path, "[Tauri ERROR] Could not resolve Core executable location");
            update_status(&status, "error", "YUSAN Core dosyası bulunamadı");
            return;
        }
    }

    let config_path = app
        .path()
        .app_data_dir()
        .ok()
        .map(|directory| {
            let _ = fs::create_dir_all(&directory);
            directory.join("settings.json")
        });
    let core_log_directory = app.path().app_log_dir().ok();
    let mut command = match app.shell().sidecar(CORE_SIDECAR_NAME) {
        Ok(command) => command
            .env("YUSAN_HOST", CORE_HOST)
            .env("YUSAN_PORT", port.to_string())
            .env("YUSAN_PARENT_PID", std::process::id().to_string()),
        Err(error) => {
            write_log(&log_path, format!("[Tauri ERROR] Core sidecar lookup failed: {error}"));
            update_status(&status, "error", "YUSAN Core başlatılamadı");
            return;
        }
    };
    if let Some(path) = config_path {
        command = command.env("YUSAN_CONFIG_PATH", path);
    }
    if let Some(directory) = core_log_directory {
        command = command.env("YUSAN_LOG_DIR", directory);
    }

    match command.spawn() {
        Ok((events, child)) => {
            write_log(&log_path, format!("[Startup] Core PID: {}", child.pid()));
            if let Some(runtime) = app.try_state::<CoreRuntime>() {
                if let Ok(mut stored_child) = runtime.child.lock() {
                    *stored_child = Some(child);
                }
            }
            monitor_core_output(events, status.clone(), log_path.clone());
            wait_for_core(status, endpoint, log_path);
        }
        Err(error) => {
            write_log(&log_path, format!("[Tauri ERROR] Core spawn failed: {error}"));
            update_status(&status, "error", "YUSAN Core başlatılamadı");
        }
    }
}

fn stop_core(app: &tauri::AppHandle) {
    if let Some(core) = app.try_state::<CoreRuntime>() {
        write_log(&core.log_path, "[Tauri] Stopping YUSAN Core");
        request_core_shutdown(&core.endpoint);
        thread::sleep(Duration::from_millis(300));
        if let Ok(mut child) = core.child.lock() {
            if let Some(child) = child.take() {
                if let Err(error) = child.kill() {
                    write_log(&core.log_path, format!("[Tauri ERROR] Core termination failed: {error}"));
                }
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            start_core(&app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![core_status])
        .build(tauri::generate_context!())
        .expect("error while running YUSAN");

    app.run(|app, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            stop_core(app);
        }
    });
}
