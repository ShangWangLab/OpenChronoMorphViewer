#!/bin/bash

sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get install python3.11
wget https://bootstrap.pypa.io/get-pip.py
sudo python3.11 get-pip.py
python3.11 -m pip install --force-reinstall numpy psutil pynrrd pyqt5 scipy vtk tifffile