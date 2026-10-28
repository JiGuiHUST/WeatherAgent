"""Pin browser runtime assets locally so the UI doesn't depend on a CDN."""
from pathlib import Path
import requests
root=Path(__file__).resolve().parents[1]/"static"/"vendor"
root.mkdir(parents=True,exist_ok=True)
assets={"leaflet.js":"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        "leaflet.css":"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "bootstrap.min.css":"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
        "bootstrap.bundle.min.js":"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
        "bootstrap-icons.min.css":"https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        "fonts/bootstrap-icons.woff2":"https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff2",
        "fonts/bootstrap-icons.woff":"https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/bootstrap-icons.woff",
        "images/layers.png":"https://unpkg.com/leaflet@1.9.4/dist/images/layers.png",
        "images/layers-2x.png":"https://unpkg.com/leaflet@1.9.4/dist/images/layers-2x.png"}
for name,url in assets.items():
    path=root/name
    if path.exists(): continue
    r=requests.get(url,timeout=30);r.raise_for_status()
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(r.content)
    print(name,len(r.content))
