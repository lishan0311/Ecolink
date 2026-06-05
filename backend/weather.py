import requests
from datetime import datetime, timedelta
import json
 
LATITUDE = 3.1073
LONGITUDE = 101.6067
TIMEZONE = "Asia/Kuala_Lumpur"
 
_weather_cache = None
_cache_time = None
CACHE_DURATION = 3600  

WEATHER_MAP = {
    "Berjerebu": "Hazy",
    "Tiada hujan": "Sunny",
    "Hujan": "Rainy",
    "Hujan di beberapa tempat": "Scattered Rain",
    "Hujan di satu dua tempat": "Isolated Rain",
    "Hujan di satu dua tempat di kawasan pantai": "Isolated Rain (Coastal)",
    "Hujan di satu dua tempat di kawasan pedalaman": "Isolated Rain (Inland)",
    "Ribut petir": "Thunderstorms",
    "Ribut petir di beberapa tempat": "Scattered Thunderstorms",
    "Ribut petir di beberapa tempat di kawasan pedalaman": "Scattered Thunderstorms (Inland)",
    "Ribut petir di satu dua tempat": "Isolated Thunderstorms",
    "Ribut petir di satu dua tempat di kawasan pantai": "Isolated Thunderstorms (Coastal)",
    "Ribut petir di satu dua tempat di kawasan pedalaman": "Isolated Thunderstorms (Inland)"
}
 
def get_weather_forecast():
    global _weather_cache, _cache_time
    
    now = datetime.now()
    
    if _weather_cache and _cache_time:
        elapsed = (now - _cache_time).seconds
        if elapsed < CACHE_DURATION:
            return _weather_cache
    
    try:
        url = "https://api.data.gov.my/weather/forecast?contains=Ds058@location__location_id&limit=7"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        # Sort data by date ascending
        data.sort(key=lambda x: x["date"])
        
        forecast = []
        for item in data:
            morning = WEATHER_MAP.get(item.get("morning_forecast", "Tiada hujan"), "Sunny")
            afternoon = WEATHER_MAP.get(item.get("afternoon_forecast", "Tiada hujan"), "Sunny")
            night = WEATHER_MAP.get(item.get("night_forecast", "Tiada hujan"), "Sunny")
            summary = WEATHER_MAP.get(item.get("summary_forecast", "Tiada hujan"), "Sunny")
            
            # Estimate solar percentage based on summary/afternoon
            solar_pct = 80
            if "Rain" in summary or "Thunderstorm" in summary:
                solar_pct = 30
            elif "Cloudy" in summary or "Hazy" in summary:
                solar_pct = 50
            if "Rain" in afternoon or "Thunderstorm" in afternoon:
                solar_pct -= 20
                
            # Emoji mapping
            emoji = "☀️"
            if "Rain" in summary: emoji = "🌧️"
            elif "Thunderstorm" in summary: emoji = "⛈️"
            elif "Cloudy" in summary: emoji = "☁️"
            elif "Hazy" in summary: emoji = "🌫️"
            
            forecast.append({
                "date": item["date"],
                "condition": summary.lower().replace(" ", "_"),
                "emoji": emoji,
                "label": summary,
                "morning": morning,
                "afternoon": afternoon,
                "night": night,
                "temp_min": item.get("min_temp", 24),
                "temp_max": item.get("max_temp", 33),
                "solar_pct": max(10, min(100, solar_pct))
            })
            
        if not forecast:
            raise Exception("Empty data from API")
        
        _weather_cache = forecast
        _cache_time = now
        print(f"Weather fetched from MET Malaysia: {len(forecast)} days")
        return forecast
        
    except Exception as e:
        print(f"Weather API error: {e}, using fallback data")
        return get_fallback_weather()
 
def get_fallback_weather():
    today = datetime.now()
    conditions = ["sunny","sunny","partly_cloudy","rainy","cloudy","partly_cloudy","sunny"]
    emojis = {"sunny":"☀️","partly_cloudy":"🌤️","rainy":"🌧️","cloudy":"☁️"}
    labels = {"sunny":"Sunny","partly_cloudy":"Partly Cloudy","rainy":"Rainy","cloudy":"Cloudy"}
    solar = {"sunny":85,"partly_cloudy":55,"rainy":15,"cloudy":30}
    
    return [{
        "date": (today + timedelta(days=i)).strftime('%Y-%m-%d'),
        "condition": conditions[i],
        "emoji": emojis[conditions[i]],
        "label": labels[conditions[i]],
        "cloud_pct": {"sunny":15,"partly_cloudy":45,"rainy":80,"cloudy":75}[conditions[i]],
        "rain_mm": {"sunny":0,"partly_cloudy":1,"rainy":12,"cloudy":2}[conditions[i]],
        "solar_pct": solar[conditions[i]],
    } for i in range(7)]
 
def get_solar_advice(forecast, current_solar_pct, ldr_covered=False):
    advice = []
    today_str = datetime.now().strftime('%Y-%m-%d')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    today_weather = next((f for f in forecast if f["date"] == today_str), None)
    tomorrow_weather = next((f for f in forecast if f["date"] == tomorrow_str), None)
    
    if ldr_covered or current_solar_pct < 25:
        if today_weather and today_weather["condition"] in ["rainy","cloudy"]:
            advice.append({
                "type": "solar_drop_forecast",
                "priority": "high",
                "title": "☁️ As forecasted — solar dropping",
                "message": f"Today is {today_weather['label']}. Solar output has dropped to {current_solar_pct}%. Reschedule heavy loads to tomorrow if it's sunny.",
                "action": "reschedule"
            })
        else:
            advice.append({
                "type": "solar_drop_realtime",
                "priority": "medium",
                "title": "⛅ Temporary cloud cover",
                "message": f"Solar output dropped to {current_solar_pct}%. Pause EV charging until solar recovers.",
                "action": "pause_charging"
            })
    
    elif current_solar_pct > 60:
        advice.append({
            "type": "solar_surplus",
            "priority": "medium",
            "title": "☀️ Solar surplus now",
            "message": f"Solar at {current_solar_pct}%. Best time to run washer, dryer, or charge EV. Save RM 0.85.",
            "action": "use_now"
        })
    
    if tomorrow_weather and tomorrow_weather["condition"] in ["rainy","cloudy","drizzle"]:
        if current_solar_pct > 40:  
            advice.append({
                "type": "weather_proactive",
                "priority": "high",
                "title": f"🌧️ Tomorrow: {tomorrow_weather['label']} forecast",
                "message": f"Solar output tomorrow expected to drop {round(100 - tomorrow_weather['solar_pct'])}%. Complete laundry and EV charging TODAY to maximize solar savings.",
                "action": "charge_today",
                "tomorrow_solar": tomorrow_weather["solar_pct"]
            })
    
    return advice

def get_weather_warnings():
    """Mock weather warnings for demonstration."""
    return [
        {
            "id": "W1",
            "type": "rain",
            "title": "Strong Rain Warning",
            "message": "Heavy rain expected between 4:00 PM and 6:00 PM. Avoid using high-power appliances during this period.",
            "severity": "medium",
            "timestamp": datetime.now().isoformat()
        }
    ]

def get_earthquakes():
    """Mock earthquake data (common for MET Malaysia API)."""
    return [
        {
            "id": "E1",
            "location": "Nias Region, Indonesia",
            "magnitude": "4.2",
            "depth": "10km",
            "time": datetime.now().strftime("%I:%M %p"),
            "distance": "450km from Port Dickson"
        }
    ]
