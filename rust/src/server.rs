//! HTTP routes — index page, MJPEG stream and health check — optionally behind Basic auth.
//! Status codes, headers and bodies match `src/docker_picamera/server.py`.

use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::Router;
use axum::body::Body;
use axum::extract::{ConnectInfo, State};
use axum::http::{HeaderMap, Method, StatusCode, Uri, header};
use axum::response::{IntoResponse, Response};
use bytes::Bytes;
use futures_util::stream;
use tokio::sync::watch;

use crate::auth;
use crate::camera::Latest;

pub const AUTH_REALM: &str = "picamera";
pub const HEALTH_MAX_AGE: Duration = Duration::from_secs(5);

pub struct Site {
    pub frames: watch::Receiver<Latest>,
    pub page: Bytes,
    /// `None` serves every route without credentials (example mode).
    pub expected_auth: Option<Vec<u8>>,
}

pub fn render_page(title: &str, heading: &str, width: u32, height: u32) -> Bytes {
    Bytes::from(format!(
        "<html>\n<head>\n<title>{title}</title>\n</head>\n<body>\n<h1>{heading}</h1>\n\
         <img src=\"stream.mjpg\" width=\"{width}\" height=\"{height}\" />\n</body>\n</html>\n"
    ))
}

pub fn router(site: Arc<Site>) -> Router {
    Router::new().fallback(handle).with_state(site)
}

async fn handle(
    State(site): State<Arc<Site>>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
) -> Response {
    let path = uri.path();
    let response = route(&site, peer, &method, path, &headers);
    tracing::info!(
        "{} \"{} {}\" {}",
        peer.ip(),
        method,
        path,
        response.status().as_u16()
    );
    response
}

fn route(
    site: &Site,
    peer: SocketAddr,
    method: &Method,
    path: &str,
    headers: &HeaderMap,
) -> Response {
    if method != Method::GET {
        return (StatusCode::NOT_IMPLEMENTED, "Unsupported method\n").into_response();
    }
    if path == "/healthz" {
        return health(site);
    }
    if let Some(expected) = &site.expected_auth {
        let received = headers.get(header::AUTHORIZATION);
        let ok = received.is_some_and(|r| auth::matches(r.as_bytes(), expected));
        if !ok {
            let body: &'static str = if received.is_none() {
                "no auth header received"
            } else {
                "not authenticated"
            };
            return (
                StatusCode::UNAUTHORIZED,
                [
                    (
                        header::WWW_AUTHENTICATE,
                        format!("Basic realm=\"{AUTH_REALM}\""),
                    ),
                    (header::CONTENT_TYPE, "text/html".into()),
                ],
                body,
            )
                .into_response();
        }
    }
    match path {
        "/" => (
            StatusCode::MOVED_PERMANENTLY,
            [(header::LOCATION, "/index.html")],
        )
            .into_response(),
        "/index.html" => ([(header::CONTENT_TYPE, "text/html")], site.page.clone()).into_response(),
        "/stream.mjpg" => stream_response(site.frames.clone(), peer),
        _ => (StatusCode::NOT_FOUND, "Not Found\n").into_response(),
    }
}

fn health(site: &Site) -> Response {
    let fresh = site
        .frames
        .borrow()
        .as_ref()
        .is_some_and(|(_, at)| at.elapsed() <= HEALTH_MAX_AGE);
    let (status, body) = if fresh {
        (StatusCode::OK, "ok\n")
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, "no recent frame\n")
    };
    (status, [(header::CONTENT_TYPE, "text/plain")], body).into_response()
}

/// Logs the client's departure when the response body is dropped.
struct Departure(SocketAddr);

impl Drop for Departure {
    fn drop(&mut self) {
        tracing::info!("Removed streaming client {}: connection closed", self.0);
    }
}

fn stream_response(frames: watch::Receiver<Latest>, peer: SocketAddr) -> Response {
    // The first frame goes out immediately if one exists; then one part per new frame.
    // A slow client skips frames instead of queueing them, and every client shares the
    // same reference-counted frame.
    let state = (frames, true, Departure(peer));
    let parts = stream::unfold(state, |(mut rx, first, departure)| async move {
        if !first || rx.borrow().is_none() {
            rx.changed().await.ok()?;
        }
        let frame = rx.borrow_and_update().as_ref().map(|(f, _)| f.clone())?;
        let head = format!(
            "--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: {}\r\n\r\n",
            frame.len()
        );
        let part = [Bytes::from(head), frame, Bytes::from_static(b"\r\n")].concat();
        Some((
            Ok::<_, std::convert::Infallible>(Bytes::from(part)),
            (rx, false, departure),
        ))
    });
    (
        [
            (header::AGE, "0"),
            (header::CACHE_CONTROL, "no-cache, private"),
            (header::PRAGMA, "no-cache"),
            (
                header::CONTENT_TYPE,
                "multipart/x-mixed-replace; boundary=FRAME",
            ),
        ],
        Body::from_stream(parts),
    )
        .into_response()
}
