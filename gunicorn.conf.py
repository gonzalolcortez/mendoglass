import os

# Bind to the port Render.com assigns via the PORT environment variable.
# Falls back to 10000 (Render's default) when PORT is not set.
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# Use 2 workers; 1 is enough for the Render free tier but 2 gives basic
# redundancy without exceeding the memory limit.
try:
    workers = int(os.environ.get("WEB_CONCURRENCY", 2))
except (TypeError, ValueError):
    workers = 2

# Synchronous worker – no extra dependencies required.
worker_class = "sync"

# 120 s keeps long-running DB operations alive without timing out.
timeout = 120

# Graceful shutdown window.
graceful_timeout = 30

# Keep-alive for load-balancer connections.
keepalive = 5

# Write logs to stdout/stderr so Render can capture them.
accesslog = "-"
errorlog = "-"
loglevel = "info"
