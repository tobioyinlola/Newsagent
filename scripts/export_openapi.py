"""Write the FastAPI OpenAPI schema to frontend/openapi.json and frontend/admin/openapi.json (inputs to the generated TS clients)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import app  # noqa: E402

root = Path(__file__).resolve().parents[1]
text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
for target in ("frontend", "frontend/admin"):
    out = root / target / "openapi.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}")
