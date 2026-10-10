//! Splits a concatenated-JPEG byte stream (`rpicam-vid --codec mjpeg -o -`) into frames.
//!
//! The splitter walks JPEG structure instead of searching for `FF D9`: after SOI come
//! length-prefixed marker segments up to SOS, then entropy-coded data in which `FF` is
//! followed by `00` (byte stuffing) or `D0..D7` (restart markers) unless it starts a real
//! marker. Only a complete SOI..EOI frame is ever emitted; bytes outside one are dropped
//! and counted. The buffer is bounded so a corrupt stream cannot grow memory.

use bytes::{Bytes, BytesMut};

const SOI: u8 = 0xD8;
const EOI: u8 = 0xD9;
const SOS: u8 = 0xDA;
const MIN_CAPACITY: usize = 1 << 20;

pub struct Splitter {
    buf: BytesMut,
    largest_frame: usize,
    /// Bytes discarded because they were not part of a complete frame.
    pub dropped: u64,
}

enum Scan {
    /// A complete frame ends at this offset (exclusive).
    Frame(usize),
    /// More input is needed.
    Incomplete,
    /// The data after this SOI is not a JPEG; resynchronise past it.
    Corrupt,
}

impl Default for Splitter {
    fn default() -> Self {
        Self::new()
    }
}

impl Splitter {
    pub fn new() -> Self {
        Self {
            buf: BytesMut::new(),
            largest_frame: 0,
            dropped: 0,
        }
    }

    fn capacity(&self) -> usize {
        MIN_CAPACITY.max(4 * self.largest_frame)
    }

    /// Feed bytes; returns every frame completed by them, oldest first.
    pub fn push(&mut self, data: &[u8]) -> Vec<Bytes> {
        self.buf.extend_from_slice(data);
        let mut frames = Vec::new();
        loop {
            let Some(start) = find_soi(&self.buf) else {
                // Keep a trailing FF: it may be the first half of the next SOI.
                let keep = usize::from(self.buf.last() == Some(&0xFF));
                let drop = self.buf.len() - keep;
                self.dropped += drop as u64;
                let _ = self.buf.split_to(drop);
                break;
            };
            if start > 0 {
                self.dropped += start as u64;
                let _ = self.buf.split_to(start);
            }
            match scan_frame(&self.buf) {
                Scan::Frame(end) => {
                    self.largest_frame = self.largest_frame.max(end);
                    frames.push(self.buf.split_to(end).freeze());
                }
                Scan::Corrupt => {
                    self.dropped += 2;
                    let _ = self.buf.split_to(2);
                }
                Scan::Incomplete => {
                    if self.buf.len() > self.capacity() {
                        self.dropped += self.buf.len() as u64;
                        self.buf.clear();
                    }
                    break;
                }
            }
        }
        frames
    }
}

fn find_soi(buf: &[u8]) -> Option<usize> {
    buf.windows(2).position(|w| w == [0xFF, SOI])
}

