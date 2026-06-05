import sqlite3
import json
import os
from datetime import datetime, timedelta
 
DB_PATH = os.path.join(os.path.dirname(__file__), 'ecolink.db')
 
def get_current_month_kwh():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0).isoformat()
    
    result = c.execute(
        "SELECT SUM(kwh) FROM hourly_usage WHERE timestamp >= ? AND house_id = 'B'",
        (month_start,)
    ).fetchone()
    
    conn.close()
    return result[0] or 0.0
 
def get_current_bill(kwh):
    """Real-time bill calculation based on TNB tariff"""
    bill = 0
    tier_info = {}
    
    # Tier 1: 0 - 200 kWh (RM 0.218)
    if kwh > 0:
        t1_kwh = min(kwh, 200)
        bill += t1_kwh * 0.218
        tier_info = {"current_rate": 0.218, "next_threshold": 200 if kwh < 200 else 300}
    
    # Tier 2: 201 - 300 kWh (RM 0.334)
    if kwh > 200:
        t2_kwh = min(kwh - 200, 100)
        bill += t2_kwh * 0.334
        tier_info = {"current_rate": 0.334, "next_threshold": 300}
    
    # Tier 3: 301 - 600 kWh (RM 0.516)
    if kwh > 300:
        t3_kwh = min(kwh - 300, 300)
        bill += t3_kwh * 0.516
        tier_info = {"current_rate": 0.516, "next_threshold": 600}
        
    # Tier 4: 601 - 900 kWh (RM 0.546)
    if kwh > 600:
        t4_kwh = min(kwh - 600, 300)
        bill += t4_kwh * 0.546
        tier_info = {"current_rate": 0.546, "next_threshold": 900}
        
    # Tier 5: > 900 kWh (RM 0.571)
    if kwh > 900:
        t5_kwh = kwh - 900
        bill += t5_kwh * 0.571
        tier_info = {"current_rate": 0.571, "next_threshold": 9999}
        
    # Minimum monthly charge
    bill = max(bill, 3.00)
    
    return {
        "estimated": round(bill, 2),
        "tier": tier_info
    }
 
def predict_tier_jump(current_kwh):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    today = datetime.now()
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    
    rows = c.execute(
        """SELECT DATE(timestamp) as day, SUM(kwh) as daily_kwh
        FROM hourly_usage
        WHERE timestamp >= ? AND house_id = 'B'
        GROUP BY day
        ORDER BY day DESC
        LIMIT 7
        """,
        (seven_days_ago,)
    ).fetchall()
    
    conn.close()
    
    if not rows:
        return None
    
    avg_daily_kwh = sum(r[1] for r in rows) / len(rows)
    
    days_in_month = 30  
    days_elapsed = today.day
    days_remaining = max(1, days_in_month - days_elapsed)
    
    predicted_total = current_kwh + (avg_daily_kwh * days_remaining)
    
    tier_threshold = 300 if current_kwh < 300 else 600
    
    if predicted_total > tier_threshold and current_kwh < tier_threshold:
        kwh_to_jump = tier_threshold - current_kwh
        days_to_jump = kwh_to_jump / avg_daily_kwh if avg_daily_kwh > 0 else 99
        
        if days_to_jump <= 5:
            return {
                "warning": True,
                "days_to_jump": round(days_to_jump, 1),
                "current_kwh": round(current_kwh, 1),
                "threshold": tier_threshold,
                "remaining_kwh": round(kwh_to_jump, 1),
                "avg_daily": round(avg_daily_kwh, 2),
                "predicted_total": round(predicted_total, 1),
                "suggestion": f"Reduce daily usage by {round(avg_daily_kwh - kwh_to_jump/days_remaining, 1)} kWh to avoid jumping."
            }
    
    return {"warning": False, "days_to_jump": round((tier_threshold - current_kwh) / avg_daily_kwh, 1) if avg_daily_kwh > 0 else 99}
 
