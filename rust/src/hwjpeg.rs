//! Hardware JPEG encoding on the Raspberry Pi's V4L2 memory-to-memory encoder
//! (`bcm2835-codec`, node named `bcm2835-codec-encode_image`, Pi 3/4; the Pi 5 has none).
//!
//! One raw I420 frame in, one JPEG out, synchronously, with one MMAP buffer per queue.
//! The encoder uses the multi-planar API (as picamera2's own V4L2 encoder does), so the
//! few structures and ioctls it needs are declared here over `libc` — no C library to
//! link, so the cross-compile is unchanged. Linux only; elsewhere `open` reports
//! "unsupported" and `auto` falls back to software.

use std::path::{Path, PathBuf};

use bytes::Bytes;

/// The V4L2 card name of the JPEG encoder node.
pub const ENCODER_NAME: &str = "bcm2835-codec-encode_image";
/// Where the encoder is looked for; `PICAMERA_V4L2_SYSFS` overrides it (tests).
pub const DEFAULT_SYSFS: &str = "/sys/class/video4linux";

pub fn sysfs_dir() -> PathBuf {
    std::env::var_os("PICAMERA_V4L2_SYSFS").map_or_else(|| DEFAULT_SYSFS.into(), PathBuf::from)
}

/// `/dev/videoN` of the JPEG encoder, found by name under `sysfs` (`videoN/name`).
pub fn probe(sysfs: &Path) -> Option<PathBuf> {
    let mut found: Vec<String> = std::fs::read_dir(sysfs)
        .ok()?
        .flatten()
        .filter_map(|entry| {
            let node = entry.file_name().into_string().ok()?;
            let name = std::fs::read_to_string(entry.path().join("name")).ok()?;
            (name.trim() == ENCODER_NAME).then_some(node)
        })
        .collect();
    found.sort();
    found.first().map(|node| Path::new("/dev").join(node))
}

/// Luma row stride of `rpicam-vid --codec yuv420` output: the width rounded up to 64
/// bytes (the ISP's alignment; measured on a Pi 3: 800 wide → 832). Chroma rows are half.
pub fn i420_stride(width: u32) -> usize {
    (width as usize).next_multiple_of(64)
}

/// Bytes in one I420 frame as `rpicam-vid --codec yuv420` writes it, row padding included.
pub fn i420_frame_size(width: u32, height: u32) -> usize {
    let (stride, h) = (i420_stride(width), height as usize);
    stride * h + 2 * (stride / 2) * h.div_ceil(2)
}

/// Copy an I420 frame of `width`x`height` from `src` (camera layout: luma stride
/// `src_stride`, planes back to back) into `dst` laid out as the encoder asks: luma stride
/// `dst_stride`, `dst_rows` luma rows per plane allocation (chroma half of each).
/// Padding bytes in `dst` are left as they were.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub fn repack_i420(
    src: &[u8],
    src_stride: usize,
    dst: &mut [u8],
    dst_stride: usize,
    dst_rows: usize,
    width: usize,
    height: usize,
) {
    let (cw, ch) = (width.div_ceil(2), height.div_ceil(2));
    let planes = [
        (0, 0, src_stride, dst_stride, width, height),
        (
            src_stride * height,
            dst_stride * dst_rows,
            src_stride / 2,
            dst_stride / 2,
            cw,
            ch,
        ),
        (
            src_stride * height + (src_stride / 2) * ch,
            dst_stride * dst_rows + (dst_stride / 2) * dst_rows.div_ceil(2),
            src_stride / 2,
            dst_stride / 2,
            cw,
            ch,
        ),
    ];
    for (src_off, dst_off, ss, ds, w, h) in planes {
        for row in 0..h {
            let s = src_off + row * ss;
            let d = dst_off + row * ds;
            dst[d..d + w].copy_from_slice(&src[s..s + w]);
        }
    }
}

/// Something that turns one raw frame into one JPEG.
pub trait JpegEncode: Send + 'static {
    fn encode(&mut self, raw: &[u8]) -> std::io::Result<Bytes>;
}

#[cfg(target_os = "linux")]
pub use linux::HwJpeg;

#[cfg(not(target_os = "linux"))]
pub struct HwJpeg;

#[cfg(not(target_os = "linux"))]
impl HwJpeg {
    pub fn open(
        _device: &Path,
        _width: u32,
        _height: u32,
        _quality: Option<u32>,
    ) -> std::io::Result<Self> {
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "V4L2 hardware encoding is Linux-only",
        ))
    }
}

