"""Stand-in for libcamera's Python bindings (conformance tests only)."""


class Transform:
    def __init__(self, hflip: bool = False, vflip: bool = False) -> None:
        self.hflip, self.vflip = hflip, vflip
