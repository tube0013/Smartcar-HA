"""Update the manifest file."""

import json
from pathlib import Path
import sys


def update_manifest():
    """Update the manifest file."""
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in {"--version", "-V"}:
            version = sys.argv[index + 1]

    path = Path(f"{Path.cwd()}/custom_components/smartcar/manifest.json")

    with path.open(encoding="utf-8") as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


update_manifest()
