# GPU Setup

Enable GPU support for Styx Portal instances.

## Host Prerequisites

### NVIDIA (CUDA)

Install on the Docker host:
1. [NVIDIA GPU drivers](https://docs.nvidia.com/datacenter/tesla/tesla-installation-notes/)
2. [NVIDIA Container Runtime](https://github.com/NVIDIA/nvidia-container-runtime)

Example (Ubuntu/Debian):
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### AMD / Intel (DRI)

GPU is accessible via `/dev/dri` (read-only device node on the host). The backend container already maps this:
```yaml
devices:
  - /dev/dri:/dev/dri
```

## Environment Configuration

Set these in `.env` before first start:

```bash
# Find your GIDs on the host
getent group video render

# Example output:
# video:x:44:
# render:x:992:

# Set in .env
VIDEO_GID=44
RENDER_GID=992
```

Wrong GID values won't break the portal — the container will start successfully but GPU won't be accessible to the backend. Correct the GIDs and restart.

## Enabling GPU on a Template

In the admin template editor, set:

```json
{
  "name": "desktop-with-gpu",
  "image": "your-selkies-image",
  "gpu_enabled": true,
  "gpu_count": 1
}
```

Fields:
- **gpu_enabled** (bool): whether this template supports GPU acceleration
- **gpu_count** (int): number of GPUs to allocate per instance (default 1)

## Verifying GPU Inside a Desktop

Once you launch an instance from a GPU-enabled template:

1. Open the desktop in the browser
2. Open a terminal and run:
   ```bash
   nvidia-smi    # NVIDIA/CUDA
   # or
   lspci | grep VGA  # AMD/Intel
   # or
   ls -la /dev/dri  # All platforms
   ```

## Troubleshooting

### Device not found

**Symptom:** `nvidia-smi` shows "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver" or `/dev/dri` is missing.

**Fix:**
1. Verify the host has drivers installed: `nvidia-smi` (on the Docker host)
2. Check backend GIDs: `docker exec styx-backend id | grep video,render` — must list those groups
3. Correct GIDs in `.env` if needed and restart

### Driver mismatch

**Symptom:** `nvidia-smi` works on the host but fails inside the container.

**Fix:** Ensure the container image includes CUDA libraries matching the host driver version (usually bundled in the Selkies base image). Rebuild the image if needed.

### GID wrong

**Symptom:** GPU works on the host but not in instances; `/dev/dri` exists but is inaccessible.

**Fix:**
1. Run on the host: `getent group video render` — note the correct GIDs
2. Update `.env` with correct GIDs
3. Restart the backend: `docker compose restart backend`
