"""Weather provider contract. Live data never falls back to synthetic weather."""
from services.live_weather import fetch

class WeatherProvider:
    def hourly(self,lat,lon,date_iso):
        raise NotImplementedError
    def describe(self):
        return {"kind":type(self).__name__}

class OpenMeteoProvider(WeatherProvider):
    def __init__(self,**kwargs):
        pass
    def hourly(self,lat,lon,date_iso):
        return fetch(lat,lon,date_iso)["hours"]
    def describe(self):
        return {"kind":"open-meteo","cache_ttl_s":1800,"unit_wind":"m/s"}

class InjectedProvider(WeatherProvider):
    """Explicit, labeled test/simulation input. Never a live fallback."""
    def __init__(self,rows,label="injected"):
        self.rows=list(rows or []);self.label=label
    def hourly(self,lat,lon,date_iso):
        if not self.rows:
            raise ValueError("InjectedProvider has no data")
        return self.rows
    def describe(self):
        return {"kind":self.label,"hours":len(self.rows)}
