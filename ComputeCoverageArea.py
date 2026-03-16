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


