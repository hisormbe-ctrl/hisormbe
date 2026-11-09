#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.9.25
#

import sys,re
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication,    
)

import window as win
import camera as cam
import style
from dataIO import CommLog, TempLog, LogManager
from gauge_reader import find_camera_id

def main():

    app = QApplication(sys.argv)
    camera_id = find_camera_id()

    window = win.MainWindow(camera_id=camera_id)
   
    window.show()

    sys.exit(app.exec())


if __name__=='__main__':

    main()
    