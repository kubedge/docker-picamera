//! `picamera-rs`: the camera-streaming contract in Rust, with frames from `rpicam-vid`.
//!
//!   picamera-rs               authenticated stream (AUTH_PASSWORD required)
//!   picamera-rs --example     unauthenticated, fixed 640x480@24
//!   picamera-rs --healthcheck GET /healthz on 127.0.0.1:$PORT; exit 0 on 200 (image HEALTHCHECK)

mod auth;
mod camera;
mod config;
mod hwjpeg;
mod mjpeg;
mod server;

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use tokio::signal::unix::{SignalKind, signal};
use tokio::sync::watch;

use camera::Codec;
use config::EncoderChoice;

const EXIT_CONFIG_ERROR: u8 = 2;
const EXIT_RUNTIME_ERROR: u8 = 1;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let env: HashMap<String, String> = std::env::vars().collect();
    match args.first().map(String::as_str) {
        Some("--healthcheck") => healthcheck(&env),
        Some("--example") | None => {
            let example = !args.is_empty();
            let loaded = if example {
                config::example_config(&env)
            } else {
                config::load_config(&env)
            };
            match loaded {
                Ok(config) => serve(config, example),
                Err(message) => {
                    eprintln!("error: {message}");
                    ExitCode::from(EXIT_CONFIG_ERROR)
                }
            }
        }
        Some(other) => {
            eprintln!("error: unknown argument {other:?}; use --example or --healthcheck");
            ExitCode::from(EXIT_CONFIG_ERROR)
        }
    }
}

fn serve(config: config::Config, example: bool) -> ExitCode {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_ansi(false)
        .init();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .expect("tokio runtime");
    let code = runtime.block_on(run(config, example));
    // Never let a stuck blocking thread (an encoder ioctl) hold the exit past SIGTERM.
    runtime.shutdown_timeout(Duration::from_secs(2));
    code
}

