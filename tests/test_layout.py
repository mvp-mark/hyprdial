from omarchy_settings.layout import Rect, logical_size, normalize, overlaps, settle, snap, touches

A = Rect("DP-1", 0, 0, 2560, 1440)
B = Rect("HDMI-A-2", 2560, 0, 1920, 1080)


def test_logical_size_applies_scale_and_rotation():
    assert logical_size("2560x1440@164.83", 1.25, 0, (0, 0)) == (2048, 1152)
    assert logical_size("1920x1080@60", 1, 1, (0, 0)) == (1080, 1920)
    assert logical_size("preferred", 2, 0, (3840, 2160)) == (1920, 1080)


def test_touches_needs_shared_edge_segment():
    assert touches(A, B)
    assert not touches(A, B.moved(2560, 1440))  # só o canto
    assert not touches(A, B.moved(2600, 0))  # vão entre eles


def test_overlaps():
    assert overlaps(A, B.moved(2000, 0))
    assert not overlaps(A, B)


def test_snap_pulls_to_nearby_edges():
    assert snap(B.moved(-1910, 20), [A], 30) == B.moved(-1920, 0)
    assert snap(B.moved(-1500, 200), [A], 30) == B.moved(-1500, 200)


def test_settle_pushes_out_of_overlap():
    assert settle(B.moved(2000, 100), [A]) == B.moved(2560, 100)


def test_settle_reattaches_a_detached_monitor():
    s = settle(B.moved(4000, 3000), [A])
    assert touches(s, A) and not overlaps(s, A)


def test_settle_above():
    assert settle(B.moved(300, -1000), [A]) == B.moved(300, -1080)


def test_settle_without_others_keeps_position():
    assert settle(B.moved(5, 5), []) == B.moved(5, 5)


def test_normalize_moves_origin_to_zero():
    assert [(r.x, r.y) for r in normalize([A, B.moved(-1920, 200)])] == [(1920, 0), (0, 200)]
