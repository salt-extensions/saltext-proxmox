"""
Wrapper around pre-commit that drops warnings about unknown config keys.

The pre-commit configuration can contain extensions that are only
supported by prek, e.g. ``priority``. pre-commit ignores them, but
warns on each invocation. It force-resets its logger's level at
runtime, so a logging filter in the calling process is the only way
to suppress this (there is no CLI/environment knob).
"""

import logging
import sys

from pre_commit.main import main


def _drop_unexpected_keys_warning(record):
    return "Unexpected key(s) present" not in record.getMessage()


if __name__ == "__main__":
    logging.getLogger("pre_commit").addFilter(_drop_unexpected_keys_warning)
    sys.exit(main())
