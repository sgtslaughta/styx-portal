#!/bin/sh
# Started by labwc as its session command once the Wayland compositor (and its
# Xwayland server) are up. labwc exports DISPLAY for us, pointing at the Xwayland
# the XFCE X11 apps use.
#
# xfce4-session skips launching a window manager when it sees a Wayland session
# (XDG_SESSION_TYPE=wayland), assuming the compositor manages windows. But the
# XFCE apps run as X11/Xwayland clients that need an ICCCM/EWMH window manager —
# without one there is no cursor, no window placement, no move/resize, no frames.
# So we start xfwm4 on the Xwayland display ourselves, then the XFCE session.
xfwm4 &

exec xfce4-session
