"""Tests for WeatherAnimation and WeatherIconAnimation."""

import numpy as np

from flipdisc.animations.weather import WeatherAnimation
from flipdisc.animations.weather_icon import _CONDITIONS, WeatherIconAnimation

ALL_CONDITIONS = list(_CONDITIONS)


class TestWeatherIconAnimation:
    def test_all_conditions_render(self):
        for cond in ALL_CONDITIONS:
            icon = WeatherIconAnimation(28, 28)
            icon.configure(condition=cond)
            frame = icon.render_gray()
            assert frame.shape == (28, 28)
            assert frame.dtype == np.float32

    def test_unknown_condition_falls_back(self):
        icon = WeatherIconAnimation(28, 28)
        icon.configure(condition="hail")
        frame = icon.render_gray()
        assert frame.shape == (28, 28)
        # Should not raise and should have some lit pixels (cloudy fallback)
        assert frame.max() > 0.0

    def test_icon_is_top_right_aligned(self):
        """Icon should be placed top-right, so bottom-left should be mostly dark."""
        icon = WeatherIconAnimation(28, 28)
        icon.configure(condition="sunny")
        frame = icon.render_gray()
        # Bottom-left 20x8 region should be dark (few or no lit pixels)
        bottom_left = frame[20:28, 0:8]
        assert bottom_left.sum() < 5, "Bottom-left region has too many lit pixels"


class TestWeatherAnimation:
    def test_all_conditions_render_without_exception(self):
        for cond in ALL_CONDITIONS:
            anim = WeatherAnimation(28, 28)
            anim.configure(temp=72, condition=cond, unit="F")
            frame = anim.render_gray()
            assert frame.shape == (28, 28)
            assert frame.max() >= 0.0

    def test_default_renders(self):
        anim = WeatherAnimation(28, 28)
        frame = anim.render_gray()
        assert frame.shape == (28, 28)

    def test_temp_text_updates(self):
        anim = WeatherAnimation(28, 28)
        anim.configure(temp=72, condition="sunny", unit="F")
        frame1 = anim.render_gray()
        anim.configure(temp=55)
        frame2 = anim.render_gray()
        # Frames should differ because temperature changed
        assert not np.array_equal(frame1, frame2)

    def test_unit_change_rerenders(self):
        anim = WeatherAnimation(28, 28)
        anim.configure(temp=22, condition="cloudy", unit="C")
        frame_c = anim.render_gray()
        anim.configure(unit="F")
        frame_f = anim.render_gray()
        # Unit is not displayed (only number + degree symbol) — frames are identical
        assert np.array_equal(frame_c, frame_f)

    def test_condition_update_does_not_raise(self):
        anim = WeatherAnimation(28, 28)
        anim.configure(temp=68, condition="sunny")
        anim.configure(condition="rain")  # should not raise
        frame = anim.render_gray()
        assert frame.shape == (28, 28)

    def test_step_does_not_raise(self):
        anim = WeatherAnimation(28, 28)
        anim.configure(temp=72, condition="sunny")
        for _ in range(10):
            anim.step(1 / 60)
        anim.render_gray()

    def test_params_stored(self):
        anim = WeatherAnimation(28, 28)
        anim.configure(temp=72, condition="sunny", unit="F")
        assert anim.params.get("temp") == 72
        assert anim.params.get("condition") == "sunny"
        assert anim.params.get("unit") == "F"
