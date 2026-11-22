import sys
print("python:", sys.version)
try:
    import pygame
    print("pygame ok", pygame.__version__)
except Exception as e:
    print("pygame fail:", e)
try:
    import OpenGL
    print("OpenGL ok")
except Exception as e:
    print("OpenGL fail:", e)