#[cfg(not(target_os = "linux"))]
impl JpegEncode for HwJpeg {
    fn encode(&mut self, _raw: &[u8]) -> std::io::Result<Bytes> {
        unreachable!("HwJpeg cannot be opened off Linux")
    }
}

#[cfg(target_os = "linux")]
mod linux {
    use std::ffi::CString;
    use std::io::{Error, ErrorKind, Result};
    use std::os::unix::ffi::OsStrExt;
    use std::path::Path;

    use bytes::Bytes;

    use super::{JpegEncode, i420_frame_size, i420_stride, repack_i420};

    // --- uapi/linux/videodev2.h, the parts used here ----------------------------------

    const BUF_TYPE_CAPTURE_MPLANE: u32 = 9;
    const BUF_TYPE_OUTPUT_MPLANE: u32 = 10;
    const MEMORY_MMAP: u32 = 1;
    const FIELD_NONE: u32 = 1;
    const CID_JPEG_COMPRESSION_QUALITY: u32 = 0x009d_0903;

    const fn fourcc(code: &[u8; 4]) -> u32 {
        (code[0] as u32) | (code[1] as u32) << 8 | (code[2] as u32) << 16 | (code[3] as u32) << 24
    }
    const PIX_FMT_YUV420: u32 = fourcc(b"YU12");
    const PIX_FMT_JPEG: u32 = fourcc(b"JPEG");

    #[repr(C, packed)]
    #[derive(Clone, Copy, Default)]
    struct PlanePixFormat {
        sizeimage: u32,
        bytesperline: u32,
        reserved: [u16; 6],
    }

    #[repr(C, packed)]
    #[derive(Clone, Copy, Default)]
    struct PixFormatMplane {
        width: u32,
        height: u32,
        pixelformat: u32,
        field: u32,
        colorspace: u32,
        plane_fmt: [PlanePixFormat; 8],
        num_planes: u8,
        flags: u8,
        ycbcr_enc: u8,
        quantization: u8,
        xfer_func: u8,
        reserved: [u8; 7],
    }

    #[repr(C)]
    union FormatUnion {
        pix_mp: PixFormatMplane,
        raw: [u8; 200],
        _align: [u64; 25],
    }

    #[repr(C)]
    struct Format {
        typ: u32,
        fmt: FormatUnion,
    }

    #[repr(C)]
    #[derive(Default)]
    struct RequestBuffers {
        count: u32,
        typ: u32,
        memory: u32,
        capabilities: u32,
        flags: u8,
        reserved: [u8; 3],
    }

    #[repr(C)]
    #[derive(Default, Clone, Copy)]
    struct Plane {
        bytesused: u32,
        length: u32,
        m: u64, // union { __u32 mem_offset; unsigned long userptr; __s32 fd; }
        data_offset: u32,
        reserved: [u32; 11],
    }

    #[repr(C)]
    #[derive(Default)]
    struct Buffer {
        index: u32,
        typ: u32,
        bytesused: u32,
        flags: u32,
        field: u32,
        timestamp: [i64; 2],
        timecode: [u32; 4],
        sequence: u32,
        memory: u32,
        m: u64, // union { offset; userptr; struct v4l2_plane *planes; fd; }
        length: u32,
        reserved2: u32,
        request_fd: u32,
    }

    #[repr(C)]
    struct Control {
        id: u32,
        value: i32,
    }

    // The kernel's sizes on 64-bit Linux; a layout slip fails the build, not the camera.
    const _: () = assert!(size_of::<PlanePixFormat>() == 20);
    const _: () = assert!(size_of::<PixFormatMplane>() == 192);
    const _: () = assert!(size_of::<Format>() == 208);
    const _: () = assert!(size_of::<RequestBuffers>() == 20);
    const _: () = assert!(size_of::<Plane>() == 64);
    const _: () = assert!(size_of::<Buffer>() == 88);
    const _: () = assert!(size_of::<Control>() == 8);

