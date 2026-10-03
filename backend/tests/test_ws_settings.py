from app.services.ws_settings import is_v2_agent, resolve_stream_settings

SYS = {"WORKSTATION_IDLE_TIMEOUT_S": 900, "WORKSTATION_IDLE_WARN_LEAD_S": 60,
       "WORKSTATION_IDLE_TIMEOUT_ENABLED": True, "WORKSTATION_SEAT_WIDTH": 2560,
       "WORKSTATION_SEAT_HEIGHT": 1440, "WORKSTATION_CURSOR_WORKAROUND": True}


def test_is_v2_agent():
    assert is_v2_agent("0.5.0") and is_v2_agent("0.6.2") and is_v2_agent("1.0.0")
    assert not is_v2_agent("0.4.11") and not is_v2_agent(None) and not is_v2_agent("junk")


def test_defaults_fill_and_overrides_win():
    eff = resolve_stream_settings({"framerate": 60, "idle_timeout_s": 300}, SYS, "0.5.0")
    assert eff["framerate"] == 60
    assert eff["idle_timeout_s"] == 300            # override wins
    assert eff["idle_warn_lead_s"] == 60           # default fills
    assert eff["seat_shell"] == "gnome"
    assert (eff["seat_width"], eff["seat_height"]) == (2560, 1440)
    assert eff["cursor_workaround"] is True


def test_old_h264_keys_alias_to_video_keys_for_v2():
    eff = resolve_stream_settings({"h264_crf": 22, "h264_streaming_mode": True,
                                   "h264_paintover_crf": 18}, SYS, "0.5.0")
    assert eff["video_crf"] == 22
    assert eff["video_streaming_mode"] is True
    assert eff["video_paintover_crf"] == 18


def test_new_video_key_beats_old_alias():
    eff = resolve_stream_settings({"h264_crf": 22, "video_crf": 30}, SYS, "0.5.0")
    assert eff["video_crf"] == 30


def test_v1_agent_gets_todays_shape_only():
    eff = resolve_stream_settings({"h264_crf": 22}, SYS, "0.4.11")
    assert eff["h264_crf"] == 22
    for k in ("seat_shell", "seat_width", "cursor_workaround", "video_crf"):
        assert k not in eff
    assert eff["idle_timeout_s"] == 900


def test_bad_seat_shell_falls_back_to_gnome():
    eff = resolve_stream_settings({"seat_shell": "kde"}, SYS, "0.5.0")
    assert eff["seat_shell"] == "gnome"
