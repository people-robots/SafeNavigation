import pygame       as PG

import configparser as cp
import numpy        as np

from  Playground  import Playground_Object
from  Robot       import Robot_Object
from  Target      import Target_Object
from  Monitoring  import Monitors

class Game_Object(object):
    def __init__(self):
        PG.init()
        self.StaticObstacles = []

        self.WhiteColor         = (255, 255, 255)
        self.BlackColor         = (0, 0, 0)
        self.Display_Width      = 1200
        self.Display_Height     = 600
        self.MainWindow_Title   = 'Robot Simulator'
        PG.display.set_caption (self.MainWindow_Title)
        self.gameDisplay        = PG.display.set_mode((self.Display_Width, self.Display_Height))
        self.Playground         = Playground_Object(800, self.Display_Height,"Maps/Maps_c.png")
        self.TargetPoint        = Target_Object((740,50))
        self.Robot              = Robot_Object (self.gameDisplay, self.TargetPoint,(50,550),speed=10)
        self.Monitor            = Monitors(self.Robot,PG.display,self.Playground.Playground)

    def GameLoop(self):

        clock = PG.time.Clock()
        shouldClose = False
        while not shouldClose:

            for event in PG.event.get():
                if event.type == PG.QUIT:
                    shouldClose = True
                if event.type == PG.MOUSEBUTTONUP:
                    pos = PG.mouse.get_pos()
                    self.Robot.Coordinate = pos
                    self.Robot.PathList.append(pos                    )
                    # if event.type == PG.KEYDOWN:
            result = False
            self.Robot.Coordinate = (50,550)
            self.Playground.Nextstep(self.gameDisplay)
            clockrobot = 0
            while (result == False):

                result = self.Robot.NextStep(self.Playground.GridData)
                clockrobot = clockrobot + 1
            self.TargetPoint.draw(self.gameDisplay)
            self.Robot.draw(self.gameDisplay)
            self.Monitor.draw()
            PG.display.update()
            print (clockrobot * 5)
            print ("Distance : ")
            print (len(self.Robot.PathList))
            self.Robot.PathList.clear()
            clock.tick(1000)
        PG.quit()
        return 0