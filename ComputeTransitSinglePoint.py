import skyfield.api
from datetime import datetime, timedelta, timezone


class ComputeTransitSinglePoint:
    def __init__(
            self,
            first_line: str,
            second_line: str,
            site_longitude: float,
            site_latitude: float,
            site_altitude: float,
            start_time: datetime,
            end_time: datetime
    ):
        """
        :param first_line: tle第一行
        :param second_line: tle第二行
        :param site_longitude: 站点经度
        :param site_latitude: 站点纬度
        :param site_altitude: 站点海拔(米)
        :param start_time: 开始时间
        :param end_time: 结束时间
        """
        self._first_line = first_line
        self._second_line = second_line
        self._site_longitude = site_longitude
        self._site_latitude = site_latitude
        self._site_altitude = site_altitude
        self._start_time = start_time.replace(tzinfo=skyfield.api.utc)
        self._end_time = end_time.replace(tzinfo=skyfield.api.utc)
        self._elevation_threshold = 5.0
        self._ts = None
        self._satellite = None
        self._observer = None
        self._events = []
        self._result_list = []

    def _obj_init(self):

        # 初始化时间和卫星对象
        self._ts = skyfield.api.load.timescale()

        # 创建卫星对象
        self._satellite = skyfield.api.EarthSatellite(self._first_line, self._second_line, 'ISS', self._ts)

        # 创建观测站点的Topos对象
        self._observer = skyfield.api.Topos(
            latitude_degrees=self._site_latitude,
            longitude_degrees=self._site_longitude,
            elevation_m=self._site_altitude
        )

    # 生成时间序列（间隔1分钟）
    def _generate_time_sequence(self):

        current = self._start_time

        while current <= self._end_time:

            t = self._ts.from_datetime(current)

            topocentric = (self._satellite - self._observer).at(t)

            alt, az, distance = topocentric.altaz()

            if alt.degrees >= self._elevation_threshold:

                self._events.append((current, alt.degrees, distance.km))

            current += timedelta(minutes=1)

    # 计算卫星过境时间段数据
    def _compute_transits(self):
        current_transit = None
        for time, angle, distance in self._events:
            if not current_transit:
                current_transit = {
                    'start_time': time,
                    'end_time': time,
                    'target_timeliness': 0.0,          # 同一时刻，持续 0 秒
                    'max_pitch_angle': angle,
                    'indication_accuracy': distance
                }
            else:
                if (time - current_transit['end_time']).total_seconds() <= 60:
                    current_transit['end_time'] = time
                    current_transit['target_timeliness'] = (
                        current_transit['end_time'] -
                        current_transit['start_time']).total_seconds()
                    current_transit['max_pitch_angle'] = max(
                        current_transit['max_pitch_angle'], angle)
                    current_transit['indication_accuracy'] = min(
                        current_transit['indication_accuracy'], distance)
                else:
                    self._result_list.append(current_transit)
                    current_transit = {
                        'start_time': time,
                        'end_time': time,
                        'target_timeliness': 0.0,
                        'max_pitch_angle': angle,
                        'indication_accuracy': distance
                    }
        if current_transit:
            self._result_list.append(current_transit)

    def run(self):

        self._obj_init()

        self._generate_time_sequence()

        self._compute_transits()

        for i in range(len(self._result_list)):

            self._result_list[i]['start_time'] = self._result_list[i]['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            self._result_list[i]['end_time'] = self._result_list[i]['end_time'].strftime('%Y-%m-%d %H:%M:%S')

        return self._result_list


