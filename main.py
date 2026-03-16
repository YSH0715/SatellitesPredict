import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import pandas as pd
from fastapi.responses import StreamingResponse
import io

from ComputeSubpoint import ComputeSubpoint
from ComputeTransitSinglePoint import ComputeTransitSinglePoint
from ComputeCoverageArea import ComputeCoverageArea

app = FastAPI(title="基于SGP4的卫星轨迹预测分析系统 API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],             # 允许所有源（开发环境建议用 *，生产环境建议指定具体域名）
    allow_credentials=True,
    allow_methods=["*"],             # 允许所有 HTTP 方法 (GET, POST, 等)
    allow_headers=["*"],             # 允许所有请求头
)

# --- 数据库与数据获取工具 ---

def get_tle_from_db(sat_id: int):
    """从数据库读取指定卫星最新的TLE"""
    conn = sqlite3.connect('satellite_system.db')
    cursor = conn.cursor()
    query = '''
        SELECT t.tle_line1, t.tle_line2 
        FROM tle_data t
        WHERE t.sat_id = ?
        ORDER BY t.fetch_time DESC
        LIMIT 1
    '''
    cursor.execute(query, (sat_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def update_tle_task():
    """后台任务：从 Celestrak 获取数据并更新数据库"""
    url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        lines = response.text.strip().split('\n')

        conn = sqlite3.connect('satellite_system.db')
        cursor = conn.cursor()

        for i in range(0, len(lines), 3):
            if i + 2 >= len(lines): break
            name = lines[i].strip()
            l1, l2 = lines[i + 1].strip(), lines[i + 2].strip()
            sat_id = int(l2[2:7])  # 解析 NORAD ID

            # 更新卫星主表与数据表
            cursor.execute("INSERT OR REPLACE INTO satellites (sat_id, sat_name, updated_at) VALUES (?, ?, ?)",
                           (sat_id, name, datetime.now()))
            cursor.execute("INSERT INTO tle_data (sat_id, tle_line1, tle_line2, fetch_time) VALUES (?, ?, ?, ?)",
                           (sat_id, l1, l2, datetime.now()))

        conn.commit()
        conn.close()
        print(f"[{datetime.now()}] TLE 自动更新成功")
    except Exception as e:
        print(f"更新失败: {e}")


# --- API 路由设计 ---

@app.post("/api/data/update")
async def trigger_update(background_tasks: BackgroundTasks):
    """
    手动触发 TLE 数据更新。
    使用后台任务避免请求阻塞。
    """
    background_tasks.add_task(update_tle_task)
    return {"message": "TLE update task has been started in the background."}


@app.get("/api/satellite/trajectory/{sat_id}")
async def get_trajectory(sat_id: int, minutes: int = 90, step: int = 60):
    """获取未来轨迹点序列"""
    tle = get_tle_from_db(sat_id)
    if not tle:
        raise HTTPException(status_code=404, detail="Satellite TLE not found")

    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=minutes)

    # 实例化你编写的 ComputeSubpoint 类
    computer = ComputeSubpoint(tle[0], tle[1], start, end, step)
    return computer.run()


@app.get("/api/satellite/coverage/{sat_id}")
async def get_coverage(sat_id: int):
    """获取当前时刻的覆盖范围（多边形点集）"""
    tle = get_tle_from_db(sat_id)
    if not tle:
        raise HTTPException(status_code=404, detail="Satellite data not found")

    now = datetime.now(timezone.utc)
    # ComputeCoverageArea 内部会调用 ComputeSubpoint
    computer = ComputeCoverageArea(tle[0], tle[1], now, now + timedelta(seconds=1), 1)
    results = computer.run()
    return results[0] if results else {}


@app.get("/api/satellite/transit")
async def get_transit(sat_id: int, lon: float, lat: float, alt: float = 0):
    """
    预测未来24小时内的过境信息
    """
    # 1. 从数据库获取该卫星的 TLE
    tle = get_tle_from_db(sat_id)
    if not tle:
        raise HTTPException(status_code=404, detail="Satellite data not found")

    # 2. 设置时间范围：从现在开始，往后推 24 小时
    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=24)

    try:
        # 这里传入前端传来的站点经纬度 (lon, lat)
        computer = ComputeTransitSinglePoint(tle[0], tle[1], lon, lat, alt, start, end)

        # 执行计算：内部会计算仰角、方位角等，并筛选出仰角 > 5度的时段
        results = computer.run()

        # 返回给前端 JSON 列表 (包含 start_time, max_pitch_angle, target_timeliness 等)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/satellites/list")
