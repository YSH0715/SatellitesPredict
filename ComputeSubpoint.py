import skyfield.api
from datetime import datetime, timedelta

from skyfield.sgp4lib import EarthSatellite
from skyfield.timelib import utc


class ComputeSubpoint:
    def __init__(
            self,
            first_line: str,
            second_line: str,
            start_time: datetime,
            end_time: datetime,
            time_step: int
    ):
        self._first_line = first_line
        self._second_line = second_line
        self._start_time = start_time
        self._end_time = end_time
        self._time_step = timedelta(seconds=time_step)
        self._result_list = []

    def run(self):
        load = skyfield.api.Loader('~/.skyfield-data')
        ts = load.timescale()
        satellite = EarthSatellite(self._first_line, self._second_line, 'ISS', ts)

        current = self._start_time
        while current <= self._end_time:
            # 核心修改：使用 replace(tzinfo=utc) 明确告知这是 UTC 时间
            t = ts.from_datetime(current.replace(tzinfo=utc))

            geocentric = satellite.at(t)
            # 建议使用 wgs84.subpoint(geocentric) 这种更现代的写法
            subpoint = geocentric.subpoint()

            self._result_list.append({
                'time': current.strftime('%Y-%m-%d %H:%M:%S'),
                'longitude': subpoint.longitude.degrees,
                'latitude': subpoint.latitude.degrees,
                'altitude': subpoint.elevation.km
            })

            current += self._time_step

        return self._result_list


def test_compute_subpoint_logic():
    line1 = "1 25544U 98067A   23225.52406734  .00016149  00000-0  29033-3 0  9997"
    line2 = "2 25544  51.6416 261.3283 0004511 113.8824 331.0664 15.49817992411135"

    # 在创建 datetime 时显式指定 tzinfo
    start_dt = datetime(2023, 8, 13, 12, 0, 0, tzinfo=utc)
    end_dt = datetime(2023, 8, 13, 12, 0, 30, tzinfo=utc)
    step = 10  # 每 10 秒计算一次

    # 2. 实例化并运行
    print(f"开始测试卫星坐标计算...")
    computer = ComputeSubpoint(line1, line2, start_dt, end_dt, step)
    results = computer.run()

    # 3. 验证结果
    # 检查点 1: 结果数量是否正确 (0s, 10s, 20s, 30s 应该有 4 个点)
    expected_count = 4
    assert len(results) == expected_count, f"预期点数 {expected_count}, 实际得到 {len(results)}"

    # 检查点 2: 验证经纬度范围
    for i, point in enumerate(results):
        lon = point['longitude']
        lat = point['latitude']
        alt = point['altitude']

        # 经度 [-180, 180], 纬度 [-90, 90]
        assert -180 <= lon <= 180, f"第 {i} 个点的经度 {lon} 超出范围"
        assert -90 <= lat <= 90, f"第 {i} 个点的纬度 {lat} 超出范围"

        # 检查点 3: 验证高度是否符合低轨卫星特征 (通常在 400km 左右)
        assert 300 <= alt <= 500, f"第 {i} 个点的高度 {alt}km 不符合 ISS 常规轨道"

        print(f"点 {i} 校验通过: Time={point['time']}, Lon={lon:.2f}, Lat={lat:.2f}, Alt={alt:.2f}km")

    print("--- 所有测试项已通过！ ---")


if __name__ == "__main__":
    test_compute_subpoint_logic()