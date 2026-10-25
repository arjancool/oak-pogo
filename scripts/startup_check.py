"""Start OAK once in a temporary data directory and ask whether it is ready.

Used by CI on Windows (audit F09 of 25 October): there the IANA time zones come from the tzdata
package, because Windows does not ship them.

    cd backend && .venv/Scripts/python ../scripts/startup_check.py
"""

import os
import tempfile

os.environ["OAK_DATA_DIR"] = tempfile.mkdtemp()
os.environ["OAK_GAMEDATA_AUTO_UPDATE"] = "false"
os.environ["OAK_EVENTS_AUTO_UPDATE"] = "false"

from fastapi.testclient import TestClient

from app.main import create_app

with TestClient(create_app()) as client:
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
print("OAK start op dit platform")
