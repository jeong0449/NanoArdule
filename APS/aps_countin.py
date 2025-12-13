# aps_countin.py — built-in Count-In patterns for APS
#
# APS 전체 규칙:
#   - 1 pattern = 2 bars
#   - 일반 패턴은 length = 32 step (16 step x 2 bars) 기준
#
# 카운트인은 내부적으로 2 bar 길이 패턴으로 두되,
# 실제 재생 시에는 앞 1 bar(절반)만 잘라 씁니다.

from aps_core import Pattern

def get_countin_presets():
    """
    단일 카운트-인 패턴 리스트를 반환한다.

    - 전체 길이: 32 step (2 bars)
    - 실제 재생: APS 쪽에서 앞 16 step (1 bar)만 사용
    - 내용: 1 bar 기준 4분음표 위치(0, 4, 8, 12)에만 HH 타격
    """
    length = 32       # 2 bars 전체 길이
    slots = 1         # HH만 사용

    # grid[step][slot] = accent_level
    grid = [[0] for _ in range(length)]

    # 1 bar(16 step 기준)의 4분음표 위치: 0, 4, 8, 12
    # 2 bar 전체 중에서 우리는 1 bar만 쓸 것이므로,
    # 0,4,8,12 에만 히트를 넣어 두면 된다.
    for step in (0, 4, 8, 12):
        grid[step][0] = 2   # acc2 = medium accent

    p = Pattern(
        name="CountIn_HH",
        path="(internal)",
        length=length,
        slots=slots,
        grid=grid,
        time_sig="4/4",
        grid_type="16",          # 기존 패턴들과 동일한 16th grid
        triplet=False,
        slot_abbr=["HH"],
        slot_name=["Closed Hi-Hat"],
        slot_note=[42],          # GM Closed Hi-Hat
    )

    return [p]
