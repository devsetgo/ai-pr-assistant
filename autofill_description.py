#!/usr/bin/env python3
"""Entry point kept at the repo root for `entrypoint.sh` / Docker `ENTRYPOINT`
compatibility; the actual implementation lives in the `pr_description` package.
"""

import sys

from pr_description.cli import main

if __name__ == "__main__":
    sys.exit(main())
