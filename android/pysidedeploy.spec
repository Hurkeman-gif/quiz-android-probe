[app]
title = 答题练习软件
project_dir = .
input_file = main.py
exec_directory = .
icon = assets/icon.png

[qt]
modules = Core,Gui,Widgets,Sql

[python]
android_packages = buildozer==1.5.0,cython==0.29.33

[android]
arch = aarch64

[buildozer]
mode = debug
