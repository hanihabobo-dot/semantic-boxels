set -e
mkdir -p /root/task_shots/tampura_environments/class_uncertain /root/task_shots/tampura_environments/find_dice
[ -e /root/task_shots/env_configs ] || ln -s /root/tampura-work/tampura_environments/env_configs /root/task_shots/env_configs
[ -e /root/task_shots/tampura_environments/class_uncertain/problems ] || ln -s /root/tampura-work/tampura_environments/tampura_environments/class_uncertain/problems /root/task_shots/tampura_environments/class_uncertain/problems
[ -e /root/task_shots/tampura_environments/find_dice/problems ] || ln -s /root/tampura-work/tampura_environments/tampura_environments/find_dice/problems /root/task_shots/tampura_environments/find_dice/problems
ls -la /root/task_shots /root/task_shots/tampura_environments/*
ls /root/task_shots/tampura_environments/find_dice/problems
E=/root/tampura-work/tampura_environments/tampura_environments
grep -n "alpha\|rgba\|color" $E/puck_slide/env.py | head -30
echo ---
grep -n "def initialize\|random.choice\|listdir" $E/find_dice/env.py $E/class_uncertain/env.py | head
