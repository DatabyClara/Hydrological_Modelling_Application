# -*- coding: utf-8 -*-
"""
Run the NAM model with the settings in NAM_setup.py.

Original version: esa, 2019. Modernised 2026.
"""
import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

import NAM as Model
import NAM_setup as setup

# Folders: data and output are located next to this script
EXERCISE_dir = os.path.dirname(os.path.abspath(__file__))
DATA_dir = os.path.join(EXERCISE_dir, 'Data')
OUTPUT_dir = os.path.join(EXERCISE_dir, 'Output')
start_time = datetime.now()

# Initialise the model (constructor of the NAM class in NAM.py)
MyNAM_model = Model.NAM(DATA_dir)

# Run the simulation
MyNAM_model.run_simulation()
if MyNAM_model.invalid:
    raise SystemExit('Fix the parameter values in NAM_setup.py and run again.')

# Write results
MyNAM_model.write_outputs(OUTPUT_dir)

end_time = datetime.now()
print("Duration: {}".format(end_time - start_time))


# Check outflow (plot one period at a time)
nsub = setup.nsub
Sim_all = pd.DataFrame({'SimFlow': MyNAM_model.Qt}, index=MyNAM_model.sim_time)
Obs_all = pd.DataFrame({'ObsFlow': MyNAM_model.flow}, index=MyNAM_model.sim_time)
Start = '2005-01-01 00'
End = '2005-06-01 23'
Sim = Sim_all.loc[Start:End]
Obs = Obs_all.loc[Start:End]
ax = Sim.plot(y='SimFlow')
Obs.plot(ax=ax, y='ObsFlow', title='Observation vs. simulation for subcatchment %d' % nsub)
ax.set_ylabel('Flow [m$^3$/s]')
plt.show()
