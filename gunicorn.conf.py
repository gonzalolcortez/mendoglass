import os

bind = "0.0.0.0:" + os.environ.get("PORT", "10000")
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
timeout = 120
accesslog = "-"
errorlog = "-"
