import math

def wind_turbine_power(turbine_type, blade_length, diameter, height, air_density, wind_speed, cp, kw, km, ke, ke_t, kt):
    """
    Calculate the power output of a wind turbine.  https://windcycle.energy/wind_turbine_calculator/
    Parameters:
    turbine_type (str): 'HAWT' for Horizontal-Axis Wind Turbine or 'VAWT' for Vertical-Axis Wind Turbine
    blade_length (float): Length of the blade in meters (used for HAWT)
    diameter (float): Diameter of the turbine in meters (used for VAWT)
    height (float): Height of the turbine in meters (used for VAWT)
    air_density (float): Air density in kg/m^3 (default is 1.225 kg/m^3)
    wind_speed (float): Wind speed in m/s
    cp (float): Power coefficient (must be less than the Betz limit of 0.593)
    kw (float): Wake losses (fraction, e.g., 0.03 for 3%)
    km (float): Mechanical losses (fraction, e.g., 0.003 for 0.3%)
    ke (float): Electrical losses (fraction, e.g., 0.015 for 1.5%)
    ke_t (float): Electrical transmission losses (fraction, e.g., 0.10 for 10%)
    kt (float): Downtime losses due to maintenance (fraction, e.g., 0.03 for 3%)

    Returns:
    float: Power output in watts
    """

    # Calculate the swept area (A)
    if turbine_type == 'HAWT':
        # For Horizontal-Axis Wind Turbine
        A = math.pi * blade_length ** 2
    elif turbine_type == 'VAWT':
        # For Vertical-Axis Wind Turbine
        A = diameter * height
    else:
        raise ValueError("Invalid turbine type. Use 'HAWT' or 'VAWT'.")

    # Calculate the available wind power (P_wind)
    P_wind = 0.5 * air_density * wind_speed ** 3 * A

    # Calculate the total efficiency (μ)
    mu = (1 - kw) * (1 - km) * (1 - ke) * (1 - ke_t) * (1 - kt) * cp

    # Calculate the output power (P_output)
    P_output = mu * P_wind

    return P_output

# Example usage:
turbine_type = 'HAWT'  # Horizontal-Axis Wind Turbine
blade_length = 50.0    # meters
diameter = 0.0         # not used for HAWT
height = 0.0           # not used for HAWT
air_density = 1.225    # kg/m^3
wind_speed = 12.0      # m/s
cp = 0.4               # Power coefficient (40%)
kw = 0.05              # Wake losses (5%)
km = 0.003             # Mechanical losses (0.3%)
ke = 0.015             # Electrical losses (1.5%)
ke_t = 0.10            # Electrical transmission losses (10%)
kt = 0.03              # Downtime losses (3%)

power_output = wind_turbine_power(turbine_type, blade_length, diameter, height, air_density, wind_speed, cp, kw, km, ke, ke_t, kt)
print(f"Estimated Power Output: {power_output:.2f} watts")

# Example usage:
turbine_type = 'HAWT'  # Horizontal-Axis Wind Turbine
blade_length = 1       # meters
diameter = 0.4         # not used for HAWT
height = 1.0         # not used for HAWT
air_density = 1.225    # kg/m^3
wind_speed = 12.0      # m/s
cp = 0.4               # Power coefficient (40%)
kw = 0.05              # Wake losses (5%)
km = 0.003             # Mechanical losses (0.3%)
ke = 0.015             # Electrical losses (1.5%)
ke_t = 0.10            # Electrical transmission losses (10%)
kt = 0.03              # Downtime losses (3%)
ew = 0.44              # euro per watt

power_output = wind_turbine_power(turbine_type, blade_length, diameter, height, air_density, wind_speed, cp, kw, km, ke, ke_t, kt)
print(f"Estimated Power Output: {power_output:.2f} watts")


# read pandas dataframe
import pandas as pd
df = pd.read_csv('~/Downloads/history.csv', decimal='.', sep=',')

# remove rows with missing values
df = df.dropna()

# remove where state is not a number
df = df[pd.to_numeric(df['state'], errors='coerce').notnull()]


# calculate seconds between rows
df['last_changed'] = pd.to_datetime(df['last_changed'])
df['time_diff'] = df['last_changed'].diff().dt.total_seconds()
df['time_diff'] = df['time_diff'].fillna(0)

df['state'] = df['state'].astype(float)

# convert km/h into m/s
df['speed'] = df['state'] / 3.6

# calculate power output in watts
df['power_output'] = df.apply(lambda row: wind_turbine_power('VAWT', blade_length, diameter , height , air_density , row['speed'], cp , kw, km, ke, ke_t, kt), axis=1)

# calculate energy output watts * seconds
df['energy_output'] = df['power_output'] * df['time_diff']

# convert into kWh
df['energy_output'] = df['energy_output'] / (3600*1000)

# calculate cumulative energy output
df['cumulative_energy_output'] = df['energy_output'].cumsum()

df['cumulative_euro_output'] = df['cumulative_energy_output'] * ew

# save to csv
df.to_csv('~/Downloads/history_output.csv', index=False)

# plot column diagram of energy output per day
import matplotlib.pyplot as plt

df['last_changed'] = pd.to_datetime(df['last_changed'])
df['date'] = df['last_changed'].dt.date

df.groupby('date')['energy_output'].sum().plot(kind='bar')
plt.title('Energy Output per Day')
plt.xlabel('Date')
plt.ylabel('Energy Output (kWh)')
plt.show()

# save plot as png
plt.savefig('~/Downloads/energy_output_per_day.png')

# plot line diagram of cumulative energy output
df.plot(x='last_changed', y='cumulative_energy_output')
plt.title('Cumulative Energy Output')
plt.xlabel('Date')
plt.ylabel('Cumulative Energy Output (kWh)')
plt.show()


# save plot as png
plt.savefig('~/Downloads/cumulative_energy_output.png')
