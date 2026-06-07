#!/bin/bash

tmux new-session -d -s garmin 'python main.py'

ttyd -p 9000 tmux attach -t garmin