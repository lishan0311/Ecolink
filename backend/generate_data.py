import sqlite3
import random
import math
from datetime import datetime, timedelta
 
DB_PATH = "ecolink.db"
 
def create_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS hourly_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            hour INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,  -- 0=Mon, 6=Sun
            power_w REAL NOT NULL,         -- 该小时平均功率(W)
            kwh REAL NOT NULL,             -- 该小时用电量(kWh)
            house_id TEXT DEFAULT 'B'      -- 主要追踪B户
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS monthly_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            month INTEGER,
            total_kwh REAL,
            total_cost REAL,
            last_updated TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS live_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            power_b REAL,     -- House B 功率
            power_a REAL,     -- House A 功率  
            power_c REAL,     -- House C 功率
            solar_pct REAL,   -- 太阳能/LDR百分比
            kwh_b REAL,       -- House B 本月累计kWh
            anomaly BOOLEAN DEFAULT 0
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,   -- tier_warning/anomaly/solar_surplus/weather
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT 0,
            data TEXT            -- JSON额外数据
        )
    """)
    
    conn.commit()
    conn.close()
    print("Tables created.")
 
def generate_hourly_pattern(hour, day_of_week, month_day):
    is_weekend = day_of_week >= 5  # 周六周日
    
    base_patterns = {
        0:  180,   # 凌晨12点 - 低谷（空调+冰箱待机）
        1:  160,
        2:  155,   # 凌晨2点 - 最低点
        3:  150,
        4:  165,
        5:  200,   # 凌晨5点 - 稍微增加（热水器定时）
        6:  480,   # 早上6点 - 起床高峰开始
        7:  780,   # 早上7点 - 洗澡、早餐高峰
        8:  650,   # 早上8点 - 出门后稍降
        9:  420,   # 上午9点 - 工作日家里人少
        10: 380,
        11: 420,
        12: 680,   # 中午12点 - 午饭高峰
        13: 580,
        14: 350,   # 下午2点 - 最热，空调高但活动少
        15: 340,
        16: 380,
        17: 620,   # 下午5点 - 回家高峰
        18: 850,   # 晚上6点 - 做饭高峰
        19: 920,   # 晚上7点 - 最高峰（做饭+电视+空调）
        20: 860,
        21: 780,
        22: 680,   # 晚上10点 - 准备睡觉
        23: 420,
    }
    
    base = base_patterns[hour]
    
    if is_weekend:
        if 9 <= hour <= 22:
            base *= 1.25
        if 7 <= hour <= 9:
            base *= 0.8  # 周末睡懒觉，早晨功率较低
    
    month_factor = 0.95 + (month_day / 30) * 0.1
    base *= month_factor
    
    noise = random.uniform(0.85, 1.15)
    power = base * noise
    
    # kWh = power(W) * 1小时 / 1000
    kwh = power / 1000.0
    
    return round(power, 1), round(kwh, 4)
 
def generate_30_days():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("DELETE FROM hourly_usage")
    
    today = datetime.now()
    total_kwh_month = 0.0
    records = []
    
    print("Generating 30 days of data...")
    
    for day_offset in range(30, 0, -1):
        date = today - timedelta(days=day_offset)
        day_of_week = date.weekday()
        month_day = date.day
        
        for hour in range(24):
            timestamp = date.replace(hour=hour, minute=0, second=0, microsecond=0)
            power, kwh = generate_hourly_pattern(hour, day_of_week, month_day)
            
            if day_offset == 22 and 2 <= hour <= 4:
                power = random.uniform(820, 900)  
                kwh = power / 1000.0
                print(f"  Anomaly injected: Day 8, {hour}:00, {power:.0f}W")
            
            if day_offset in [15, 8] and 12 <= hour <= 14:
                power *= 1.4  
                kwh = power / 1000.0
            
            records.append((
                timestamp.isoformat(),
                hour,
                day_of_week,
                power,
                kwh,
                'B'
            ))
            
            if date.month == today.month:
                total_kwh_month += kwh
    
    c.executemany(
        "INSERT INTO hourly_usage (timestamp, hour, day_of_week, power_w, kwh, house_id) VALUES (?,?,?,?,?,?)",
        records
    )
    
    c.execute("DELETE FROM monthly_summary")
    
    cost = calculate_tnb_cost(total_kwh_month)
    
    c.execute(
        "INSERT INTO monthly_summary (year, month, total_kwh, total_cost, last_updated) VALUES (?,?,?,?,?)",
        (today.year, today.month, round(total_kwh_month, 2), round(cost, 2), today.isoformat())
    )
    
    conn.commit()
    conn.close()
    
    print(f"Generated {len(records)} hourly records.")
    print(f"Current month total: {total_kwh_month:.1f} kWh = RM {cost:.2f}")
    print(f"Days remaining: ~{(30 - today.day)} days")
    
    return total_kwh_month
 
def calculate_tnb_cost(kwh):
    cost = 3.00  # Fixed charge
    
    if kwh <= 200:
        cost += kwh * 0.218
    elif kwh <= 300:
        cost += 200 * 0.218
        cost += (kwh - 200) * 0.334
    elif kwh <= 600:
        cost += 200 * 0.218
        cost += 100 * 0.334
        cost += (kwh - 300) * 0.516
    else:
        cost += 200 * 0.218
        cost += 100 * 0.334
        cost += 300 * 0.516
        cost += (kwh - 600) * 0.546
    
    return cost
 
def generate_sample_notifications():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM notifications")
    
    import json
    
    samples = [
        (
            (datetime.now() - timedelta(days=22)).isoformat(),
            "anomaly",
            "Abnormal usage detected",
            "Power at 2AM–5AM was 850W, 166% above normal. Check: AC timer, water heater, fridge.",
            1,
            json.dumps({"hour": 3, "power": 852, "baseline": 155})
        ),
        (
            (datetime.now() - timedelta(hours=4)).isoformat(),
            "tier_warning",
            "Tariff tier-jump warning",
            "You've used 287 kWh. Based on your usage trend, you will cross 300 kWh in 3 days. Rate will jump 53%.",
            0,
            json.dumps({"current_kwh": 287, "predicted_days": 3})
        ),
        (
            datetime.now().isoformat(),
            "solar",
            "Community solar surplus",
            "Neighbor's solar is producing excess now. Best time to run washing machine. Save RM 0.85.",
            0,
            json.dumps({"solar_pct": 72, "saving": 0.85})
        ),
    ]
    
    c.executemany(
        "INSERT INTO notifications (timestamp, type, title, message, is_read, data) VALUES (?,?,?,?,?,?)",
        samples
    )
    conn.commit()
    conn.close()
    print("Sample notifications created.")
 
if __name__ == "__main__":
    print("=== EcoLink Database Setup ===")
    create_tables()
    total = generate_30_days()
    generate_sample_notifications()
    print("\nDatabase ready! Run app.py next.")