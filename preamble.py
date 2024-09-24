
import os
from pathlib import Path
import shutil
from typing import cast


site_packages: Path

if __name__ == "__main__":
    for path in (cast(Path, site_packages)).iterdir():
        if path.name.startswith("numpy"):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                os.remove(path)