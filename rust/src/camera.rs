//! Supervises the `rpicam-vid` child that captures frames, and publishes each JPEG.
//! Two frame sources (rust-streamer "Encoder selection"):
//! - software (default): `rpicam-vid --codec mjpeg` encodes; the splitter cuts frames;
//! - hardware: `rpicam-vid --codec yuv420` emits raw I420; each frame is encoded on the
//!   Pi's V4L2 JPEG encoder (`hwjpeg`) on a blocking thread, newest frame wins.
//!
//! `RPICAM_VID` overrides the executable (tests point it at a fake).

use std::process::{ExitStatus, Stdio};
use std::sync::{Arc, Condvar, Mutex};
use std::time::Instant;

use bytes::Bytes;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::watch;

use crate::config::Config;
use crate::hwjpeg::JpegEncode;
use crate::mjpeg::Splitter;

/// The resolved encoder (after `auto` has been decided).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Codec {
    Software,
    Hardware,
}

/// The newest frame and when it arrived; `None` until the first one.
pub type Latest = Option<(Bytes, Instant)>;

pub fn executable() -> String {
    std::env::var("RPICAM_VID").unwrap_or_else(|_| "rpicam-vid".into())
}

/// `rpicam-vid` arguments for this configuration. rpicam composes rotation with the
/// flips the same way libcamera's Transform does for the Python implementation.
pub fn args(config: &Config, codec: Codec) -> Vec<String> {
    let name = match codec {
        Codec::Software => "mjpeg",
        Codec::Hardware => "yuv420",
    };
    let mut a: Vec<String> = ["-t", "0", "-n", "--codec", name].map(String::from).into();
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
    if let (Codec::Software, Some(q)) = (codec, config.jpeg_quality) {
        a.extend(["--quality".into(), q.to_string()]);
    }
    a.extend(["-o".into(), "-".into()]);
    a
}

pub fn spawn(config: &Config, codec: Codec) -> std::io::Result<Child> {
    Command::new(executable())
        .args(args(config, codec))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
}

/// Read frames until the child's stdout closes; return its exit status. Every complete
/// frame is published to `tx`; the child's stderr is forwarded to the log.
pub async fn run(mut child: Child, tx: watch::Sender<Latest>) -> std::io::Result<ExitStatus> {
    forward_stderr(&mut child);
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

fn forward_stderr(child: &mut Child) {
    if let Some(stderr) = child.stderr.take() {
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                tracing::info!(target: "rpicam-vid", "{line}");
            }
        });
    }
}

/// One-frame handoff to the encoder thread: a slow encoder skips frames, never queues them.
#[derive(Default)]
struct Slot {
    state: Mutex<(Option<Vec<u8>>, bool)>, // (newest raw frame, closed)
    ready: Condvar,
}

impl Slot {
    fn put(&self, frame: Vec<u8>) {
        self.state.lock().expect("slot").0 = Some(frame);
        self.ready.notify_one();
    }

    fn close(&self) {
        self.state.lock().expect("slot").1 = true;
        self.ready.notify_one();
    }

    /// The next frame, or `None` once closed.
    fn take(&self) -> Option<Vec<u8>> {
        let mut state = self.state.lock().expect("slot");
        loop {
            if let Some(frame) = state.0.take() {
                return Some(frame);
            }
            if state.1 {
                return None;
            }
            state = self.ready.wait(state).expect("slot");
        }
    }
}

/// Hardware path: read raw frames of `frame_size` bytes from the child, encode each on
/// `encoder` (a blocking thread), publish the JPEGs. Ends when the child's stdout closes
/// (returns its exit status) or the encoder fails (returns the error).
pub async fn run_raw<E: JpegEncode>(
    mut child: Child,
    frame_size: usize,
    mut encoder: E,
    tx: watch::Sender<Latest>,
) -> std::io::Result<ExitStatus> {
    forward_stderr(&mut child);
    let mut stdout = child.stdout.take().expect("stdout is piped");
    let slot = Arc::new(Slot::default());
    let worker_slot = Arc::clone(&slot);
    let mut worker = tokio::task::spawn_blocking(move || -> std::io::Result<()> {
        while let Some(raw) = worker_slot.take() {
            let jpeg = encoder.encode(&raw)?;
            tx.send_replace(Some((jpeg, Instant::now())));
        }
        Ok(())
    });
    loop {
        let mut raw = vec![0u8; frame_size];
        tokio::select! {
            read = stdout.read_exact(&mut raw) => match read {
                Ok(_) => slot.put(raw),
                Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => break,
                Err(e) => { slot.close(); return Err(e); }
            },
            done = &mut worker => {
                let error = match done {
                    Ok(Err(e)) => e,
                    Ok(Ok(())) => std::io::Error::other("hardware encoder stopped"),
                    Err(e) => std::io::Error::other(format!("hardware encoder thread: {e}")),
                };
                return Err(error);
            }
        }
    }
    slot.close();
    let _ = worker.await;
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
            args(&config(&[]), Codec::Software).join(" "),
            "-t 0 -n --codec mjpeg --width 800 --height 600 --framerate 24 -o -"
        );
    }

    #[test]
    fn flips_and_rotation() {
        let a = args(
            &config(&[("ROTATE", "180"), ("HFLIP", "true"), ("VFLIP", "true")]),
            Codec::Software,
        );
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

    #[test]
    fn hardware_args_ask_for_raw_frames_and_no_quality() {
        let c = config(&[("JPEG_QUALITY", "85")]);
        let hw = args(&c, Codec::Hardware).join(" ");
        assert!(hw.contains("--codec yuv420"), "{hw}");
        assert!(!hw.contains("--quality"), "{hw}");
        let sw = args(&c, Codec::Software).join(" ");
        assert!(
            sw.contains("--codec mjpeg") && sw.contains("--quality 85 -o -"),
            "{sw}"
        );
    }

    struct Tagger(u8);

    impl JpegEncode for Tagger {
        fn encode(&mut self, raw: &[u8]) -> std::io::Result<Bytes> {
            self.0 += 1;
            Ok(Bytes::from(vec![self.0, raw[0], raw.len() as u8]))
        }
    }

    struct Broken;

    impl JpegEncode for Broken {
        fn encode(&mut self, _raw: &[u8]) -> std::io::Result<Bytes> {
            Err(std::io::Error::other("encoder wedged"))
        }
    }

    fn raw_child(frames: usize, size: usize) -> Child {
        Command::new("sh")
            .args([
                "-c",
                &format!("head -c {} /dev/zero | tr '\\0' 'a'", frames * size),
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap()
    }

    #[tokio::test(flavor = "current_thread")]
    async fn raw_frames_are_encoded_and_published() {
        let (tx, rx) = watch::channel(None);
        let status = run_raw(raw_child(3, 6), 6, Tagger(0), tx).await.unwrap();
        assert!(status.success());
        let latest = rx.borrow().as_ref().map(|(f, _)| f.to_vec()).unwrap();
        assert_eq!(&latest[1..], &[b'a', 6]);
        assert!(latest[0] >= 1, "at least one frame encoded");
    }

    #[tokio::test(flavor = "current_thread")]
    async fn encoder_failure_ends_the_run_with_the_error() {
        let (tx, _rx) = watch::channel(None);
        let err = run_raw(raw_child(2, 4), 4, Broken, tx).await.unwrap_err();
        assert!(err.to_string().contains("encoder wedged"), "{err}");
    }
}
