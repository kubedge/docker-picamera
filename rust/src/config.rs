//! Service configuration, read once from the environment at startup.
//!
//! Variable names, defaults and error messages match `src/docker_picamera/config.py`
//! exactly: the shared conformance suite checks both implementations against them.

use std::collections::HashMap;

pub const SUPPORTED_ROTATIONS: [u32; 2] = [0, 180];
pub const DEFAULT_PORT: u16 = 8000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub username: String,
    pub password: String,
    pub width: u32,
    pub height: u32,
    pub framerate: u32,
    pub rotation: u32,
    pub hflip: bool,
    pub vflip: bool,
    pub port: u16,
}

/// `docker-picamera-example` / `picamera-rs --example`: fixed settings, no credentials.
pub fn example_config(env: &HashMap<String, String>) -> Result<Config, String> {
    Ok(Config {
        username: String::new(),
        password: String::new(),
        width: 640,
        height: 480,
        framerate: 24,
        rotation: 0,
        hflip: false,
        vflip: false,
        port: load_port(env)?,
    })
}

/// Build a Config from environment variables; the first bad one is an error whose
/// message starts with the variable's name.
pub fn load_config(env: &HashMap<String, String>) -> Result<Config, String> {
    let get = |name: &str, default: &str| env.get(name).cloned().unwrap_or_else(|| default.into());

    let username = get("AUTH_USERNAME", "pi");
    if username.is_empty() {
        return Err("AUTH_USERNAME: must not be empty".into());
    }
    let password = get("AUTH_PASSWORD", "");
    if password.is_empty() {
        return Err("AUTH_PASSWORD: must be set to a non-empty value".into());
    }

    let raw_resolution = get("RESOLUTION", "800x600");
    let (width, height) = parse_resolution(&raw_resolution).ok_or_else(|| {
        format!(
            "RESOLUTION: expected <width>x<height> with positive integers, got {}",
            py_repr(&raw_resolution)
        )
    })?;

    let raw_framerate = get("FRAMERATE", "24");
    let framerate = digits(&raw_framerate).filter(|n| *n > 0).ok_or_else(|| {
        format!(
            "FRAMERATE: expected a positive integer, got {}",
            py_repr(&raw_framerate)
        )
    })?;

    let raw_rotation = get("ROTATE", "0");
    let rotation = digits(&raw_rotation)
        .filter(|n| SUPPORTED_ROTATIONS.contains(n))
        .ok_or_else(|| {
            format!(
                "ROTATE: only 0 and 180 are supported, got {}",
                py_repr(&raw_rotation)
            )
        })?;

    Ok(Config {
        username,
        password,
        width,
        height,
        framerate,
        rotation,
        hflip: flag(env, "HFLIP")?,
        vflip: flag(env, "VFLIP")?,
        port: load_port(env)?,
    })
}

/// `PORT`, default 8000.
pub fn load_port(env: &HashMap<String, String>) -> Result<u16, String> {
    let raw = env
        .get("PORT")
        .cloned()
        .unwrap_or_else(|| DEFAULT_PORT.to_string());
    digits(&raw)
        .filter(|n| (1..=65535).contains(n))
        .map(|n| n as u16)
        .ok_or_else(|| {
            format!(
                "PORT: expected a port number 1-65535, got {}",
                py_repr(&raw)
            )
        })
}

fn parse_resolution(raw: &str) -> Option<(u32, u32)> {
    let (w, h) = raw.split_once('x')?;
    let (w, h) = (digits(w)?, digits(h)?);
    (w > 0 && h > 0).then_some((w, h))
}

/// ASCII digits only (no sign, no spaces), as `^\d+$` in the Python implementation.
fn digits(raw: &str) -> Option<u32> {
    if raw.is_empty() || !raw.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    raw.parse().ok()
}

