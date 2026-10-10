"""Download robusto de arquivos grandes com ranges paralelos e retentativas."""

import logging
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import USER_AGENT

logger = logging.getLogger(__name__)


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
    """Baixa `url` para `dest` usando ranges paralelos. Retorna o caminho.

    O download é feito para um arquivo temporário `<dest>.part` e só é
    promovido ao destino final (rename atômico) após a validação do
    tamanho — assim um arquivo corrompido/interrompido (ex.: cheio de
    zeros) nunca fica no cache como se fosse válido. Se a validação
    falhar, o `.part` é apagado e o download será refeito na próxima
    execução.
    """
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        size = int(resp.headers["Content-Length"])

    if os.path.exists(dest) and not force:
        if os.path.getsize(dest) == size:
            logger.info("já baixado: %s (%.1f MB)", dest, size / 1e6)
            return dest
        logger.warning("cache inválido (tamanho diverge do remoto), "
                       "rebaixando: %s", dest)
        os.remove(dest)

    part = dest + ".part"
    if os.path.exists(part):
        logger.warning("removendo download incompleto anterior: %s", part)
        os.remove(part)

    try:
        with open(part, "wb") as f:
            f.truncate(size)

        bounds = [(i * size // workers, (i + 1) * size // workers - 1)
                  for i in range(workers)]
        t0 = time.time()
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(lambda b: _fetch_range(url, b[0], b[1], part), bounds))
        dt = time.time() - t0

        if os.path.getsize(part) != size:
            raise IOError(f"download incompleto: "
                          f"{os.path.getsize(part)} != {size}")
    except Exception:
        if os.path.exists(part):
            os.remove(part)
        logger.error("download falhou; '%s' removido e será rebaixado "
                     "na próxima execução", part)
        raise

    os.replace(part, dest)
    logger.info("download concluído em %.0fs: %s (%.1f MB)", dt, dest,
                size / 1e6)
    return dest
