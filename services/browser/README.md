# WebSift browser service

The service always launches each browser context through its internal validating forward proxy; there is no direct-egress mode. Run exactly one Uvicorn worker per container and give the container adequate shared memory (`shm_size: 1gb` or `--shm-size=1g`).

Required when binding beyond loopback:

```env
BROWSER_HOST=0.0.0.0
BROWSER_TOKEN=replace-with-a-long-random-secret
BROWSER_ALLOWED_PORTS=443
BROWSER_ALLOW_HTTP=false
BROWSER_ALLOWED_DOMAINS=
BROWSER_DENIED_DOMAINS=
```

Other settings include `BROWSER_PORT`, `BROWSER_CONCURRENCY`, `BROWSER_MAX_REQUEST_BYTES`, `BROWSER_MAX_TIMEOUT_SECONDS`, `BROWSER_MAX_HTML_BYTES`, and `BROWSER_PROXY_{CONNECT,IO,HEADER}_TIMEOUT`. The internal proxy rejects every DNS answer set containing a non-global address, pins outbound connections to a validated address, and cannot reach private service-network endpoints.

Build with `docker build -t websift-browser services/browser`. The image installs Camoufox at build time, runs non-root, exposes only the HTTP render API, and publishes no Playwright endpoint.
