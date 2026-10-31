# Window that repaints a counter every 250 ms so selkies always has frames.
import tkinter as tk, itertools
r = tk.Tk(); r.geometry("400x400+50+50")
l = tk.Label(r, font=("Sans", 80)); l.pack(expand=True, fill="both")
c = itertools.count()
def tick():
    n = next(c); l.config(text=str(n), bg=["#c33", "#3c3", "#33c"][n % 3]); r.after(33, tick)
tick(); r.mainloop()
