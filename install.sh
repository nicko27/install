rm -rvf logs/* 
rm -rvf plugins/*/__pycache__
rm -rvf ui/__pycache__
git add -v . 
git commit -m "$(date '+%Y-%m-%d %H:%M:%S')" 
git push origin master 
source .venv/bin/activate 
/media/nico/Drive/install/.venv/bin/textual run main.py --dev
deactivate
sudo chmod 777 -R logs/*
