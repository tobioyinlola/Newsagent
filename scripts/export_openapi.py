"""Write the FastAPI OpenAPI schema to frontend/openapi.json (input to the generated TS client)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import app  # noqa: E402

out = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