/// `buf` starts with SOI.
fn scan_frame(buf: &[u8]) -> Scan {
    let mut i = 2;
    loop {
        // Expect a marker: FF, optional FF fill bytes, then the marker code.
        let Some(&b) = buf.get(i) else {
            return Scan::Incomplete;
        };
        if b != 0xFF {
            return Scan::Corrupt;
        }
        while buf.get(i + 1) == Some(&0xFF) {
            i += 1;
        }
        let Some(&marker) = buf.get(i + 1) else {
            return Scan::Incomplete;
        };
        match marker {
            EOI => return Scan::Frame(i + 2),
            SOI | 0x00 => return Scan::Corrupt,
            0x01 | 0xD0..=0xD7 => i += 2, // standalone markers carry no length
            _ => {
                let Some(len) = buf.get(i + 2..i + 4) else {
                    return Scan::Incomplete;
                };
                let len = usize::from(u16::from_be_bytes([len[0], len[1]]));
                if len < 2 {
                    return Scan::Corrupt;
                }
                i += 2 + len;
                if marker == SOS {
                    // Entropy-coded data runs to the next real marker.
                    loop {
                        let Some(&byte) = buf.get(i) else {
                            return Scan::Incomplete;
                        };
                        if byte == 0xFF {
                            match buf.get(i + 1) {
                                None => return Scan::Incomplete,
                                Some(0x00 | 0xD0..=0xD7) => i += 2,
                                Some(_) => break,
                            }
                        } else {
                            i += 1;
                        }
                    }
                }
            }
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// A structurally valid JPEG: SOI, APP0, SOS, entropy data with stuffing and a
    /// restart marker, EOI.
    pub fn jpeg(tag: u8) -> Vec<u8> {
        let mut v = vec![0xFF, 0xD8];
        v.extend_from_slice(&[0xFF, 0xE0, 0x00, 0x10]);
        v.extend_from_slice(b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00");
        v.extend_from_slice(&[0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00]);
        v.extend_from_slice(&[
            tag, 0x12, 0xFF, 0x00, 0x34, 0xFF, 0xD0, 0x56, 0xFF, 0x00, tag,
        ]);
        v.extend_from_slice(&[0xFF, 0xD9]);
        v
    }

    #[test]
    fn whole_frames_in_one_push() {
        let mut s = Splitter::new();
        let input = [jpeg(1), jpeg(2)].concat();
        let frames = s.push(&input);
        assert_eq!(frames, vec![Bytes::from(jpeg(1)), Bytes::from(jpeg(2))]);
        assert_eq!(s.dropped, 0);
    }

    #[test]
    fn frames_split_across_reads_at_every_offset() {
        let input = [jpeg(1), jpeg(2)].concat();
        for cut in 0..input.len() {
            let mut s = Splitter::new();
            let mut frames = s.push(&input[..cut]);
            frames.extend(s.push(&input[cut..]));
            assert_eq!(frames.len(), 2, "cut at {cut}");
            assert_eq!(frames[1], Bytes::from(jpeg(2)));
        }
    }

    #[test]
    fn ff_d9_inside_a_segment_does_not_end_the_frame() {
        let mut frame = jpeg(3);
        // A COM segment containing FF D9 before SOS.
        let com = [0xFF, 0xFE, 0x00, 0x06, 0xFF, 0xD9, 0xAA, 0xBB];
        frame.splice(2..2, com);
        let mut s = Splitter::new();
        assert_eq!(s.push(&frame), vec![Bytes::from(frame.clone())]);
    }

    #[test]
    fn garbage_between_frames_is_dropped_and_counted() {
        let mut s = Splitter::new();
        let input = [
            b"noise".to_vec(),
            jpeg(1),
            b"\xFF\x00more".to_vec(),
            jpeg(2),
        ]
        .concat();
        let frames = s.push(&input);
        assert_eq!(frames, vec![Bytes::from(jpeg(1)), Bytes::from(jpeg(2))]);
        assert_eq!(s.dropped, 5 + 6);
    }

    #[test]
    fn corrupt_frame_resynchronises_on_the_next_soi() {
        let mut s = Splitter::new();
        let input = [vec![0xFF, 0xD8, 0x12, 0x34], jpeg(7)].concat();
        assert_eq!(s.push(&input), vec![Bytes::from(jpeg(7))]);
    }

    #[test]
    fn unterminated_frame_beyond_capacity_is_discarded() {
        let mut s = Splitter::new();
        let mut endless = jpeg(1);
        endless.truncate(endless.len() - 2); // no EOI
        s.push(&endless);
        s.push(&vec![0x11; MIN_CAPACITY + 1]);
        assert_eq!(s.buf.len(), 0);
        assert!(s.dropped > MIN_CAPACITY as u64);
        assert_eq!(s.push(&jpeg(2)), vec![Bytes::from(jpeg(2))]);
    }
}
