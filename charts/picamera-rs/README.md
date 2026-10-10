# picamera-rs chart

Deploys `kubedge1/picamera-rs`, the Rust implementation of the camera stream, with the same
contract and the same values as [`charts/picamera`](../picamera): a values file written for
one renders with the other. Differences: the chart and resource names (`<release>-picamera-rs`),
the image, and a default memory request/limit sized for the Rust image.

Choose this chart on memory-constrained camera nodes; choose `charts/picamera` for the
Python implementation.

**One camera, one owner.** libcamera lets one process own a camera. Both charts can be
installed in the same namespace (give them different `service.nodePort` values), but not
on the same camera node at the same time — split them with `nodeSelector`, or switch:

    helm uninstall picamera
    helm install picamera-rs charts/picamera-rs -f <same values>
