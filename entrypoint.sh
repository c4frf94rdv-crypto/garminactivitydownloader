#!/bin/bash

tmux new-session -d -s garmin 'python main.py'

ttyd -p 9000 -W -t fontSize=16 tmux attach -t garmin