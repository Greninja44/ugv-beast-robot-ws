"""Simple hardware controls that don't need the teleop safety machinery (lease,
watchdog, clamps) — just an authenticated fire-and-forget command. LED today;
this is also where future Robot Controls page actions (start/stop SLAM, save
map, etc.) belong.

The vendor stack publishes no LED feedback topic, so `on` here is "last state
this dashboard commanded", not a hardware-confirmed readback.
"""
from __future__ import annotations

from ..ros.bridge import RosBridge

LED_ON_PWM = 255.0
LED_OFF_PWM = 0.0


class ControlsService:
    def __init__(self, bridge: RosBridge):
        self.bridge = bridge
        self.led_on = False

    def set_led(self, on: bool) -> bool:
        pwm = LED_ON_PWM if on else LED_OFF_PWM
        self.bridge.publish_led(pwm, pwm)  # both base + head light together
        self.led_on = on
        return self.led_on
