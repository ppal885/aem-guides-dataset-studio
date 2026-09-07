# VM setup instructions

The current deployment is dashboard-only: systemd runs the canonical UAC backend, and Nginx serves the read-only evaluation dashboard plus API/MCP proxies on port `4502`.

Use [QUICK_START_FRESH_VM.md](QUICK_START_FRESH_VM.md) for the supported installation and verification commands. Use [VM_QUICK_REFERENCE.md](VM_QUICK_REFERENCE.md) for routine operations and [DOCKER.md](DOCKER.md) only when the backend-container workflow is required.

Do not install or start the retired React/Vite frontend or a frontend container.