async def get_satellites_list():
    """获取数据库中所有卫星，供前端下拉框展示"""
    conn = sqlite3.connect('satellite_system.db')
    cursor = conn.cursor()
    # 前端显示“卫星名 [#编号]”
    cursor.execute("SELECT sat_id, sat_name FROM satellites ORDER BY sat_name ASC")
    results = [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    conn.close()
    return results


@app.get("/api/satellite/batch_coverage")
async def get_batch_coverage(sat_ids: str):
    """
    批量获取卫星覆盖范围
    :param sat_ids: 逗号分隔的卫星ID，例如 "25544,43013"
    """
    id_list = [int(sid) for sid in sat_ids.split(",") if sid.strip()]
    results = []

    now = datetime.now(timezone.utc)

    for sat_id in id_list:
        tle = get_tle_from_db(sat_id)
        if not tle:
            continue

        # 计算覆盖范围
        computer = ComputeCoverageArea(tle[0], tle[1], now, now + timedelta(seconds=1), 1)
        data = computer.run()
        if data:
            res = data[0]
            res['sat_id'] = sat_id
            # 加上卫星名称方便前端识别
            conn = sqlite3.connect('satellite_system.db')
            cursor = conn.cursor()
            cursor.execute("SELECT sat_name FROM satellites WHERE sat_id=?", (sat_id,))
            name_row = cursor.fetchone()
            res['sat_name'] = name_row[0] if name_row else f"SAT {sat_id}"
            conn.close()
            results.append(res)

    return results


@app.get("/api/satellite/batch_trajectory")
async def get_batch_trajectory(sat_ids: str, minutes: int = 90, step: int = 60):
    """
    批量获取多颗卫星的轨迹数据
    :param sat_ids: 逗号分隔的ID，如 "25544,43013"
    """
    id_list = [int(sid) for sid in sat_ids.split(",") if sid.strip()]
    results = {}

    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=minutes)

    for sat_id in id_list:
        tle = get_tle_from_db(sat_id)
        if tle:
            computer = ComputeSubpoint(tle[0], tle[1], start, end, step)
            results[sat_id] = computer.run()

    return results


@app.get("/api/satellite/export_report/{sat_id}")
async def export_report(sat_id: int):
    """
    生成卫星未来12小时的运行数据分析报表（Excel）
    """
    tle = get_tle_from_db(sat_id)
    if not tle:
        raise HTTPException(status_code=404, detail="Satellite not found")

    # 1. 获取卫星名称
    conn = sqlite3.connect('satellite_system.db')
    cursor = conn.cursor()
    cursor.execute("SELECT sat_name FROM satellites WHERE sat_id=?", (sat_id,))
    name_row = cursor.fetchone()
    sat_name = name_row[0] if name_row else str(sat_id)
    conn.close()

    # 2. 计算未来12小时的数据，每10分钟采样一次
    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=12)
    # 使用 ComputeSubpoint 计算轨迹
    computer_traj = ComputeSubpoint(tle[0], tle[1], start, end, 600)
    traj_data = computer_traj.run()

    # 3. 整理数据为表格格式
    report_list = []
    for p in traj_data:
        # 针对每个点计算覆盖面积
        t_point = datetime.fromisoformat(p['time'].replace('Z', '+00:00'))
        computer_cov = ComputeCoverageArea(tle[0], tle[1], t_point, t_point + timedelta(seconds=1), 1)
        cov_res = computer_cov.run()[0]

        report_list.append({
            "时间(UTC)": p['time'],
            "经度(deg)": round(p['longitude'], 4),
            "纬度(deg)": round(p['latitude'], 4),
            "高度(km)": round(p['altitude'], 2),
            "覆盖半径(deg)": round(cov_res['cover_radius_deg'], 2),
            "覆盖面积(sqkm)": round(cov_res['cover_area_sqkm'], 2)
        })

    # 4. 使用 Pandas 转换为 Excel 字节流
    df = pd.DataFrame(report_list)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Satellite Report')
    output.seek(0)

    # 5. 返回文件下载响应
    filename = f"Report_{sat_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import uvicorn

    # 运行服务器
    uvicorn.run(app, host="0.0.0.0", port=8000)