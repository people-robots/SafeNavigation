import pygame       as PG

import configparser as cp
import numpy        as np

from  Playground  import Playground_Object
from  Robot       import Robot_Object, RobotStats
from  Target      import Target_Object
from  Monitoring  import Monitors
import time

class Game_Object(object):
    def __init__(self, cmdargs):
        PG.init()
        self.StaticObstacles = []

        self.cmdargs       = cmdargs
        self.WhiteColor    = (255, 255, 255)
        self.BlackColor    = (0, 0, 0)
        self.Display_Width = 1200
        self.Display_Height= 600
        self.gameDisplay   = PG.display.set_mode((self.Display_Width, self.Display_Height))
        self.Playground    = Playground_Object(800, self.Display_Height, cmdargs.map_name, cmdargs=cmdargs)
        self.TargetPoint   = Target_Object((740,50))

        self.Normal_Robot  = Robot_Object (self.gameDisplay, self.TargetPoint,(50,550), speed=cmdargs.robot_speed, cmdargs=cmdargs, name="NormalRobot")
        self.Safe_Robot    = Robot_Object (self.gameDisplay, self.TargetPoint,(50,550), speed=cmdargs.robot_speed, cmdargs=cmdargs, issafe = True, name="SafeRobot")
        self.robot_list    = []
        self.robot_list.append(self.Normal_Robot)
        self.robot_list.append(self.Safe_Robot)

        PG.display.set_caption('Robot Simulator')

    def standard_game_loop(self):
        clock = PG.time.Clock()
        step_num = 0
        while True:
            # Handle events
            for event in PG.event.get():
                if event.type == PG.QUIT:
                    return
            # Step the environment
            self.Playground.Nextstep(self.gameDisplay)
        
            allBotsAtTarget = True

            # Process robot actions
            for robot in self.robot_list:
                if not (robot.distanceToTarget() < 20):
                    allBotsAtTarget = False
                    robot.NextStep(self.Playground.GridData)

            if (self.cmdargs.batch_mode) and (allBotsAtTarget):
                return
            if not allBotsAtTarget:
                step_num += 1
            if self.cmdargs.max_steps <= step_num:
                return

            # Draw everything
            for robot in self.robot_list:
                robot.draw(self.gameDisplay)
            self.TargetPoint.draw(self.gameDisplay)
            PG.display.update()

            # Tick the clocks
            clock.tick(1000)
        
    def fast_computing_game_loop(self):
        safe_robot_at_target = False
        normal_robot_at_target = False 
        allRobotsAtTarget = False
        self.Playground.Nextstep(self.gameDisplay)
        step_num = 0
        while (not allRobotsAtTarget):
            allBotsAtTarget = True

            # Process robot actions
            for robot in self.robot_list:
                if not (robot.distanceToTarget() < 20):
                    allBotsAtTarget = False
                    robot.NextStep(self.Playground.GridData)
            step_num += 1
            if self.cmdargs.max_steps <= step_num:
                return


    def make_csv_line(self):
        output_csv = str(self.cmdargs.speedmode) + ','
        output_csv += str(self.cmdargs.radar_resolution) +','
        output_csv += str(self.cmdargs.radar_noise_level) +','
        output_csv += str(self.cmdargs.map_name) +','
        output_csv += str(self.cmdargs.map_modifier_num) +','
        output_csv += str(self.cmdargs.target_distribution_type) +','
        output_csv += str(self.cmdargs.use_integer_robot_location) +','

        normal_robot_stats = self.Normal_Robot.get_stats()
        safe_robot_stats = self.Safe_Robot.get_stats()

        output_csv += str(normal_robot_stats.num_glitches) + ","
        output_csv += str(safe_robot_stats.num_glitches) + ","

        output_csv += str(self.Normal_Robot.stepNum if self.check_robot_at_target(self.Normal_Robot) else "") + ","
        output_csv += str(self.Safe_Robot.stepNum if self.check_robot_at_target(self.Safe_Robot) else "") + ","

        output_csv += str(0 if self.check_robot_at_target(self.Normal_Robot) else 1) + ","
        output_csv += str(0 if self.check_robot_at_target(self.Safe_Robot) else 1) 


        return output_csv


    def check_robot_at_target(self, robot):
        return robot.distanceToTarget() < 20


    def GameLoop(self):
        if self.cmdargs.fast_computing:
            self.fast_computing_game_loop()
        else:
            self.standard_game_loop()

        print(self.make_csv_line());

        PG.quit()
        return 0
