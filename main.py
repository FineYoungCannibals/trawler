import multiprocessing
import os

# Must be set before any ML libraries are imported.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

# Pre-start the multiprocessing resource tracker NOW, while the process has very
# few file descriptors open. If we don't, tqdm will try to start it later from a
# worker thread while Textual has many fds open, causing spawnv_passfds to fail
# with "bad value(s) in fds_to_keep".
_lock = multiprocessing.RLock()
del _lock

from trawler.app import TrawlerApp


def main() -> None:
    TrawlerApp().run()


if __name__ == "__main__":
    main()
