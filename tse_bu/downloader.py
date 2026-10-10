"""Download robusto de arquivos grandes com ranges paralelos e retentativas."""

import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import USER_AGENT


def _fetch_range(url: str, start: int, end: int, path: str,
                 max_retries: int = 6) -> int:
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = resp.read()
            if len(data) != end - start + 1:
                raise IOError(f"chunk incompleto: {len(data)} != {end-start+1}")
            with open(path, "r+b") as f:
                f.seek(start)
                f.write(data)
            return len(data)
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return 0  # pragma: no cover


def download(url: str, dest: str, workers: int = 16, force: bool = False) -> str:
    """Baixa `url` para `dest` usando ranges paralelos. Retorna o caminho."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        size = int(resp.headers["Content-Length"])

    if os.path.exists(dest) and os.path.getsize(dest) == size and not force:
        print(f"[ok] já baixado: {dest} ({size/1e6:.1f} MB)")
        return dest

    with open(dest, "wb") as f:
        f.truncate(size)

    bounds = [(i * size // workers, (i + 1) * size // workers - 1)
              for i in range(workers)]
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda b: _fetch_range(url, b[0], b[1], dest), bounds))
    dt = time.time() - t0

    assert os.path.getsize(dest) == size, "arquivo corrompido, reexecute"
    print(f"[ok] download concluído em {dt:.0f}s: {dest} ({size/1e6:.1f} MB)")
    return dest
