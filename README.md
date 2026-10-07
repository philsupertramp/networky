# Networky

Networky is a Python application built with Python 3.13. The project includes containerization support via Docker for amd64, arm64 and arm/7 targets as well as deployment configurations using Helm.

## Application Overview

The core application in `app.py` is a network monitoring service. It runs a background loop that periodically executes ICMP ping commands against configured IPv4 and IPv6 targets to measure packet loss and latency. All network measurements are stored locally in an SQLite database.

The application also runs an HTTP server on port 8080 to expose the collected data.

### Configuration

The service is configured using environment variables:
* `DATABASE_PATH`: File path for the SQLite database.
* `INTERVAL_SECONDS`: The wait time in seconds between measurement cycles.
* `PING_COUNT`: The number of ping packets to send per cycle.
* `PING_TARGETS_V4`: Comma separated list of IPv4 addresses to monitor.
* `PING_TARGETS_V6`: Comma separated list of IPv6 addresses to monitor.

### API Endpoints

The web server provides three JSON endpoints:
* `/healthz`: Returns a standard healthy status.
* `/latest`: Returns the most recent measurement for every tracked target.
* `/history`: Returns historical network data and accepts a `limit` query parameter to control the number of records returned.

## Project Structure

* `app.py`: Main application code.
* `pyproject.toml` and `uv.lock`: Dependency management using uv.
* `.python-version`: Specifies Python 3.13.
* `Dockerfile`: Container configuration.
* `deployment/`: Helm chart directory containing values and deployment templates.
* `.github/workflows/docker-image.yaml`: GitHub Actions workflow for building the Docker image.

## Local Development

This project uses `uv` for fast Python package management. 

1. Ensure Python 3.13 and `uv` are installed on your system.
2. Install dependencies:
    ```bash
    uv sync
    ```
3. Run the application:
    ```bash
    python app.py
    ```

## Docker

To build the Docker image locally:

```bash
docker build -t networky .

```

## Deployment

The application is deployed to a Kubernetes cluster using Helm.

Navigate to the root directory and run:

```bash
helm install networky ./deployment

```

Configuration can be modified by editing the `deployment/values.yaml` file.
