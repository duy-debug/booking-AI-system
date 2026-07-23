from datetime import time


# Chuyển thời gian trong ngày thành tổng số phút để tính khoảng nghỉ.
def time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


# Chuyển tổng số phút đã giới hạn trong ngày về kiểu time dùng cho truy vấn.
def minutes_to_time(value: int, *, end_boundary: bool = False) -> time:
    if value <= 0:
        return time.min
    if value >= 24 * 60:
        return time.max if end_boundary else time(23, 59)
    return time(value // 60, value % 60)


# Mở rộng khung booking về hai phía để yêu cầu khoảng cách nghỉ tối thiểu.
def expand_time_window(
    start_time: time,
    end_time: time,
    break_minutes: int,
) -> tuple[time, time]:
    if break_minutes <= 0:
        return start_time, end_time
    start_minutes = max(0, time_to_minutes(start_time) - break_minutes)
    end_minutes = min(24 * 60, time_to_minutes(end_time) + break_minutes)
    return (
        minutes_to_time(start_minutes),
        minutes_to_time(end_minutes, end_boundary=True),
    )


# Kiểm tra overlap trong context đã nạp sẵn và tính thêm thời gian nghỉ của shop.
def intervals_overlap_with_break(
    existing_start: time,
    existing_end: time,
    candidate_start: time,
    candidate_end: time,
    break_minutes: int,
) -> bool:
    expanded_start, expanded_end = expand_time_window(
        candidate_start,
        candidate_end,
        break_minutes,
    )
    return existing_start < expanded_end and existing_end > expanded_start
