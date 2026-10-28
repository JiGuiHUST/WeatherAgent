"""Read an API key from stdin without printing it or accepting it in argv."""
import sys
from pathlib import Path

import getpass
key = getpass.getpass("DeepSeek API key (hidden): ").strip()
if not key.startswith("sk-") or len(key) < 20:
    raise SystemExit("Invalid API key format")
path = Path(__file__).resolve().parents[1] / ".env"
existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
names = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL"}
lines = [line for line in existing if line.partition("=")[0].strip() not in names]
lines += ["OPENAI_API_KEY=" + key, "OPENAI_BASE_URL=https://api.deepseek.com", "LLM_MODEL=deepseek-flash"]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("DeepSeek configured in ignored .env; secret not displayed.")
