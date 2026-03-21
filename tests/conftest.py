import os
import sys
from pathlib import Path


def _add_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_add_path(Path(__file__).resolve().parents[1])
hermes_repo = Path(os.environ.get('HERMES_AGENT_REPO', '~/.hermes/hermes-agent')).expanduser()
if hermes_repo.exists():
    _add_path(hermes_repo)
