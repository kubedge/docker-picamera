//! HTTP Basic authentication with a constant-time comparison.

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use subtle::ConstantTimeEq;

/// The exact `Authorization` value a client must send.
pub fn expected_header(username: &str, password: &str) -> Vec<u8> {
    format!(
        "Basic {}",
        STANDARD.encode(format!("{username}:{password}"))
    )
    .into_bytes()
}

pub fn matches(received: &[u8], expected: &[u8]) -> bool {
    received.ct_eq(expected).into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_is_basic_base64() {
        assert_eq!(expected_header("pi", "s3cret"), b"Basic cGk6czNjcmV0");
    }

    #[test]
    fn comparison() {
        let e = expected_header("pi", "s3cret");
        assert!(matches(&e, &e));
        assert!(!matches(b"Basic cGk6d3Jvbmc=", &e));
        assert!(!matches(b"", &e));
    }
}