    const fn ioc(dir: u64, nr: u64, size: usize) -> u64 {
        (dir << 30) | ((size as u64) << 16) | ((b'V' as u64) << 8) | nr
    }
    const W: u64 = 1;
    const R: u64 = 2;
    const VIDIOC_S_FMT: u64 = ioc(R | W, 5, size_of::<Format>());
    const VIDIOC_REQBUFS: u64 = ioc(R | W, 8, size_of::<RequestBuffers>());
    const VIDIOC_QUERYBUF: u64 = ioc(R | W, 9, size_of::<Buffer>());
    const VIDIOC_QBUF: u64 = ioc(R | W, 15, size_of::<Buffer>());
    const VIDIOC_DQBUF: u64 = ioc(R | W, 17, size_of::<Buffer>());
    const VIDIOC_STREAMON: u64 = ioc(W, 18, size_of::<i32>());
    const VIDIOC_STREAMOFF: u64 = ioc(W, 19, size_of::<i32>());
    const VIDIOC_S_CTRL: u64 = ioc(R | W, 28, size_of::<Control>());

    fn xioctl<T>(fd: i32, request: u64, arg: &mut T, what: &str) -> Result<()> {
        // SAFETY: `arg` is the #[repr(C)] struct whose size is encoded in `request`.
        let rc = unsafe { libc::ioctl(fd, request as _, arg as *mut T) };
        if rc < 0 {
            let e = Error::last_os_error();
            return Err(Error::new(e.kind(), format!("{what}: {e}")));
        }
        Ok(())
    }

    struct Mapping {
        ptr: *mut u8,
        len: usize,
    }

    impl Drop for Mapping {
        fn drop(&mut self) {
            // SAFETY: ptr/len come from a successful mmap of this length.
            unsafe { libc::munmap(self.ptr.cast(), self.len) };
        }
    }

    /// An open encoder session for one resolution.
    pub struct HwJpeg {
        fd: i32,
        width: usize,
        height: usize,
        frame_size: usize,
        /// The encoder's input layout, as `VIDIOC_S_FMT` returned it.
        bytesperline: usize,
        rows: usize,
        sizeimage: usize,
        output: Mapping,
        capture: Mapping,
    }

    // The fd and mappings are only touched by the owning thread.
    unsafe impl Send for HwJpeg {}

    impl HwJpeg {
        pub fn open(device: &Path, width: u32, height: u32, quality: Option<u32>) -> Result<Self> {
            let path = CString::new(device.as_os_str().as_bytes())
                .map_err(|_| Error::new(ErrorKind::InvalidInput, "device path"))?;
            // SAFETY: plain open(2) of a NUL-terminated path.
            let fd = unsafe { libc::open(path.as_ptr(), libc::O_RDWR | libc::O_CLOEXEC) };
            if fd < 0 {
                let e = Error::last_os_error();
                return Err(Error::new(
                    e.kind(),
                    format!("open {}: {e}", device.display()),
                ));
            }
            let frame_size = i420_frame_size(width, height);
            let stride = i420_stride(width);
            let setup = || -> Result<(Mapping, Mapping, usize, usize, usize)> {
                // Ask for the camera's own stride; the driver may round it or the height
                // up, so the layout it returns is the one frames are repacked into.
                let (bytesperline, sizeimage) = set_format(
                    fd,
                    BUF_TYPE_OUTPUT_MPLANE,
                    PIX_FMT_YUV420,
                    width,
                    height,
                    stride as u32,
                    frame_size,
                )?;
                let rows = if bytesperline == 0 {
                    0
                } else {
                    sizeimage * 2 / (3 * bytesperline)
                };
                if bytesperline < width as usize || rows < height as usize {
                    return Err(Error::new(
                        ErrorKind::InvalidData,
                        format!(
                            "encoder input layout {bytesperline} bytes/line x {rows} rows \
                             cannot hold {width}x{height}"
                        ),
                    ));
                }
                set_format(
                    fd,
                    BUF_TYPE_CAPTURE_MPLANE,
                    PIX_FMT_JPEG,
                    width,
                    height,
                    0,
                    0,
                )?;
                if let Some(q) = quality {
                    let mut ctrl = Control {
                        id: CID_JPEG_COMPRESSION_QUALITY,
                        value: q as i32,
                    };
                    xioctl(fd, VIDIOC_S_CTRL, &mut ctrl, "set JPEG quality")?;
                }
                let output = map_one(fd, BUF_TYPE_OUTPUT_MPLANE)?;
                if output.len < sizeimage {
                    return Err(Error::new(
                        ErrorKind::InvalidData,
                        format!("encoder input buffer {} < {sizeimage} bytes", output.len),
                    ));
                }
                let capture = map_one(fd, BUF_TYPE_CAPTURE_MPLANE)?;
                queue(fd, BUF_TYPE_CAPTURE_MPLANE, 0)?;
                for typ in [BUF_TYPE_OUTPUT_MPLANE, BUF_TYPE_CAPTURE_MPLANE] {
                    let mut t = typ as i32;
                    xioctl(fd, VIDIOC_STREAMON, &mut t, "stream on")?;
                }
                Ok((output, capture, bytesperline, rows, sizeimage))
            };
            match setup() {
                Ok((output, capture, bytesperline, rows, sizeimage)) => Ok(Self {
                    fd,
                    width: width as usize,
                    height: height as usize,
                    frame_size,
                    bytesperline,
                    rows,
                    sizeimage,
                    output,
                    capture,
                }),
                Err(e) => {
                    // SAFETY: fd is ours and open.
                    unsafe { libc::close(fd) };
                    Err(e)
                }
            }
        }
    }

