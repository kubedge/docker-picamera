//! Supervises the `rpicam-vid` child that captures and encodes MJPEG, and publishes
//! each complete frame. `RPICAM_VID` overrides the executable (tests point it at a fake).

use std::process::{ExitStatus, Stdio};
use std::time::Instant;

use bytes::Bytes;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::watch;

use crate::config::Config;
use crate::mjpeg::Splitter;

/// The newest frame and when it arrived; `None` until the first one.
pub type Latest = Option<(Bytes, Instant)>;

pub fn executable() -> String {
    std::env::var("RPICAM_VID").unwrap_or_else(|_| "rpicam-vid".into())
}

/// `rpicam-vid` arguments for this configuration. rpicam composes rotation with the
/// flips the same way libcamera's Transform does for the Python implementation.
pub fn args(config: &Config) -> Vec<String> {
    let mut a: Vec<String> = ["-t", "0", "-n", "--codec", "mjpeg"]
        .map(String::from)
        .into();
    a.extend(["--width".into(), config.width.to_string()]);
    a.extend(["--height".into(), config.height.to_string()]);
    a.extend(["--framerate".into(), config.framerate.to_string()]);
    if config.hflip {
        a.push("--hflip".into());
    }
    if config.vflip {
        a.push("--vflip".into());
    }
    if config.rotation == 180 {
        a.extend(["--rotation".into(), "180".into()]);
    }
    a.extend(["-o".into(), "-".into()]);
    a
}

pub fn spawn(config: &Config) -> std::io::Result<Child> {
    Command::new(executable())
        .args(args(config))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
}

/// Read frames until the child's stdout closes; return its exit status. Every complete
/// frame is published to `tx`; the child's stderr is forwarded to the log.
pub async fn run(mut child: Child, tx: watch::Sender<Latest>) -> std::io::Result<ExitStatus> {
    if let Some(stderr) = child.stderr.take() {
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                tracing::info!(target: "rpicam-vid", "{line}");
            }
        });
    }
    let mut stdout = child.stdout.take().expect("stdout is piped");
    let mut splitter = Splitter::new();
    let mut chunk = vec![0u8; 64 * 1024];
    loop {
        let n = stdout.read(&mut chunk).await?;
        if n == 0 {
            break;
        }
        for frame in splitter.push(&chunk[..n]) {
            tx.send_replace(Some((frame, Instant::now())));
        }
    }
    if splitter.dropped > 0 {
        tracing::info!(
            "discarded {} bytes outside complete JPEG frames",
            splitter.dropped
        );
    }
    child.wait().await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn config(pairs: &[(&str, &str)]) -> Config {
        let mut env: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect();
        env.insert("AUTH_PASSWORD".into(), "x".into());
        crate::config::load_config(&env).unwrap()
    }

    #[test]
    fn default_args() {
        assert_eq!(
            args(&config(&[])).join(" "),
            "-t 0 -n --codec mjpeg --width 800 --height 600 --framerate 24 -o -"
        );
    }

    #[test]
    fn flips_and_rotation() {
        let a = args(&config(&[
            ("ROTATE", "180"),
            ("HFLIP", "true"),
            ("VFLIP", "true"),
        ]));
        let joined = a.join(" ");
        assert!(
            joined.contains("--hflip --vflip --rotation 180 -o -"),
            "{joined}"
        );
    }

    #[tokio::test(flavor = "current_thread")]
    async fn child_exit_ends_the_run_with_its_status() {
        let child = Command::new("sh")
            .args(["-c", "exit 3"])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let (tx, _rx) = watch::channel(None);
        let status = run(child, tx).await.unwrap();
        assert_eq!(status.code(), Some(3));
    }

    #[tokio::test(flavor = "current_thread")]
    async fn frames_from_the_child_are_published() {
        let frame = crate::mjpeg::tests::jpeg(9);
        let hex: String = frame.iter().map(|b| format!("\\{b:03o}")).collect();
        let child = Command::new("sh")
            .args(["-c", &format!("printf '{hex}'")])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let (tx, rx) = watch::channel(None);
        run(child, tx).await.unwrap();
        assert_eq!(rx.borrow().as_ref().map(|(f, _)| f.to_vec()), Some(frame));
    }
}
