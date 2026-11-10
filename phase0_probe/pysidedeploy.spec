[app]
title = Phase0Probe
project_dir = .
input_file = main.py
exec_directory = .

[qt]
modules = Core,Gui,Widgets

[python]
android_packages = buildozer==1.5.0,cython==0.29.33

[android]
arch = aarch64

[buildozer]
mode = debug