    impl JpegEncode for HwJpeg {
        fn encode(&mut self, raw: &[u8]) -> Result<Bytes> {
            if raw.len() != self.frame_size {
                return Err(Error::new(
                    ErrorKind::InvalidData,
                    format!(
                        "raw frame is {} bytes, expected {}",
                        raw.len(),
                        self.frame_size
                    ),
                ));
            }
            // SAFETY: the output mapping is at least sizeimage bytes (checked in open) and
            // only this thread touches it while the buffer is dequeued.
            let input = unsafe { std::slice::from_raw_parts_mut(self.output.ptr, self.sizeimage) };
            repack_i420(
                raw,
                i420_stride(self.width as u32),
                input,
                self.bytesperline,
                self.rows,
                self.width,
                self.height,
            );
            queue_used(self.fd, BUF_TYPE_OUTPUT_MPLANE, 0, self.sizeimage as u32)?;
            wait_readable(self.fd, 1000)?;
            let used = dequeue(self.fd, BUF_TYPE_CAPTURE_MPLANE)? as usize;
            // SAFETY: the driver wrote `used` bytes into the capture mapping.
            let jpeg =
                unsafe { std::slice::from_raw_parts(self.capture.ptr, used.min(self.capture.len)) };
            let frame = Bytes::copy_from_slice(jpeg);
            queue(self.fd, BUF_TYPE_CAPTURE_MPLANE, 0)?;
            dequeue(self.fd, BUF_TYPE_OUTPUT_MPLANE)?;
            Ok(frame)
        }
    }

    impl Drop for HwJpeg {
        fn drop(&mut self) {
            for typ in [BUF_TYPE_OUTPUT_MPLANE, BUF_TYPE_CAPTURE_MPLANE] {
                let mut t = typ as i32;
                let _ = xioctl(self.fd, VIDIOC_STREAMOFF, &mut t, "stream off");
            }
            // SAFETY: fd is ours; mappings are dropped after this (field order).
            unsafe { libc::close(self.fd) };
        }
    }

    fn set_format(
        fd: i32,
        typ: u32,
        pixelformat: u32,
        width: u32,
        height: u32,
        bytesperline: u32,
        sizeimage: usize,
    ) -> Result<(usize, usize)> {
        let mut pix = PixFormatMplane {
            width,
            height,
            pixelformat,
            field: FIELD_NONE,
            num_planes: 1,
            ..Default::default()
        };
        pix.plane_fmt[0] = PlanePixFormat {
            sizeimage: sizeimage as u32,
            bytesperline,
            reserved: [0; 6],
        };
        let mut format = Format {
            typ,
            fmt: FormatUnion { raw: [0; 200] },
        };
        format.fmt.pix_mp = pix;
        xioctl(fd, VIDIOC_S_FMT, &mut format, "set format")?;
        // SAFETY: S_FMT on a multi-planar type fills pix_mp.
        let plane = unsafe { format.fmt.pix_mp.plane_fmt[0] };
        Ok((plane.bytesperline as usize, plane.sizeimage as usize))
    }

