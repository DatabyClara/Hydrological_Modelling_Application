# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 13:18:31 2019

@author: esa
"""

# Set up file for NAM simulation
# Adapt this script to your files

sub_area = 'SubCatchmArea.csv'

time_step = 'H' # D: daily, H: hourly

# input data
flow = 'Flow.xlsx'
pet = 'PET.xlsx'
precip = 'Precip.xlsx'
#Temp = 'Temp.xlsx'

# model components
snow = 'No' # will you use the snow module? (you need temperature data!)

# Select a catchment (1-10)
nsub = 2

# Model parameters
# parnumber:     0      1      2      3      4      5     6     7     8     9    10     11
parname=['Umax', 'Lmax', 'CQOF', 'CKIF', 'CK1', 'CK2', 'TOF', 'TIF', 'TG', 'CKBF', 'Csnow', 'T0']

# Minimum parameter values
paramMin = [5, 50, 0.0, 150, 3, 3, 0, 0, 0, 500, 2, -3]

# Maximum parameter values
paramMax = [35, 1000, 1.0, 1500, 48, 48, 0.9, 0.9, 0.99, 7500, 5, 3]

# Set parameter values
Fpar = [8, 50, 0.5, 500, 5, 10, 0., 0., 0., 1000, 2, 0]

# Initial values for states
relU = 0.3
relL = 0.5
OF = 0
OFp = 0.0
IF = 0
IFp = 0.0
BF = 0.1
OFmin = 0.40
Beta = 0.3631
# extra states
Ss = 0
Sw = 0


########################################################################################
# Define simulation warm-up period
########################################################################################

# Defining starting date of the simulation
StartDate = '2002-01-01 00' #YYYY-MM-DD HH

# Defining ending date of the simulation
EndDate = '2014-12-31 23' #YYYY-MM-DD HH

# Defining ending date of warming-up period
EndWuDate = '2004-12-31 23' #YYYY-MM-DD HH