"""Vision integration tests land after the local-attachment migration."""

import pytest

pytestmark = pytest.mark.skip(reason="Vision path not migrated yet")
