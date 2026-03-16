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