def detect_anomaly(current_power, current_hour=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if current_hour is None:
        current_hour = datetime.now().hour
    
    baseline_rows = c.execute(
        "SELECT AVG(power_w), COUNT(*) "
        "FROM hourly_usage "
        "WHERE hour = ? AND house_id = 'B'",
        (current_hour,)
    ).fetchone()
    
    conn.close()
    
    baseline_avg = baseline_rows[0] or 300
    sample_count = baseline_rows[1] or 0
    
    if sample_count < 7:
        return {"anomaly": False, "baseline": None}
    
    deviation_pct = ((current_power - baseline_avg) / baseline_avg * 100) if baseline_avg > 0 else 0
    is_anomaly = current_power > baseline_avg * 2.0  
    
    result = {
        "anomaly": is_anomaly,
        "current_power": round(current_power, 1),
        "baseline_avg": round(baseline_avg, 1),
        "deviation_pct": round(deviation_pct, 1),
        "hour": current_hour
    }
    
    if is_anomaly:
        result["message"] = f"Power is {round(deviation_pct)}% above normal for this hour. Check appliances."
    
    return result
 
def get_usage_trend():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    today = datetime.now()
    
    today_str = today.strftime('%Y-%m-%d')
    hourly = c.execute(
        """
        SELECT hour, AVG(power_w)
        FROM hourly_usage
        WHERE DATE(timestamp) = ? AND house_id = 'B'
        GROUP BY hour
        ORDER BY hour
        """,
        (today_str,)
    ).fetchall()
    
    daily = c.execute(
        """
        SELECT DATE(timestamp) as day, SUM(kwh) as total
        FROM hourly_usage
        WHERE house_id = 'B'
        GROUP BY day
        ORDER BY day DESC
        LIMIT 7
        """
    ).fetchall()
    
    conn.close()
    
    hourly_data = [0] * 24
    for row in hourly:
        hourly_data[row[0]] = round(row[1], 0)
    
    if not hourly:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        hist = c.execute(
                """
                SELECT hour, AVG(power_w)
                FROM hourly_usage
                WHERE house_id = 'B'
                GROUP BY hour
                ORDER BY hour
                """
        ).fetchall()
        conn.close()
        for row in hist:
            hourly_data[row[0]] = round(row[1], 0)
    return {
        "hourly": hourly_data,
        "daily": [{"date": r[0], "kwh": round(r[1], 2)} for r in daily]
    }
 
def save_live_reading(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute(
        "INSERT INTO live_readings \
        (timestamp, power_b, power_a, power_c, solar_pct, kwh_b, anomaly)\
        VALUES (?,?,?,?,?,?,?)",
        (
            datetime.now().isoformat(),
            data.get("house_b", {}).get("power", 0),
            data.get("house_a", {}).get("power", 0),
            data.get("house_c", {}).get("power", 0),
            data.get("house_a", {}).get("solar_percent", 0),
            data.get("house_b", {}).get("kwh", 0),
            data.get("house_b", {}).get("anomaly", False)
        )
    )
    
    conn.commit()
    conn.close()
 
def add_notification(ntype, title, message, extra_data=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    existing = c.execute(
        "SELECT id FROM notifications WHERE type=? AND timestamp>? AND is_read=0",
        (ntype, one_hour_ago)
    ).fetchone()
    
    if not existing:
        c.execute(
            "INSERT INTO notifications (timestamp, type, title, message, is_read, data)\n"
            "VALUES (?,?,?,?,0,?)",
            (
                datetime.now().isoformat(),
                ntype, title, message,
                json.dumps(extra_data) if extra_data else None
            )
        )
        conn.commit()
    
    conn.close()
 
def get_unread_notifications():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    rows = c.execute(
        "SELECT id, timestamp, type, title, message, data\n"
        "FROM notifications\n"
        "WHERE is_read = 0\n"
        "ORDER BY timestamp DESC\n"
        "LIMIT 10"
    ).fetchall()
    
    conn.close()
    
    return [{
        "id": r[0], "timestamp": r[1], "type": r[2],
        "title": r[3], "message": r[4],
        "data": json.loads(r[5]) if r[5] else None
    } for r in rows]

def get_standby_power():
    """Estimate standby waste based on midnight usage (2AM-4AM)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get average power between 2AM and 4AM in the last 7 days
    row = c.execute(
        "SELECT AVG(power_w) FROM hourly_usage "
        "WHERE hour IN (2, 3) AND house_id = 'B'"
    ).fetchone()
    
    conn.close()
    
    standby_w = row[0] or 145.9 # Mock baseline if no data
    monthly_kwh = (standby_w * 24 * 30) / 1000
    monthly_cost = monthly_kwh * 0.218
    
    return {
        "standby_w": round(standby_w, 1),
        "monthly_kwh": round(monthly_kwh, 1),
        "monthly_cost_rm": round(monthly_cost, 2)
    }

def get_community_leaderboard(current_kwh_b=250.5):
    """Dynamic leaderboard data with avatars and savings."""
    last_month_kwh = 310.0
    this_month_kwh = round(current_kwh_b, 1)
    savings_pct = round(((last_month_kwh - this_month_kwh) / last_month_kwh) * 100, 1)

    # Simulation: 15 houses
    houses = [
        {"id": "Neighbor #08", "savings_pct": 18.2, "rank": 1, "avatar": "/static/images/profile_1.png", "badges": ["7-Day Streak", "Tier Master"]},
        {"id": "Neighbor #15", "savings_pct": 15.5, "rank": 2, "avatar": "/static/images/profile_2.png", "badges": ["7-Day Streak"]},
        {"id": "Neighbor #03", "savings_pct": 14.1, "rank": 3, "avatar": "/static/images/profile_3.png", "badges": ["Tier Master"]},
        {"id": "Neighbor #12", "savings_pct": 12.8, "rank": 4, "avatar": "/static/images/profile_4.png", "badges": ["Rising Star"]},
        {"id": "Neighbor #09", "savings_pct": 11.2, "rank": 5, "avatar": "/static/images/profile_5.png", "badges": []},
        {"id": "Neighbor #04", "savings_pct": 9.8, "rank": 6, "avatar": "/static/images/profile_6.png", "badges": []},
        {"id": "Neighbor #23 (You)", "savings_pct": savings_pct, "rank": 7, "avatar": "/static/images/profile_1.png", "badges": ["Rising Star"], "kwh_now": this_month_kwh, "kwh_last": last_month_kwh},
        {"id": "Neighbor #01", "savings_pct": 7.5, "rank": 8, "avatar": "/static/images/profile_2.png", "badges": []},
        {"id": "Neighbor #14", "savings_pct": 6.8, "rank": 9, "avatar": "/static/images/profile_3.png", "badges": []},
        {"id": "Neighbor #07", "savings_pct": 5.2, "rank": 10, "avatar": "/static/images/profile_4.png", "badges": []},
        {"id": "Neighbor #10", "savings_pct": 4.1, "rank": 11, "avatar": "/static/images/profile_5.png", "badges": []},
        {"id": "Neighbor #02", "savings_pct": 3.5, "rank": 12, "avatar": "/static/images/profile_6.png", "badges": []},
        {"id": "Neighbor #11", "savings_pct": 2.1, "rank": 13, "avatar": "/static/images/profile_1.png", "badges": []},
        {"id": "Neighbor #06", "savings_pct": 1.2, "rank": 14, "avatar": "/static/images/profile_2.png", "badges": []},
        {"id": "Neighbor #13", "savings_pct": -0.5, "rank": 15, "avatar": "/static/images/profile_3.png", "badges": []},
    ]
    
    # Re-sort based on real-time savings_pct
    houses.sort(key=lambda x: x["savings_pct"], reverse=True)
    for i, h in enumerate(houses):
        h["rank"] = i + 1
        
    return houses

def get_community_stats():
    """Aggregate stats for the hero section."""
    num_households = 15
    
    # Hardcoded Demo Data
    total_kwh_saved = 3562.8
    total_rm_saved = 1247.0
    total_co2_avoided = 423.0
    
    return {
        "kwh": total_kwh_saved,
        "rm": total_rm_saved,
        "co2": total_co2_avoided,
        "households": num_households
    }

def get_virtual_scheduling_advice(solar_pct, is_ev_charging):
    """Generate community-level scheduling advice."""
    advice = []
    
    if solar_pct > 80 and not is_ev_charging:
        advice.append({
            "type": "community_solar",
            "title": "Community Solar Surplus",
            "message": "Neighbor #12 has 2.4kW surplus! Ideal time for your laundry or EV top-up.",
            "priority": "medium"
        })
    
    return advice