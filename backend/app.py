from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from datetime import datetime
import json
import os

from analytics import (
    get_current_month_kwh, get_current_bill,
    predict_tier_jump, detect_anomaly, get_usage_trend,
    save_live_reading, add_notification, get_unread_notifications,
    get_standby_power, get_community_leaderboard, get_virtual_scheduling_advice,
    get_community_stats
)
from weather import get_weather_forecast, get_solar_advice, get_weather_warnings, get_earthquakes

app = Flask(__name__, 
            template_folder='../frontend/templates',
            static_folder='../frontend/static')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'ecolink.db')

# Global state for simulation/ESP32 data
latest_data = {
    "house_a": {"current_power": 0, "solar_percent": 50, "kwh": 156.3},
    "house_b": {"current_power": 0, "kwh": 275.0, "anomaly": False},
    "house_c": {"current_power": 0, "ev_charging": False, "kwh": 203.1},
    "live_sensor": {"real_power": 0},
    "ldr_covered": False,
    "last_update": datetime.now().isoformat(),
    "notifications_sent": {
        "tier_280": False,
        "tier_290": False,
        "anomaly_active": False
    }
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/community')
def community():
    return render_template('community.html')

@app.route('/alerts')
def alerts():
    return render_template('alerts.html')

# ── ESP32 Data Endpoint ──
@app.route('/api/data', methods=['POST'])
def receive_data():
    global latest_data
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        # Update latest state
        if "house_a" in data: latest_data["house_a"].update(data["house_a"])
        if "house_b" in data: latest_data["house_b"].update(data["house_b"])
        if "house_c" in data: latest_data["house_c"].update(data["house_c"])
            
        latest_data["last_update"] = datetime.now().isoformat()
        
        solar_pct = latest_data["house_a"].get("solar_percent", 100)
        latest_data["ldr_covered"] = solar_pct < 25
        
        current_kwh = latest_data["house_b"].get("kwh", 0)
        current_power = latest_data["house_b"].get("current_power", 0)

        # Database logging
        try:
            save_live_reading(latest_data)
        except Exception as e:
            print(f"DB Save Error: {e}")

        # Analysis Engine: Anomaly (Sync with physical buzzer 3500W+)
        try:
            if current_power > 3500:
                if not latest_data["notifications_sent"]["anomaly_active"]:
                    add_notification(
                        "anomaly",
                        "ABNORMAL USAGE DETECTED",
                        f"Power surged to {current_power:.0f}W! Over 200% above baseline. Check for fridge failure or left-on AC.",
                        {"power": current_power}
                    )
                    latest_data["notifications_sent"]["anomaly_active"] = True
            else:
                # Reset when power drops back
                latest_data["notifications_sent"]["anomaly_active"] = False
        except Exception as e:
            print(f"Anomaly Engine Error: {e}")

        # Analysis Engine: Tier Jump (Dual-Stage Logic)
        try:
            if current_kwh >= 290 and not latest_data["notifications_sent"]["tier_290"]:
                add_notification(
                    "tier_warning",
                    "CRITICAL TARIFF ALERT",
                    f"Reached {current_kwh:.1f} kWh. ONLY {300-current_kwh:.1f} kWh LEFT before 53% surge! Action: Turn off non-essential items.",
                    {"kwh": current_kwh, "stage": 290}
                )
                latest_data["notifications_sent"]["tier_290"] = True
            elif current_kwh >= 280 and not latest_data["notifications_sent"]["tier_280"] and current_kwh < 290:
                add_notification(
                    "tier_warning",
                    "Tariff Limit Approaching",
                    f"Reached {current_kwh:.1f} kWh. You are {300-current_kwh:.1f} kWh away from next tier. Suggest: Reduce AC 2h/day.",
                    {"kwh": current_kwh, "stage": 280}
                )
                latest_data["notifications_sent"]["tier_280"] = True
            
            # Reset if month changes or kWh drops (for demo)
            if current_kwh < 270:
                latest_data["notifications_sent"]["tier_280"] = False
                latest_data["notifications_sent"]["tier_290"] = False

        except Exception as e:
            print(f"Tier Prediction Error: {e}")

        # Weather & Community Advice
        try:
            forecast = get_weather_forecast()
            solar_advice = get_solar_advice(forecast, solar_pct, latest_data["ldr_covered"])
            for advice in solar_advice:
                if advice["priority"] == "high":
                    add_notification(advice["type"], advice["title"], advice["message"], advice)
            
            # Community Virtual Scheduling
            community_advice = get_virtual_scheduling_advice(solar_pct, latest_data["house_c"].get("ev_charging", False))
            for advice in community_advice:
                add_notification(advice["type"], advice["title"], advice["message"], advice)
                
        except Exception as e:
            print(f"Advice Engine Error: {e}")

        return jsonify({"status": "ok", "received": True})

    except Exception as main_e:
        print(f"🔥 Critical API Error: {main_e}")
        return jsonify({"status": "error", "message": str(main_e)}), 500


# ── Realtime Dashboard API ──
@app.route('/api/realtime')
def get_realtime():
    current_kwh = latest_data["house_b"]["kwh"]
    current_power = latest_data["house_b"]["current_power"]
    solar_pct = latest_data["house_a"]["solar_percent"]
    
    try:
        bill_data = get_current_bill(current_kwh)
        cost = bill_data["estimated"]
        tier_info = bill_data["tier"]
        tier_pred = predict_tier_jump(current_kwh)
        anomaly = detect_anomaly(current_power)
        notifications = get_unread_notifications()
        standby = get_standby_power()
        leaderboard = get_community_leaderboard(current_kwh)
        community_stats = get_community_stats()
    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            traceback.print_exc(file=f)
            f.write(f"\nRealtime Data Build Error: {e}")
        print(f"Realtime Data Build Error: {e}")
        cost, tier_info, tier_pred, anomaly, notifications, standby, leaderboard, community_stats = 0, {}, {}, {"anomaly": False}, [], {}, [], {}
    
    return jsonify({
        "house_a": latest_data["house_a"],
        "house_b": {**latest_data["house_b"], "anomaly": anomaly.get("anomaly", False)},
        "house_c": latest_data["house_c"],
        "live_sensor": {**latest_data["live_sensor"], "real_power": current_power},
        "ldr_covered": latest_data["ldr_covered"],
        "last_update": latest_data["last_update"],
        
        "bill": {
            "estimated": cost,
            "kwh": round(current_kwh, 1),
            "tier": tier_info
        },
        "prediction": tier_pred,
        "anomaly": anomaly,
        "standby": standby,
        "community": {
            "leaderboard": leaderboard,
            "stats": community_stats,
            "solar_surplus": solar_pct if solar_pct > 60 else 0
        },
        "notifications": notifications,
        "unread_count": len(notifications),
    })

@app.route('/api/history')
def get_history():
    try:
        return jsonify(get_usage_trend())
    except:
        return jsonify({"hourly": [], "daily": []})

@app.route('/api/weather')
def get_weather():
    try:
        forecast = get_weather_forecast()
        warnings = get_weather_warnings()
        earthquakes = get_earthquakes()
        solar_pct = latest_data["house_a"]["solar_percent"]
        advice = get_solar_advice(forecast, solar_pct, latest_data["ldr_covered"])
        
        return jsonify({
            "forecast": forecast,
            "warnings": warnings,
            "earthquakes": earthquakes,
            "advice": advice,
            "current_solar_pct": solar_pct,
            "ldr_covered": latest_data["ldr_covered"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/notifications/read', methods=['POST'])
def mark_read():
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE notifications SET is_read = 1")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Update Error: {e}")
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    print("EcoLink 2.0 Server Starting...")
    print("   Dashboard: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
