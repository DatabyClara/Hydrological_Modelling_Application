# -*- coding: utf-8 -*-
"""
Created on Mon Nov 18 12:41:14 2019

@author: esa
"""
import numpy as np
import pandas as pd
import math
import os
import NAM_setup as setup

###################################################################################
#         NAM model
###################################################################################

#### Inputs ######
# P: daily rainfall [mm/d] or [mm/hr]
# Ep: daily potential evapotranspiration [mm/d] or [mm/hr]

##### if snow is modelled
# T: mean daily temperature [°C]


class NAM():
    def __init__(self, DATA_dir):
        """ This is a Python version of the NAM model created for the Surface Hydrology course
        of the IUPWARE program, year 2019-2020
        
        Global model parameters for calibration:
            1) Surface root zone paramenters
                Umax: Max water content in the surface storage (mm)
                Lmax: Max water content in the rootzone storage (mm)
            2) Runoff parameters
                CQOF: overland runoff coefficient
                CKIF: Time constant for routing interflow (hours)
                CK1: Time constant for routing overland flow (hours)
                CK2: Time constant for routing overland flow (different recession constant for the two reservoirs)
                TOF: Rootzone threshold value
                TIF: Rootzone threshold value for interflow
            3) Groundwater parameters
                TG: Rootzone threshold value for groundwater recharge
                CKBF: Time constant for routing baseflow (hours)
            4) Snow processes parameters
                Csnow
                T0
        """
        # model initialization
        print('')
        print('Loading setup instructions...')
        print('')
        self.time_step = setup.time_step
        fh_sub_area = os.path.join(DATA_dir,setup.sub_area)
        fh_flow = os.path.join(DATA_dir,setup.flow)
        fh_pet = os.path.join(DATA_dir,setup.pet)
        fh_precip = os.path.join(DATA_dir,setup.precip)
        try:
            fh_Temp = setup.Temp
        except:
            fh_Temp = None
            
        self.snow = setup.snow
        # consistency check
        options = ['Yes', 'yes', 'Y', 'y', 'YES']
        if self.snow in options:
            self.snow = True
            if fh_Temp == None:
                print("Temperature file not provided. Snow melt cannot be simulated.")
                print('')
                self.snow = 'No'
            else:
                fh_temp = os.path.join(DATA_dir, setup.Temp)
        else:
            self.snow = False
                
        self.nsub = setup.nsub
        
        # calibration parameters
        parname=setup.parname
        paramMin = setup.paramMin
        paramMax = setup.paramMax
        Fpar = setup.Fpar
        # check if parameters are within range
        if self.snow:
            for elem in list(zip(paramMin,Fpar,paramMax,parname)):
                if elem[0]<=elem[1]<=elem[2]:
                    self.invalid=False
                else:
                    print('The parameter %s is out of range' %(elem[3]))
                    print('')
                    self.invalid=True
        else:
            for elem in list(zip(paramMin[:-2],Fpar[:-2],paramMax[:-2],parname[:-2])):
                if elem[0]<=elem[1]<=elem[2]:
                    self.invalid=False
                else:
                    print('The parameter %s is out of range' %(elem[3]))
                    print('')
                    self.invalid=True
                    
        self.parameters = {}
        for i in range(len(parname)):
            self.parameters[parname[i]]=Fpar[i]
        if self.snow:
            self.parameters['CsnowM']=self.parameters['Csnow']/20
            self.parameters['Cswr'] = 0.00001
           
        
        # factor to convert mm/hr to m3/s
        self.fA = 3.6 # mm/h --> m³/s  (0.001*1000000/3600)^-1
        
        self.Start=pd.Timestamp(setup.StartDate)
        self.End=pd.Timestamp(setup.EndDate)
        self.EndWu=pd.Timestamp(setup.EndWuDate)
        
        print('Loading input data...')
        print('')
         
        flow_df = pd.read_excel(fh_flow, sheet_name = 'Flow', usecols = [0,1,2,3,3+self.nsub])
        start_flow = pd.Timestamp(flow_df['Year'][0],flow_df['Month'][0],flow_df['Day'][0], flow_df['Hour'][0])
        end_flow = pd.Timestamp(flow_df['Year'].iloc[-1],flow_df['Month'].iloc[-1],flow_df['Day'].iloc[-1], flow_df['Hour'].iloc[-1])
        print('Flow time series: completed!')
        pet_df = pd.read_excel(fh_pet, sheet_name = 'PET', usecols = [0,1,2,3,4])
        start_pet = pd.Timestamp(pet_df['Year'][0],pet_df['Month'][0],pet_df['Day'][0], pet_df['Hour'][0])
        end_pet = pd.Timestamp(pet_df['Year'].iloc[-1],pet_df['Month'].iloc[-1],pet_df['Day'].iloc[-1], pet_df['Hour'].iloc[-1])
        print('PET series: completed!')
        precip_df = pd.read_excel(fh_precip, sheet_name='Precip', usecols = [0,1,2,3,3+self.nsub])
        start_precip = pd.Timestamp(precip_df['Year'][0],precip_df['Month'][0],precip_df['Day'][0], precip_df['Hour'][0])
        end_precip = pd.Timestamp(precip_df['Year'].iloc[-1],precip_df['Month'].iloc[-1],precip_df['Day'].iloc[-1], precip_df['Hour'].iloc[-1])
        print('Precipitation time series: completed!')
        print('')
        if self.snow:
            temp_df = pd.read_excel(fh_temp, sheet_name='Temp', usecols = [0,1,2,3,3+self.nsub])
            start_temp = pd.Timestamp(temp_df['Year'][0],temp_df['Month'][0],temp_df['Day'][0], temp_df['Hour'][0])
            end_temp = pd.Timestamp(temp_df['Year'].iloc[-1],temp_df['Month'].iloc[-1],temp_df['Day'].iloc[-1], temp_df['Hour'].iloc[-1])
            
        self.sub_area = np.loadtxt(fh_sub_area, delimiter=',')[self.nsub-1]
               
        # check if start and end dates in the setup file are consistent with the input excel files (not checking for temperature)
        if self.Start>= max(start_flow, start_pet, start_precip):
            self.Start = self.Start
        else:
            print('WARNING: the selected start date is before the first input record')
            self.Start = max(start_flow, start_pet, start_precip)
            print('Setting the start date to the firt date where all data is available:', self.Start)
            print('')
            
        if self.End<=min(end_flow, end_pet, end_precip):
            self.End = self.End
        else:
            print('WARNING: the selected end date is after the last input record')
            print(self.End)
            self.End = min(end_flow, end_pet, end_precip)
            print('Setting the end date to the last date where all data is available:', self.End)
            print('')
        
        self.sim_time = pd.date_range(self.Start, self.End, freq=self.time_step)
        
        time_flow = pd.date_range(start_flow,end_flow, freq = self.time_step)
        flow = pd.DataFrame(data=flow_df.iloc[:,4:].values, index=time_flow)
        time_pet = pd.date_range(start_pet,end_pet, freq = self.time_step)
        # only one station for all basins
        pet = pd.DataFrame(data=pet_df.iloc[:,4:].values, index=time_pet)
        time_precip = pd.date_range(start_precip,end_precip, freq = self.time_step)
        precip = pd.DataFrame(data=precip_df.iloc[:,4:].values, index=time_precip)
        
        # select period where all data is available
        self.flow_df = flow.loc[self.sim_time]
        self.flow_df = self.flow_df.where(self.flow_df>=0)
        self.flow_df.columns = ['ObsFlow']
        self.flow = self.flow_df.values
        self.pet_df = pet.loc[self.sim_time]
        self.pet_df = self.pet_df.where(self.pet_df>=0)
        self.pet_df.columns = ['PotET']
        self.pet = self.pet_df.values
        self.precip_df = precip.loc[self.sim_time]
        self.precip_df = self.precip_df.where(self.precip_df>=0)
        self.precip_df.columns=['P']
        self.precip = self.precip_df.values
        if self.snow:
            time_temp = pd.date_range(start_temp,end_temp, freq = self.time_step)
            temp_df = pd.DataFrame(data=temp_df.iloc[:,4:].values, index=time_temp)
            self.temp_df = temp_df.loc[self.sim_time]
            self.temp_df.columns=['T']
            self.temp = self.temp_df.values

        relU = setup.relU
        relL = setup.relL
        self.OFmin = setup.OFmin
        self.Beta = setup.Beta
        self.IF = setup.IF
        self.IFp = setup.IFp
        self.BF = setup.BF
        self.Ss = setup.Ss
        self.Sw = setup.Sw
        self.OFp = setup.OFp
        self.OF = setup.OF
        
        self.QOF = np.zeros((len(self.sim_time)))
        self.OF_r = np.zeros((len(self.sim_time)))
        self.IF_r = np.zeros((len(self.sim_time)))
        self.G1 = np.zeros((len(self.sim_time)))
        self.BF_r = np.zeros((len(self.sim_time)))
        self.QIF = np.zeros((len(self.sim_time)))
        self.Qt = np.zeros((len(self.sim_time)))
        self.TSK1 = np.zeros((len(self.sim_time)))
        self.TSK2 = np.zeros((len(self.sim_time)))
        self.S = np.zeros((len(self.sim_time)))
        self.ET = np.zeros((len(self.sim_time)))
            
        # setting initial values
        self.TSK1[0]=self.parameters['CK1']
        self.TSK2[0]=self.parameters['CK2']
        
        self.U = relU*self.parameters['Umax']
        self.L = relL*self.parameters['Lmax']
    
    def run_simulation(self):
        if self.invalid:
            print('Simulation aborted because one of your parameters is out of range (see message above).')
        else:
            print('**********************************************************************')
            print('Summary of your inputs:')
            print('')
            print('START DATE: \t', self.Start)
            print('END DATE: \t', self.End)
            print('TIME STEP: \t', self.time_step)
            print('Sub-catchment number: \t', self.nsub)
            print('')
            print('Calibration parameters: ')
            for param in self.parameters:
                print(param, ':\t',self.parameters[param])
            print('**********************************************************************')
            print('')
            print('Running simulation, please wait.......')
            print('')
            #for date in self.sim_time:
            for i in range(len(self.Qt)):
                #print('Current time step: ',self.sim_time[i])
                #print('')
                if self.snow: 
                    QS = 0.
                    if self.temp[i]<=self.parameters['T0']: # snow
                        if self.Sw==0.:
                            self.Ss+=self.precip[i]
                        else:
                            QS = self.parameters['Csnow']*(self.parameters['T0']-self.temp[i])
                            if QS<=self.Sw:
                                self.Ss+=self.precip[i]+QS
                                self.Sw -= QS
                            else:
                                self.Ss+=self.precip[i]+self.Sw
                                self.Sw = 0.
                    else: # snowmelt/rainfall
                        if self.Ss==0.:
                            self.U+=self.precip[i]
                        else:
                            if self.Ss>=0.9999:
                                QS = self.parameters['Csnow']*(self.temp[i]-self.parameters['T0'])
                            else:
                                QS = self.parameters['CsnowM']*(self.temp[i]-self.parameters['T0'])
                            if QS<=self.Ss:
                                self.Sw +=self.precip[i]+QS
                                self.Ss -=QS
                            else:
                                self.Sw+=self.precip[i]+self.Ss
                                self.Ss = 0.
                            if self.Sw>=(self.parameters['Cswr']*(self.Ss+self.Sw)):
                                self.U+=self.Sw
                                self.Sw=0.
                    self.S[i] = self.Ss
                    if self.Ss>0.999:
                        self.pet[i] = 0.
                        
                else:
                    self.U+=self.precip[i] # no snow
    
                
                
                
                # Evapotranspiration
                if self.U>=self.pet[i]:
                    evap = self.pet[i]
                    self.U-=evap
                else:
                    Ea = (self.pet[i]-self.U)*(self.L/self.parameters['Lmax'])
                    evap = Ea + self.U
                    self.L-=Ea
                    self.U=0.
                self.ET[i]=evap
                
                # Interflow
                if (self.L/self.parameters['Lmax'])>self.parameters['TIF']:
                    self.QIF[i]=(1/self.parameters['CKIF'])*(((self.L/self.parameters['Lmax'])-self.parameters['TIF'])/(1-self.parameters['TIF']))*self.U
                    self.U-=self.QIF[i]
                else:
                    self.QIF[i]=0.
                
                # Surface storage
                if self.U>self.parameters['Umax']:
                    Pn = self.U-self.parameters['Umax']
                    self.U = self.parameters['Umax']
                    
                    # overland flow
                    if (self.L/self.parameters['Lmax'])>self.parameters['TOF']:
                        self.QOF[i] = self.parameters['CQOF']*((self.L/self.parameters['Lmax'])-self.parameters['TOF'])/(1-self.parameters['TOF'])*Pn
                    else:
                        self.QOF[i] = 0.
                        
                    # groundwater recharge
                    if (self.L/self.parameters['Lmax'])>self.parameters['TG']:
                        G = (Pn-float(self.QOF[i]))*((self.L/self.parameters['Lmax'])-self.parameters['TG'])/(1-self.parameters['TG'])
                    else:
                        G = 0.
                    self.G1[i]=G
                    if self.G1[i]<0.:
                        self.G1[i]=0.
                else:
                    self.QOF[i] = 0.
                    G = 0.
                    self.G1[i]=0.
                    Pn=0
                
                self.L+=(Pn-G-float(self.QOF[i]))
                
        # Flow routing
                # Linear routing baseflow
                bfp1 = (self.G1[i]*self.sub_area/self.fA)+((self.BF-(self.G1[i]*self.sub_area/self.fA)))*math.exp(-1/self.parameters['CKBF'])
                self.BF = bfp1
                self.BF_r[i] = self.BF
                
                # Two linear routing overland flow
                ifp1 = (self.QIF[i]*self.sub_area/self.fA)+(self.IFp-((self.QIF[i]*self.sub_area/self.fA)))*math.exp(-1/self.parameters['CK1'])
                self.IFp = ifp1
                ifp21 = self.IFp + (self.IF-self.IFp)*math.exp(-1/self.parameters['CK2'])
                self.IF = ifp21
                self.IF_r[i]=self.IF
                
                # Two linear routing overlabnd flow
                if (self.OFp*self.fA/self.sub_area)<self.OFmin:
                    self.TSK1[i]=self.parameters['CK1']
                else:
                    self.TSK1[i]=self.parameters['CK1']*(self.OF*self.fA/self.sub_area/self.OFmin)**(-self.Beta)
                    
                if (self.OF*self.fA/self.sub_area)<self.OFmin:
                    self.TSK2[i]=self.parameters['CK2']
                else:
                    self.TSK2[i]=self.parameters['CK2']*(self.OF*self.fA/self.sub_area/self.OFmin)**(-self.Beta)
                    
                if i == 0:
                    self.OFp = ((1-math.exp(-1/self.TSK1[i]))*math.exp(-1/self.TSK1[i])*self.OFp)/(1-math.exp(-1/self.TSK1[i])) + (-1/self.TSK1[i])*self.QOF[i]*self.sub_area/self.fA
                    self.OF = ((1-math.exp(-1/self.TSK2[i]))*math.exp(-1/self.TSK2[i])*self.OF)/(1-math.exp(-1/self.TSK2[i])) + (-1/self.TSK2[i])*self.OFp
                    self.OF_r[i]=self.OF
                else:
                    self.OFp = ((1-math.exp(-1/self.TSK1[i]))*math.exp(-1/self.TSK1[i-1])*self.OFp)/(1-math.exp(-1/self.TSK1[i-1])) + (-1/self.TSK1[i])*self.QOF[i]*self.sub_area/self.fA
                    self.OF = ((1-math.exp(-1/self.TSK2[i]))*math.exp(-1/self.TSK2[i-1])*self.OF)/(1-math.exp(-1/self.TSK2[i-1])) + (-1/self.TSK2[i])*self.OFp
                    self.OF_r[i]=self.OF
    
                # Total flow
                self.Qt[i] = self.OF+self.IF+self.BF
        
        
    def write_outputs(self,OUTPUT_dir):
        print('')
        print('Writing results to file...')
        print('')
        data_df = np.column_stack((self.ET,self.OF_r+self.IF_r,self.BF_r,self.S, self.IF_r, self.OF_r))
        df = pd.DataFrame(data = data_df, index = self.sim_time)
        df.columns= ['Evapotranspiration [mm/hr]', 'Quick flow [m3/s]', 'Slow flow/Baseflow [m3/s]', 'Snow pack [mm/hr]', 'Interflow [m3/s]', 'Overlandflow [m3/s]']
        df.index.name = 'Time'
        fname = os.path.join(OUTPUT_dir,'WB.csv')
        df.to_csv(fname, sep=';')
        
        Qt_df = pd.DataFrame(data = self.Qt, index=self.sim_time)
        Qt_df.columns= ['Total flow [m3/s]']
        Qt_df.index.name = 'Time'
        fname1 = os.path.join(OUTPUT_dir,'TF.csv')
        Qt_df[(self.EndWu+self.sim_time.freq):self.End].to_csv(fname1, sep=';')
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
                