import sqlite3
import requests
import re
from datetime import datetime

# 配置：Celestrak 提供的 TLE 数据接口（最近30天发射的卫星）
# 也可以换成：https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle"


def init_db():
    """初始化数据库表结构"""
    conn = sqlite3.connect('satellite_system.db')
    cursor = conn.cursor()

    # 卫星信息表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS satellites (
            sat_id INTEGER PRIMARY KEY,
            sat_name TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # TLE 数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tle_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sat_id INTEGER,
            tle_line1 TEXT NOT NULL,
            tle_line2 TEXT NOT NULL,
            fetch_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sat_id) REFERENCES satellites (sat_id)
        )
    ''')
    conn.commit()
    return conn


def fetch_and_save_tle():
    conn = init_db()
    cursor = conn.cursor()

    print(f"正在从 {CELESTRAK_URL} 获取数据...")

    try:
        response = requests.get(CELESTRAK_URL, timeout=20)
        response.raise_for_status()
        lines = response.text.strip().split('\n')

        # TLE 数据通常是 3 行一组：0 卫星名，1 第一行，2 第二行
        count = 0
        for i in range(0, len(lines), 3):
            if i + 2 >= len(lines):
                break

            name = lines[i].strip()
            line1 = lines[i + 1].strip()
            line2 = lines[i + 2].strip()

            # 从 TLE 第二行解析 NORAD ID (第 3-7 位)
            sat_id = int(line2[2:7])

            # 1. 更新或插入卫星基本信息
            cursor.execute('''
                INSERT OR REPLACE INTO satellites (sat_id, sat_name, updated_at)
                VALUES (?, ?, ?)
            ''', (sat_id, name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

            # 2. 插入新的 TLE 记录
            cursor.execute('''
                INSERT INTO tle_data (sat_id, tle_line1, tle_line2, fetch_time)
                VALUES (?, ?, ?, ?)
            ''', (sat_id, line1, line2, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

            count += 1

        conn.commit()
        print(f"成功更新 {count} 颗卫星的 TLE 数据！")

    except Exception as e:
        print(f"获取失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fetch_and_save_tle()