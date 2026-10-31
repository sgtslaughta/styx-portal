import subprocess, sys, dbus, dbus.mainloop.glib
from gi.repository import GLib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus(); loop = GLib.MainLoop(); out = sys.argv[1]
sc = dbus.Interface(bus.get_object("org.gnome.Mutter.ScreenCast", "/org/gnome/Mutter/ScreenCast"), "org.gnome.Mutter.ScreenCast")
sp = sc.CreateSession({})
ses = dbus.Interface(bus.get_object("org.gnome.Mutter.ScreenCast", sp), "org.gnome.Mutter.ScreenCast.Session")
stp = ses.RecordMonitor("", {"cursor-mode": dbus.UInt32(0)})
st = bus.get_object("org.gnome.Mutter.ScreenCast", stp)
def added(node):
    r = subprocess.run(["gst-launch-1.0", "-q", "pipewiresrc", f"path={node}", "num-buffers=1", "!", "videoconvert", "!",
                        "videoscale", "!", "video/x-raw,width=640,height=360", "!", "jpegenc", "quality=80", "!", "filesink", f"location={out}"],
                       capture_output=True, text=True, timeout=10)
    print("gst rc", r.returncode, r.stderr[-200:]); ses.Stop(); loop.quit()
st.connect_to_signal("PipeWireStreamAdded", added, dbus_interface="org.gnome.Mutter.ScreenCast.Stream")
ses.Start(); GLib.timeout_add_seconds(15, loop.quit); loop.run()
