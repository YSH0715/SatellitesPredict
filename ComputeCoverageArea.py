import math

import numpy as np
from datetime import datetime

from skyfield.timelib import utc

from ComputeSubpoint import ComputeSubpoint


class ComputeCoverageArea:
    def __init__(
            self,
            first_line: str,
            second_line: str,
            start_time: datetime,
            end_time: datetime,
            time_step: int,
            earth_radius: float=6371.0,
            min_elevation: int=5
    ):
        """
        :param first_line: tle第一行
        :param second_line: tle第二行
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param time_step: 时间步长(秒)
        :param earth_radius: 地球半径(km)
        :param min_elevation: 最小仰角(度)
        """
        self._first_line = first_line
        self._second_line = second_line
        self._start_time = start_time
        self._end_time = end_time
        self._time_step = time_step
        self._earth_radius = earth_radius
        self._min_elevation = min_elevation
        self._position_list = []
        self._radius_deg = 0.0
        self._result_list = []

    # 计算覆盖半径（使用几何推导：地心角 theta）
    def _calculate_coverage_radius(self, position_dict):
        """
        计算卫星在给定最小仰角下的地心角半径 (theta)
        """
        epsilon = np.radians(self._min_elevation)  # 最小仰角
        h = position_dict['altitude']  # 卫星高度
        Re = self._earth_radius  # 地球半径

        # 1. 计算 nadir angle (eta): 卫星视角下的半角
        # 根据正弦定理: Re / sin(eta) = (Re + h) / sin(90 + epsilon)
        # sin(eta) = (Re * cos(epsilon)) / (Re + h)
        sin_eta = (Re * np.cos(epsilon)) / (Re + h)

        # 数值安全检查
        sin_eta = max(-1.0, min(1.0, sin_eta))
        eta = np.arcsin(sin_eta)

        # 2. 计算地心角 (theta): 从地心看卫星与覆盖边缘的夹角
        # theta = 90° - epsilon - eta
        theta_rad = np.pi / 2 - epsilon - eta

        self._radius_deg = np.degrees(theta_rad)

    # 生成覆盖区域多边形
    def _generate_footprint(self, position_dict):
        """
        生成覆盖区域的经纬度坐标序列
        """
        angles = np.linspace(0, 2 * np.pi, 72)
        range_list = []

        center_lat = position_dict['latitude']
        center_lon = position_dict['longitude']

        # 将地心角转换为弧度
        r_rad = np.radians(self._radius_deg)
        lat_rad = np.radians(center_lat)

        for angle in angles:
            # 使用球面几何近似计算（在小范围/低纬度非常准确）
            # 若需极高精度或处理极点，应使用大圆航线公式
            d_lat = self._radius_deg * np.sin(angle)

            # 极点保护：防止 cos(lat) 为 0 导致除以零错误
            cos_lat = np.cos(lat_rad)
            if abs(cos_lat) < 1e-6:
                cos_lat = 1e-6

            d_lon = (self._radius_deg * np.cos(angle)) / cos_lat

            target_lat = center_lat + d_lat
            target_lon = center_lon + d_lon

            # 纬度钳制 [-90, 90]
            target_lat = max(-90.0, min(90.0, target_lat))

            # 经度标准化 [-180, 180]
            while target_lon > 180: target_lon -= 360
            while target_lon < -180: target_lon += 360

            range_list.append({
                'longitude': round(target_lon, 6),
                'latitude': round(target_lat, 6)
            })

        return range_list

    def run(self):
        self._position_list = ComputeSubpoint(
            first_line=self._first_line,
            second_line=self._second_line,
            start_time=self._start_time,
            end_time=self._end_time,
            time_step=self._time_step
        ).run()

        self._result_list = []
        for position_dict in self._position_list:
            # 1. 计算当前高度下的覆盖半径
            self._calculate_coverage_radius(position_dict)

            # 2. 生成多边形点集
            range_list = self._generate_footprint(position_dict)

            # 3. 计算球面覆盖面积 (公式: 2 * pi * R^2 * (1 - cos(theta)))
            theta_rad = np.radians(self._radius_deg)
            spherical_area = 2 * np.pi * (self._earth_radius ** 2) * (1 - np.cos(theta_rad))

            self._result_list.append({
                'time': position_dict['time'],
                'subpoint': {
                    'longitude': position_dict['longitude'],
                    'latitude': position_dict['latitude']
                },
                'cover_radius_deg': round(self._radius_deg, 4),
                'cover_area_sqkm': round(spherical_area, 2),
                'cover_range': range_list
            })

        return self._result_list


