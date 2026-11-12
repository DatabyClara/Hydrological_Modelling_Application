# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 12:58:25 2019

@author: esa
"""

# Import necessary libraries
import os
from datetime import datetime
import numpy as np
import pandas as pd
# Import the model
import NAM as Model
import NAM_setup as setup 

# Set directory where input data is and where scripts are
EXERCISE_dir = os.getcwd()
DATA_dir = os.path.join(EXERCISE_dir, 'Data')
OUTPUT_dir = os.path.join(EXERCISE_dir, 'Output')
start_time = datetime.now()

# Initialize the model by calling the constructor of the NAM class (in NAM.py)
MyNAM_model = Model.NAM(DATA_dir)

# Running simulation
MyNAM_model.run_simulation()

#writing results
MyNAM_model.write_outputs(OUTPUT_dir)

end_time = datetime.now()
print("Duration: {}".format(end_time-start_time))


# check outflow
# one year at the time
nsub = setup.nsub
Sim_all = pd.DataFrame(data = MyNAM_model.Qt, index = MyNAM_model.sim_time)
Sim_all.columns = ['SimFlow']
Obs_all = pd.DataFrame(data = MyNAM_model.flow, index = MyNAM_model.sim_time)
Obs_all.columns=['ObsFlow']
Start = '2005-01-01 00'
End = '2005-06-01 23'
Sim = Sim_all[Start:End]
Obs = Obs_all[Start:End]
ax = Sim.plot(y='SimFlow')
Obs.plot(ax=ax, y = 'ObsFlow', title = 'Observation vs. simulation for subcatchment %d' %(nsub))