fn flag(env: &HashMap<String, String>, name: &str) -> Result<bool, String> {
    let raw = env.get(name).cloned().unwrap_or_else(|| "false".into());
    match raw.to_lowercase().as_str() {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(format!(
            "{name}: expected true or false, got {}",
            py_repr(&raw)
        )),
    }
}

/// Python's `repr()` of a str, for identical messages: single quotes unless the value
/// contains one and no double quote.
fn py_repr(value: &str) -> String {
    if value.contains('\'') && !value.contains('"') {
        format!("\"{value}\"")
    } else {
        format!("'{}'", value.replace('\\', "\\\\").replace('\'', "\\'"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        let mut map: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect();
        map.entry("AUTH_PASSWORD".into())
            .or_insert_with(|| "s3cret".into());
        map
    }

    fn err(pairs: &[(&str, &str)]) -> String {
        load_config(&env(pairs)).unwrap_err()
    }

    #[test]
    fn defaults_apply_when_only_password_is_set() {
        assert_eq!(
            load_config(&env(&[])).unwrap(),
            Config {
                username: "pi".into(),
                password: "s3cret".into(),
                width: 800,
                height: 600,
                framerate: 24,
                rotation: 0,
                hflip: false,
                vflip: false,
                port: 8000,
            }
        );
    }

    #[test]
    fn explicit_values_apply() {
        let c = load_config(&env(&[
            ("AUTH_USERNAME", "cam"),
            ("RESOLUTION", "1280x720"),
            ("FRAMERATE", "15"),
            ("ROTATE", "180"),
            ("HFLIP", "TRUE"),
            ("VFLIP", "False"),
            ("PORT", "9000"),
        ]))
        .unwrap();
        assert_eq!(
            (c.username.as_str(), c.width, c.height, c.framerate),
            ("cam", 1280, 720, 15)
        );
        assert_eq!(
            (c.rotation, c.hflip, c.vflip, c.port),
            (180, true, false, 9000)
        );
    }

    #[test]
    fn password_is_required() {
        let mut no_password = env(&[]);
        no_password.remove("AUTH_PASSWORD");
        for e in [no_password, env(&[("AUTH_PASSWORD", "")])] {
            assert_eq!(
                load_config(&e).unwrap_err(),
                "AUTH_PASSWORD: must be set to a non-empty value"
            );
        }
    }

    #[test]
    fn empty_username_is_rejected() {
        assert_eq!(
            err(&[("AUTH_USERNAME", "")]),
            "AUTH_USERNAME: must not be empty"
        );
    }

    #[test]
    fn malformed_resolution_names_variable_and_value() {
        for v in ["800by600", "800x", "x600", "0x600", "800x0", "-800x600", ""] {
            assert_eq!(
                err(&[("RESOLUTION", v)]),
                format!("RESOLUTION: expected <width>x<height> with positive integers, got '{v}'")
            );
        }
    }

    #[test]
    fn framerate_must_be_positive_integer() {
        for v in ["0", "-1", "abc", "2.5", ""] {
            assert!(err(&[("FRAMERATE", v)]).starts_with("FRAMERATE: "), "{v}");
        }
    }

    #[test]
    fn only_0_and_180_rotation() {
        for v in ["90", "270", "-180", "abc"] {
            assert_eq!(
                err(&[("ROTATE", v)]),
                format!("ROTATE: only 0 and 180 are supported, got '{v}'")
            );
        }
    }

    #[test]
    fn flip_must_be_true_or_false() {
        for name in ["HFLIP", "VFLIP"] {
            assert_eq!(
                err(&[(name, "yes")]),
                format!("{name}: expected true or false, got 'yes'")
            );
        }
    }

    #[test]
    fn port_must_be_1_to_65535() {
        for v in ["0", "65536", "abc", ""] {
            assert!(err(&[("PORT", v)]).starts_with("PORT: "), "{v}");
        }
    }

    #[test]
    fn repr_matches_python() {
        assert_eq!(py_repr("a"), "'a'");
        assert_eq!(py_repr("it's"), "\"it's\"");
    }
}
