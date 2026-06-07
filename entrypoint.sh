#!/bin/bash
tmux new-session -d -s garmin 'export TERM=xterm-256color && python main.py; exec bash -i'

ttyd -p 9000 -W -t fontSize=16 tmux attach -t garmin