    fn map_one(fd: i32, typ: u32) -> Result<Mapping> {
        let mut req = RequestBuffers {
            count: 1,
            typ,
            memory: MEMORY_MMAP,
            ..Default::default()
        };
        xioctl(fd, VIDIOC_REQBUFS, &mut req, "request buffers")?;
        let mut plane = Plane::default();
        let mut buf = Buffer {
            typ,
            memory: MEMORY_MMAP,
            m: &mut plane as *mut Plane as u64,
            length: 1,
            ..Default::default()
        };
        xioctl(fd, VIDIOC_QUERYBUF, &mut buf, "query buffer")?;
        let len = plane.length as usize;
        let offset = (plane.m & 0xffff_ffff) as libc::off_t;
        // SAFETY: mapping the driver's buffer at the offset it reported.
        let ptr = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                len,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED,
                fd,
                offset,
            )
        };
        if ptr == libc::MAP_FAILED {
            let e = Error::last_os_error();
            return Err(Error::new(e.kind(), format!("mmap: {e}")));
        }
        Ok(Mapping {
            ptr: ptr.cast(),
            len,
        })
    }

    fn queue(fd: i32, typ: u32, index: u32) -> Result<()> {
        queue_used(fd, typ, index, 0)
    }

    fn queue_used(fd: i32, typ: u32, index: u32, bytesused: u32) -> Result<()> {
        let mut plane = Plane {
            bytesused,
            ..Default::default()
        };
        let mut buf = Buffer {
            index,
            typ,
            memory: MEMORY_MMAP,
            field: FIELD_NONE,
            m: &mut plane as *mut Plane as u64,
            length: 1,
            ..Default::default()
        };
        xioctl(fd, VIDIOC_QBUF, &mut buf, "queue buffer")
    }

    /// Dequeue one buffer; returns the plane's bytesused.
    fn dequeue(fd: i32, typ: u32) -> Result<u32> {
        let mut plane = Plane::default();
        let mut buf = Buffer {
            typ,
            memory: MEMORY_MMAP,
            m: &mut plane as *mut Plane as u64,
            length: 1,
            ..Default::default()
        };
        xioctl(fd, VIDIOC_DQBUF, &mut buf, "dequeue buffer")?;
        Ok(plane.bytesused)
    }

    fn wait_readable(fd: i32, timeout_ms: i32) -> Result<()> {
        let mut pfd = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        // SAFETY: one valid pollfd.
        let rc = unsafe { libc::poll(&mut pfd, 1, timeout_ms) };
        match rc {
            0 => Err(Error::new(
                ErrorKind::TimedOut,
                "hardware encoder: no JPEG within 1 s",
            )),
            n if n < 0 => Err(Error::last_os_error()),
            _ => Ok(()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn i420_sizes_match_rpicam_vid_on_device() {
        // Measured on kube-node02 (Pi 3, OV5647): 640 is 64-aligned, 800 pads to 832.
        assert_eq!(i420_frame_size(640, 480), 460_800);
        assert_eq!(i420_frame_size(800, 600), 748_800);
        assert_eq!(i420_stride(800), 832);
    }

    #[test]
    fn repack_moves_each_plane_to_the_encoder_layout() {
        let (w, h, ss) = (4usize, 2usize, 6usize);
        // camera layout: Y 6x2, U 3x1, V 3x1; padding bytes are 0xEE.
        let src = [
            1, 2, 3, 4, 0xEE, 0xEE, 5, 6, 7, 8, 0xEE, 0xEE, // Y
            9, 10, 0xEE, // U
            11, 12, 0xEE, // V
        ];
        let (ds, rows) = (8usize, 4usize);
        let mut dst = vec![0u8; ds * rows * 3 / 2];
        repack_i420(&src, ss, &mut dst, ds, rows, w, h);
        assert_eq!(&dst[0..4], &[1, 2, 3, 4]);
        assert_eq!(&dst[8..12], &[5, 6, 7, 8]);
        assert_eq!(&dst[32..34], &[9, 10]); // U at ds*rows
        assert_eq!(&dst[40..42], &[11, 12]); // V at ds*rows + ds/2*rows/2
        assert_eq!(dst.iter().filter(|&&b| b == 0xEE).count(), 0);
    }

    #[test]
    fn probe_finds_the_encoder_by_name() {
        let dir = std::env::temp_dir().join(format!("hwjpeg-probe-{}", std::process::id()));
        for (node, name) in [
            ("video10", "bcm2835-codec-decode"),
            ("video31", "bcm2835-codec-encode_image"),
            ("video0", "unicam-image"),
        ] {
            std::fs::create_dir_all(dir.join(node)).unwrap();
            std::fs::write(dir.join(node).join("name"), format!("{name}\n")).unwrap();
        }
        assert_eq!(probe(&dir), Some(PathBuf::from("/dev/video31")));
        std::fs::remove_dir_all(dir.join("video31")).unwrap();
        assert_eq!(probe(&dir), None);
        std::fs::remove_dir_all(&dir).unwrap();
        assert_eq!(probe(Path::new("/nonexistent")), None);
    }
}
