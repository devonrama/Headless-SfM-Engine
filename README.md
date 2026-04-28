# Headless-SfM Engine

An asynchronous, stateless REST API microservice engineered to orchestrate the COLMAP Structure-from-Motion (SfM) pipeline. Built with FastAPI, designed for enterprise geospatial integration and automated cloud photogrammetry workflows.

## Architectural Capabilities

This engine transitions heavy C++ photogrammetry binaries into a multi-tenant, web-accessible microservice with strict hardware resource management:

* **Asynchronous I/O Orchestration:** Utilizes FastAPI's background tasks and `asyncio` to execute intensive SIFT extraction and Bundle Adjustment non-blocking.
* **VRAM Saturation Defense:** Implements pre-computation dynamic downscaling via Pillow (max 1024px) to guarantee zero Out-of-Memory (OOM) failures on constrained hardware (e.g., RTX 3060 6GB) during simultaneous processing.
* **Subprocess Deadlock Bypass:** Bypasses Python's internal `stdout/stderr` buffer limits via OS-level shell redirection, eliminating pipeline hangs during massive logging outputs.
* **Dynamic Payload Flattening:** Natively tolerates asymmetrical client inputs by recursively scanning, extracting, and flattening nested `.zip` directory structures before computation.
* **Stateless State Tracking:** Infers processing status deterministically via physical file existence and regex-based log parsing, eliminating the need for redundant stateful database tracking.

## System Execution Demonstration

The following video demonstrates the API intercepting a nested `.zip` spatial image payload, executing the async SfM pipeline, and returning the deterministic spatial coordinates (points and camera extrinsics).

<video src="HSE%20demo.mp4" controls="controls" width="100%"></video>

## Developer
**Devon Rama Wikunanda**
Geodesy Engineering, Universitas Diponegoro
NIM: 21110124130099