def test_compute_coverage_area():
    """
    针对 ComputeCoverageArea 类的完整测试用例
    验证物理计算、数据结构和多边形生成
    """
    print("=" * 50)
    print("开始测试：卫星覆盖区域计算 (ComputeCoverageArea)")
    print("=" * 50)

    # 1. 准备测试数据 (ISS 国际空间站某时刻真实 TLE)
    line1 = "1 25544U 98067A   23225.52406734  .00016149  00000-0  29033-3 0  9997"
    line2 = "2 25544  51.6416 261.3283 0004511 113.8824 331.0664 15.49817992411135"

    # 2. 设定时间范围（显式指定 UTC 时区）
    # 计算 2023年8月13日 12:00:00 开始的 3 分钟数据
    start_dt = datetime(2023, 8, 13, 12, 0, 0, tzinfo=utc)
    end_dt = datetime(2023, 8, 13, 12, 3, 0, tzinfo=utc)
    step = 60  # 每 60 秒生成一个点

    # 3. 初始化计算类
    # 设定最小仰角为 5 度，地球半径为 6371 km
    coverage_calculator = ComputeCoverageArea(
        first_line=line1,
        second_line=line2,
        start_time=start_dt,
        end_time=end_dt,
        time_step=step,
        earth_radius=6371.0,
        min_elevation=5
    )

    try:
        # 执行计算
        results = coverage_calculator.run()

        # 4. 验证结果
        # 校验点 1: 结果数量 (0, 1, 2, 3 分钟，共 4 个结果)
        assert len(results) == 4, f"预期 4 个点，实际得到 {len(results)} 个"

        for i, res in enumerate(results):
            # 获取数据（使用更新后的键名）
            time_str = res['time']
            radius_deg = res['cover_radius_deg']
            area_sqkm = res['cover_area_sqkm']
            footprint = res['cover_range']
            subpoint = res['subpoint']

            # 校验点 2: 物理数值合理性
            # 对于高度约 400km 的 ISS，5度仰角下的地心角半径应在 15°-17° 左右
            assert 10 < radius_deg < 25, f"第 {i} 点半径 {radius_deg:.2f}° 物理数值异常"

            # 校验点 3: 覆盖面积合理性
            # 15.8度半径对应的面积大约在 1000万 到 1500万 平方公里之间
            assert 5_000_000 < area_sqkm < 20_000_000, f"第 {i} 点面积 {area_sqkm:,.2f} km² 异常"

            # 校验点 4: 多边形点数
            assert len(footprint) == 72, f"第 {i} 点覆盖范围点数应为 72，实际为 {len(footprint)}"

            # 打印关键信息
            print(f"[样本 {i}] 时间: {time_str}")
            print(f"    - 星下点: Lon {subpoint['longitude']:.2f}, Lat {subpoint['latitude']:.2f}")
            print(f"    - 覆盖半径: {radius_deg:.4f} 度")
            print(f"    - 覆盖面积: {area_sqkm:,.2f} 平方公里")
            print(f"    - 边界点示例: {footprint[0]}")

        print("\n" + "=" * 50)
        print("单元测试成功：所有物理校验和数据结构校验均已通过！")
        print("=" * 50)

    except Exception as e:
        print(f"\n测试失败！捕捉到异常: {type(e).__name__}")
        print(f"错误详细信息: {e}")
        raise e


if __name__ == "__main__":
    test_compute_coverage_area()