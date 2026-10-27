#!/usr/bin/env python3
"""Start the local llama.cpp model for direct Python integrations."""

import time

try:
    from .extractor import log, log_configuration, start_llama, stop_llama
except ImportError:
    from extractor import log, log_configuration, start_llama, stop_llama

if __name__ == "__main__":
    log("Starting local model for direct Python integrations")
    log_configuration()
    llama_process = start_llama()
    try:
        log("Ready: import extract_text from app.extractor in your service")
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log("Shutdown signal received")
    finally:
        stop_llama(llama_process)
