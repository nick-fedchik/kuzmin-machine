"""Shared writer for the golden files: deterministic gzip (no timestamp, no file name)."""

import gzip
import io
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def open_gz_text(path):
    """Yield a UTF-8 text file whose content is stored as reproducible gzip."""
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="\n") as text:
                yield text


def write_gz_text(path, text):
    with open_gz_text(path) as fh:
        fh.write(text)


def compress_existing(path):
    """Replace PATH (plain JSON) by PATH.gz; returns the new path."""
    path = Path(path)
    target = path.with_name(path.name + ".gz")
    write_gz_text(target, path.read_text(encoding="utf-8"))
    return target