async fn run(config: config::Config, example: bool) -> ExitCode {
    let (title, heading, expected_auth) = if example {
        let t = "Raspberry Pi - Surveillance Camera";
        (t, t, None)
    } else {
        (
            "picamera MJPEG streaming demo",
            "PiCamera MJPEG Streaming Demo",
            Some(auth::expected_header(&config.username, &config.password)),
        )
    };
    let (tx, rx) = watch::channel(None);
    let site = Arc::new(server::Site {
        frames: rx,
        page: server::render_page(title, heading, config.width, config.height),
        expected_auth,
    });

    // Resolve ENCODER before starting the camera: `hardware` without an encoder is a
    // startup error, `auto` without one falls back to software.
    let device = hwjpeg::probe(&hwjpeg::sysfs_dir());
    let encoder = match (config.encoder, &device) {
        (EncoderChoice::Software, _) => None,
        (EncoderChoice::Auto, None) => {
            tracing::info!("hardware JPEG encoder not found; using software");
            None
        }
        (EncoderChoice::Hardware, None) => {
            eprintln!(
                "error: camera: hardware JPEG encoder not found (no {} under {})",
                hwjpeg::ENCODER_NAME,
                hwjpeg::sysfs_dir().display()
            );
            return ExitCode::from(EXIT_RUNTIME_ERROR);
        }
        (EncoderChoice::Hardware | EncoderChoice::Auto, Some(path)) => {
            match hwjpeg::HwJpeg::open(path, config.width, config.height, config.jpeg_quality) {
                Ok(session) => Some((session, path.clone())),
                Err(e) if config.encoder == EncoderChoice::Auto => {
                    tracing::info!("hardware JPEG encoder unusable ({e}); using software");
                    None
                }
                Err(e) => {
                    eprintln!("error: camera: hardware JPEG encoder: {e}");
                    return ExitCode::from(EXIT_RUNTIME_ERROR);
                }
            }
        }
    };
    let codec = if encoder.is_some() {
        Codec::Hardware
    } else {
        Codec::Software
    };

    let child = match camera::spawn(&config, codec) {
        Ok(child) => child,
        Err(e) => {
            eprintln!("error: camera: cannot start {}: {e}", camera::executable());
            return ExitCode::from(EXIT_RUNTIME_ERROR);
        }
    };
    tracing::info!(
        "camera {}x{}@{} hflip={} vflip={} rotation={} encoder={} via {}",
        config.width,
        config.height,
        config.framerate,
        config.hflip,
        config.vflip,
        config.rotation,
        match &encoder {
            None => "software".to_string(),
            Some((_, path)) => format!("hardware({})", path.display()),
        },
        camera::executable()
    );

    let listener = match tokio::net::TcpListener::bind(("0.0.0.0", config.port)).await {
        Ok(l) => l,
        Err(e) => {
            eprintln!("error: cannot listen on port {}: {e}", config.port);
            return ExitCode::from(EXIT_RUNTIME_ERROR);
        }
    };
    tracing::info!("serving on port {}", config.port);

    let (stop_tx, mut stop_rx) = watch::channel(false);
    let app = server::router(site).into_make_service_with_connect_info::<SocketAddr>();
    let server = tokio::spawn(async move {
        axum::serve(listener, app)
            .with_graceful_shutdown(async move {
                let _ = stop_rx.wait_for(|stop| *stop).await;
            })
            .await
    });

    let mut sigterm = signal(SignalKind::terminate()).expect("SIGTERM handler");
    let mut sigint = signal(SignalKind::interrupt()).expect("SIGINT handler");
    let mut camera = match encoder {
        None => tokio::spawn(camera::run(child, tx)),
        Some((session, _)) => {
            let frame_size = hwjpeg::i420_frame_size(config.width, config.height);
            tokio::spawn(camera::run_raw(child, frame_size, session, tx))
        }
    };

    let code = tokio::select! {
        _ = sigterm.recv() => { tracing::info!("received SIGTERM, shutting down"); None }
        _ = sigint.recv() => { tracing::info!("received SIGINT, shutting down"); None }
        ended = &mut camera => {
            match ended {
                Ok(Ok(status)) => tracing::error!("camera process exited: {status}"),
                Ok(Err(e)) => tracing::error!("camera pipeline failed: {e}"),
                Err(e) => tracing::error!("camera task failed: {e}"),
            }
            Some(ExitCode::from(EXIT_RUNTIME_ERROR))
        }
    };

    // Stop the child (kill_on_drop sends SIGKILL when the task's Child is dropped), end
    // every stream by dropping the frame sender with it, then stop accepting.
    camera.abort();
    let _ = camera.await;
    let _ = stop_tx.send(true);
    let _ = tokio::time::timeout(Duration::from_secs(5), server).await;
    match code {
        Some(code) => code,
        None => {
            tracing::info!("stopped");
            ExitCode::SUCCESS
        }
    }
}

fn healthcheck(env: &HashMap<String, String>) -> ExitCode {
    let port = match config::load_port(env) {
        Ok(p) => p,
        Err(message) => {
            eprintln!("error: {message}");
            return ExitCode::from(EXIT_CONFIG_ERROR);
        }
    };
    let probe = || -> std::io::Result<bool> {
        let addr = SocketAddr::from(([127, 0, 0, 1], port));
        let mut s = TcpStream::connect_timeout(&addr, Duration::from_secs(3))?;
        s.set_read_timeout(Some(Duration::from_secs(3)))?;
        s.write_all(b"GET /healthz HTTP/1.0\r\nHost: localhost\r\n\r\n")?;
        let mut head = [0u8; 12];
        s.read_exact(&mut head)?;
        Ok(head.ends_with(b" 200"))
    };
    match probe() {
        Ok(true) => ExitCode::SUCCESS,
        _ => ExitCode::from(EXIT_RUNTIME_ERROR),
    }
}
