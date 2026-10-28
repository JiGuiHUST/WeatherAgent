"""Compatibility facade over the selected real weather source."""
from datetime import timedelta
from services.live_weather import summary, now,provider_status
from utils.common import nearest_run_time
MAX_FORECAST_DAYS = 3 if provider_status()['active']=='weathercn' else 16
MAX_FORECAST_HOURS = 72 if provider_status()['active']=='weathercn' else 16 * 24

def get_weather_summary(target_dt, bbox_str):
    return summary(target_dt, bbox_str)

def check_forecast_availability(target_dt, run_dt=None):
    current = now().replace(tzinfo=None)
    run = run_dt or current
    run = run.replace(tzinfo=None)
    target = target_dt.replace(tzinfo=None)
    delta = target - run
    maximum = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=MAX_FORECAST_DAYS)
    return dict(within_range=current.date() <= target.date() < maximum.date(),
                hours_ahead=int(delta.total_seconds() // 3600), run_time=run, max_target=maximum,
                days_over=max(0,(target.date()-maximum.date()).days+1), is_past=target.date()<current.date(),
                limit_hours=MAX_FORECAST_HOURS, limit_days=MAX_FORECAST_DAYS)
