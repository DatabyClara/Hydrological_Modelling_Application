# -*- coding: utf-8 -*-
"""
NAM rainfall-runoff model (Surface Hydrology course, IUPWARE).

Original version: esa, 2019.
Modernised 2026: works with current NumPy (2.x) and pandas (2.x / 3.x),
reads its inputs from CSV files and
runs the simulation loop on plain Python floats, which is ~100x faster.
The model equations are unchanged with respect to the 2019 version.

Inputs
    P  : rainfall [mm/time step]
    Ep : potential evapotranspiration [mm/time step]
    T  : mean temperature [deg C] (only if the snow module is used)
"""
import math
import os

import numpy as np
import pandas as pd

import NAM_setup as setup

MISSING_VALUE_THRESHOLD = 0  # values < 0 (e.g. -777) in the input files are treated as missing


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def _read_table(path):
    """Read an input table with columns Year, Month, Day, Hour, values...

    CSV is the standard format (comma separated, header in the first row,
    missing values coded as a negative number, e.g. -777). Excel files are
    still accepted, but reading large .xlsx files is very slow.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f'Input file not found: {path}')
    if path.lower().endswith(('.xlsx', '.xls')):
        print(f'  Reading {os.path.basename(path)} (Excel is slow; consider saving it as .csv)...')
        return pd.read_excel(path, sheet_name=0)
    return pd.read_csv(path)


def _to_series(df, column, name, mask_negative=True):
    """Build a time-indexed series for one column of an input table."""
    index = pd.DatetimeIndex(pd.to_datetime(dict(year=df['Year'], month=df['Month'],
                                                 day=df['Day'], hour=df['Hour'])))
    s = pd.Series(df.iloc[:, column].to_numpy(dtype=float), index=index, name=name)
    if mask_negative:
        s = s.where(s >= MISSING_VALUE_THRESHOLD)  # -777 etc. -> NaN
    return s, index[0], index[-1]


def _normalise_freq(time_step):
    """Accept 'H'/'h'/'D'/'d' (pandas >= 2.2 only accepts lowercase 'h')."""
    ts = str(time_step).strip().lower()
    if ts in ('h', 'hour', 'hourly'):
        return 'h'
    if ts in ('d', 'day', 'daily'):
        return 'D'
    raise ValueError(f"time_step must be 'H' (hourly) or 'D' (daily), got {time_step!r}")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class NAM:
    def __init__(self, DATA_dir):
        """Python version of the NAM model for the Surface Hydrology course.

        Global model parameters for calibration:
            1) Surface / root zone parameters
                Umax: Max water content in the surface storage (mm)
                Lmax: Max water content in the root zone storage (mm)
            2) Runoff parameters
                CQOF: overland flow runoff coefficient (-)
                CKIF: time constant for interflow (hours)
                CK1 : time constant for routing overland flow, reservoir 1 (hours)
                CK2 : time constant for routing overland flow, reservoir 2 (hours)
                TOF : root zone threshold value for overland flow (-)
                TIF : root zone threshold value for interflow (-)
            3) Groundwater parameters
                TG  : root zone threshold value for groundwater recharge (-)
                CKBF: time constant for routing baseflow (hours)
            4) Snow parameters
                Csnow: degree-day coefficient
                T0   : threshold temperature
        """
        print('\nLoading setup instructions...\n')
        self.time_step = _normalise_freq(setup.time_step)

        fh_sub_area = os.path.join(DATA_dir, setup.sub_area)
        fh_flow = os.path.join(DATA_dir, setup.flow)
        fh_pet = os.path.join(DATA_dir, setup.pet)
        fh_precip = os.path.join(DATA_dir, setup.precip)
        fh_temp = getattr(setup, 'Temp', None)

        # snow module switch
        self.snow = str(setup.snow).strip().lower() in ('yes', 'y', 'true', '1')
        if self.snow and fh_temp is None:
            print('Temperature file not provided. Snow melt cannot be simulated.\n')
            self.snow = False
        if self.snow:
            fh_temp = os.path.join(DATA_dir, fh_temp)

        self.nsub = setup.nsub

        # calibration parameters + range check
        parname, paramMin, paramMax, Fpar = setup.parname, setup.paramMin, setup.paramMax, setup.Fpar
        n_check = len(parname) if self.snow else len(parname) - 2  # last two are snow parameters
        self.invalid = False
        for lo, val, hi, name in list(zip(paramMin, Fpar, paramMax, parname))[:n_check]:
            if not (lo <= val <= hi):
                print(f'The parameter {name} = {val} is out of range [{lo}, {hi}]\n')
                self.invalid = True

        self.parameters = dict(zip(parname, Fpar))
        if self.snow:
            self.parameters['CsnowM'] = self.parameters['Csnow'] / 20
            self.parameters['Cswr'] = 0.00001

        # factor to convert mm/time step * km2 to m3/s
        # hourly: 1 mm/h over 1 km2 = 1/3.6 m3/s ; daily: 1 mm/d over 1 km2 = 1/86.4 m3/s
        self.fA = 3.6 if self.time_step == 'h' else 86.4

        self.Start = pd.Timestamp(setup.StartDate)
        self.End = pd.Timestamp(setup.EndDate)
        self.EndWu = pd.Timestamp(setup.EndWuDate)

        # ---- input data -----------------------------------------------------
        print('Loading input data...')
        col = 3 + self.nsub  # columns: Year, Month, Day, Hour, sub1, sub2, ...
        flow, start_flow, end_flow = _to_series(_read_table(fh_flow), col, 'ObsFlow')
        print('  Flow time series: completed!')
        pet, start_pet, end_pet = _to_series(_read_table(fh_pet), 4, 'PotET')  # one station
        print('  PET time series: completed!')
        precip, start_precip, end_precip = _to_series(_read_table(fh_precip), col, 'P')
        print('  Precipitation time series: completed!\n')
        if self.snow:
            temp, _, _ = _to_series(_read_table(fh_temp), col, 'T', mask_negative=False)

        self.sub_area = float(np.loadtxt(fh_sub_area, delimiter=',')[self.nsub - 1])

        # check that the simulation period is covered by the inputs
        first = max(start_flow, start_pet, start_precip)
        last = min(end_flow, end_pet, end_precip)
        if self.Start < first:
            print('WARNING: the selected start date is before the first input record')
            self.Start = first
            print('Setting the start date to the first date where all data is available:', self.Start, '\n')
        if self.End > last:
            print('WARNING: the selected end date is after the last input record')
            self.End = last
            print('Setting the end date to the last date where all data is available:', self.End, '\n')

        self.sim_time = pd.date_range(self.Start, self.End, freq=self.time_step)

        self.flow_df = flow.reindex(self.sim_time).to_frame()
        self.pet_df = pet.reindex(self.sim_time).to_frame()
        self.precip_df = precip.reindex(self.sim_time).to_frame()
        self.flow = self.flow_df['ObsFlow'].to_numpy()
        self.pet = self.pet_df['PotET'].to_numpy()
        self.precip = self.precip_df['P'].to_numpy()
        if self.snow:
            self.temp_df = temp.reindex(self.sim_time).to_frame()
            self.temp = self.temp_df['T'].to_numpy()

        for label, values in (('precipitation', self.precip), ('PET', self.pet)):
            missing = np.isnan(values)
            if missing.any():
                first_gap = self.sim_time[np.argmax(missing)]
                print(f'WARNING: {missing.sum()} missing {label} values in the simulation period '
                      f'(first gap: {first_gap}).\n'
                      '         From that moment the soil moisture becomes NaN and no new runoff is '
                      'generated:\n         the simulated flow only recedes. Choose a period or '
                      'sub-catchment with complete data.\n')

        # ---- initial states ---------------------------------------------------
        self.OFmin = setup.OFmin
        self.Beta = setup.Beta
        self.IF = setup.IF
        self.IFp = setup.IFp
        self.BF = setup.BF
        self.Ss = setup.Ss
        self.Sw = setup.Sw
        self.OFp = setup.OFp
        self.OF = setup.OF
        self.U = setup.relU * self.parameters['Umax']
        self.L = setup.relL * self.parameters['Lmax']

    # -----------------------------------------------------------------------
    def run_simulation(self):
        if self.invalid:
            print('Simulation aborted because one of your parameters is out of range (see message above).')
            return

        print('*' * 70)
        print('Summary of your inputs:\n')
        print('START DATE: \t', self.Start)
        print('END DATE: \t', self.End)
        print('TIME STEP: \t', self.time_step)
        print('Sub-catchment number: \t', self.nsub, '\n')
        print('Calibration parameters: ')
        for param, value in self.parameters.items():
            print(param, ':\t', value)
        print('*' * 70, '\n')
        print('Running simulation, please wait.......\n')

        p = self.parameters
        Umax, Lmax, CQOF, CKIF = p['Umax'], p['Lmax'], p['CQOF'], p['CKIF']
        CK1, CK2, TOF, TIF, TG, CKBF = p['CK1'], p['CK2'], p['TOF'], p['TIF'], p['TG'], p['CKBF']
        A, fA, OFmin, Beta = self.sub_area, self.fA, self.OFmin, self.Beta
        snow = self.snow
        if snow:
            Csnow, T0, CsnowM, Cswr = p['Csnow'], p['T0'], p['CsnowM'], p['Cswr']
            temp = self.temp.tolist()

        exp = math.exp
        kBF = exp(-1 / CKBF)
        k1 = exp(-1 / CK1)
        k2 = exp(-1 / CK2)

        # plain Python lists/floats are much faster than NumPy element access in a loop
        precip = self.precip.tolist()
        pet = self.pet.tolist()
        n = len(precip)
        QOF_out = [0.0] * n
        QIF_out = [0.0] * n
        G1_out = [0.0] * n
        ET_out = [0.0] * n
        S_out = [0.0] * n
        BF_out = [0.0] * n
        IF_out = [0.0] * n
        OF_out = [0.0] * n
        Qt_out = [0.0] * n
        TSK1_out = [0.0] * n
        TSK2_out = [0.0] * n

        U, L = self.U, self.L
        BF, IF, IFp, OF, OFp = self.BF, self.IF, self.IFp, self.OF, self.OFp
        Ss, Sw = self.Ss, self.Sw
        tsk1_prev = tsk2_prev = None

        for i in range(n):
            P = precip[i]
            Ep = pet[i]

            # ---- snow module / rainfall -----------------------------------
            if snow:
                T = temp[i]
                if T <= T0:  # snow
                    if Sw == 0.:
                        Ss += P
                    else:
                        QS = Csnow * (T0 - T)
                        if QS <= Sw:
                            Ss += P + QS
                            Sw -= QS
                        else:
                            Ss += P + Sw
                            Sw = 0.
                else:  # snowmelt / rainfall
                    if Ss == 0.:
                        U += P
                    else:
                        if Ss >= 0.9999:
                            QS = Csnow * (T - T0)
                        else:
                            QS = CsnowM * (T - T0)
                        if QS <= Ss:
                            Sw += P + QS
                            Ss -= QS
                        else:
                            Sw += P + Ss
                            Ss = 0.
                        if Sw >= (Cswr * (Ss + Sw)):
                            U += Sw
                            Sw = 0.
                S_out[i] = Ss
                if Ss > 0.999:
                    Ep = 0.
            else:
                U += P

            # ---- evapotranspiration ---------------------------------------
            if U >= Ep:
                evap = Ep
                U -= evap
            else:
                Ea = (Ep - U) * (L / Lmax)
                evap = Ea + U
                L -= Ea
                U = 0.
            ET_out[i] = evap

            # ---- interflow -------------------------------------------------
            if (L / Lmax) > TIF:
                QIF = (1 / CKIF) * (((L / Lmax) - TIF) / (1 - TIF)) * U
                U -= QIF
            else:
                QIF = 0.
            QIF_out[i] = QIF

            # ---- surface storage, overland flow, recharge ------------------
            if U > Umax:
                Pn = U - Umax
                U = Umax
                if (L / Lmax) > TOF:
                    QOF = CQOF * ((L / Lmax) - TOF) / (1 - TOF) * Pn
                else:
                    QOF = 0.
                if (L / Lmax) > TG:
                    G = (Pn - QOF) * ((L / Lmax) - TG) / (1 - TG)
                else:
                    G = 0.
                G1 = G if G >= 0. else 0.
            else:
                QOF = 0.
                G = 0.
                G1 = 0.
                Pn = 0
            QOF_out[i] = QOF
            G1_out[i] = G1

            L += (Pn - G - QOF)

            # ---- routing ---------------------------------------------------
            # linear reservoir baseflow
            g = G1 * A / fA
            BF = g + (BF - g) * kBF
            BF_out[i] = BF

            # two linear reservoirs interflow
            q = QIF * A / fA
            IFp = q + (IFp - q) * k1
            IF = IFp + (IF - IFp) * k2
            IF_out[i] = IF

            # two (non-linear) reservoirs overland flow
            if (OFp * fA / A) < OFmin:
                tsk1 = CK1
            else:
                tsk1 = CK1 * (OF * fA / A / OFmin) ** (-Beta)
            if (OF * fA / A) < OFmin:
                tsk2 = CK2
            else:
                tsk2 = CK2 * (OF * fA / A / OFmin) ** (-Beta)
            if tsk1_prev is None:
                tsk1_prev, tsk2_prev = tsk1, tsk2
            TSK1_out[i] = tsk1
            TSK2_out[i] = tsk2

            OFp = ((1 - exp(-1 / tsk1)) * exp(-1 / tsk1_prev) * OFp) / (1 - exp(-1 / tsk1_prev)) \
                + (-1 / tsk1) * QOF * A / fA
            OF = ((1 - exp(-1 / tsk2)) * exp(-1 / tsk2_prev) * OF) / (1 - exp(-1 / tsk2_prev)) \
                + (-1 / tsk2) * OFp
            OF_out[i] = OF
            tsk1_prev, tsk2_prev = tsk1, tsk2

            # ---- total flow ------------------------------------------------
            Qt_out[i] = OF + IF + BF

        # store final states and results as NumPy arrays (same names as before)
        self.U, self.L = U, L
        self.BF, self.IF, self.IFp, self.OF, self.OFp = BF, IF, IFp, OF, OFp
        self.Ss, self.Sw = Ss, Sw
        self.QOF = np.array(QOF_out)
        self.QIF = np.array(QIF_out)
        self.G1 = np.array(G1_out)
        self.ET = np.array(ET_out)
        self.S = np.array(S_out)
        self.BF_r = np.array(BF_out)
        self.IF_r = np.array(IF_out)
        self.OF_r = np.array(OF_out)
        self.Qt = np.array(Qt_out)
        self.TSK1 = np.array(TSK1_out)
        self.TSK2 = np.array(TSK2_out)

    # -----------------------------------------------------------------------
    def write_outputs(self, OUTPUT_dir):
        print('\nWriting results to file...\n')
        os.makedirs(OUTPUT_dir, exist_ok=True)
        df = pd.DataFrame({
            'Evapotranspiration [mm/hr]': self.ET,
            'Quick flow [m3/s]': self.OF_r + self.IF_r,
            'Slow flow/Baseflow [m3/s]': self.BF_r,
            'Snow pack [mm/hr]': self.S,
            'Interflow [m3/s]': self.IF_r,
            'Overlandflow [m3/s]': self.OF_r,
        }, index=self.sim_time)
        df.index.name = 'Time'
        df.to_csv(os.path.join(OUTPUT_dir, 'WB.csv'), sep=';')

        Qt_df = pd.DataFrame({'Total flow [m3/s]': self.Qt}, index=self.sim_time)
        Qt_df.index.name = 'Time'
        after_warmup = self.EndWu + pd.tseries.frequencies.to_offset(self.time_step)
        Qt_df.loc[after_warmup:self.End].to_csv(os.path.join(OUTPUT_dir, 'TF.csv'), sep=';')
