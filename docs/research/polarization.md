# Polarization

The challenge asks which polarizations reveal which changes. This page collects
what the team's notebooks and reference material state. It is a working
discussion, not a validated study.

## SAR basics

SAR is an active microwave sensor. It sees day and night and through clouds. The
return depends on surface roughness and dielectric constant. Water has a high
dielectric constant, so SAR is sensitive to water bodies, floods and soil
moisture. Interferometry (InSAR) measures deformation at centimeter scale.

## What NISAR GCOV provides

- GCOV delivers calibrated, terrain-corrected gamma-0 **power**, not raw complex
  amplitude.
- `HHHH` is the power of the HH channel; `HVHV` is the power of the HV channel.
  They are not RGB images.
- Off-diagonal terms such as `HHHV` are complex and carry amplitude and phase
  relations. They are outside the first model.
- Frequency A and B are both acquisition frequencies of the **L-band** instrument
  in `LSAR` paths; they are not L-band versus S-band. Frequency B pixels are
  usually coarser.

## Which polarization shows which change

| Polarization | Mechanism | Change it highlights |
|---|---|---|
| HH (co-pol) | Specular reflection on open water gives low return; under vegetation, water plus trunks create a **double bounce** that raises HH. | Open water extent; flooding beneath forest canopy. |
| HV (cross-pol) | **Volume** scattering inside the canopy. | Forest loss and burns reduce HV. |
| L-band vs C-band | The longer L-band wavelength penetrates the canopy further than C-band (Sentinel-1). | Compare NISAR with OPERA RTC-S1 / DSWx-S1 to see sub-canopy water. |

The deployed U-Net water model uses HH only. The training pilot extracts both
`HHHH` and `HVHV` from frequency A; the value of adding frequency B is to be
measured by comparing A and A+B models.

## Ice

The challenge also asks about polarization over ice. The notebooks do not study
ice; glacier cases are listed only as context (East Antarctic glaciers in ISRO
S-band data).
