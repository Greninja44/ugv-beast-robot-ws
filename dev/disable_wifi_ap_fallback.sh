#!/usr/bin/env bash
# Disable the Pi's WiFi-loss-to-hotspot fallback (RaspberryConnect's "AccessPopup").
# Run this FROM WSL (it SSHes into the Pi). Safe & reversible.
#
# WHAT THIS FIXES: the stock Waveshare image ships AccessPopup, a systemd timer
# that checks every 2 minutes whether the Pi can see its configured WiFi SSID —
# and if not, switches wlan0 into its OWN access point ("AccessPopup" /
# 1234567890, static IP 192.168.50.5) instead of continuing to retry the real
# network. From the outside this looks exactly like the Pi "lost WiFi entirely"
# (it vanishes from the LAN at its normal IP) even though it's actually fine and
# just sitting in hotspot mode waiting for someone to join it and reconfigure —
# this caused at least two full OS reflashes in this project that likely weren't
# needed at all. Disabling it leaves NetworkManager's own autoconnect/retry
# behavior in charge, which just keeps trying the real SSID instead of bailing
# into a hotspot.
#
# Revert: ssh ugv "sudo systemctl enable --now AccessPopup.timer"
set -euo pipefail

PI=ugv  # ssh alias

echo ">> disabling AccessPopup (WiFi-loss hotspot fallback) on $PI"
ssh "$PI" "sudo systemctl disable --now AccessPopup.timer AccessPopup.service"

echo ">> current state:"
ssh "$PI" "systemctl is-enabled AccessPopup.timer; systemctl is-active AccessPopup.timer"
echo ">> done. The Pi will now just keep retrying its configured WiFi (NetworkManager"
echo "   autoconnect) instead of falling back to its own hotspot."
