# Overview

## The challenge

*Dancing with the SARs* (NASA Space Apps Challenge 2026, Earth Science track) asks teams
to build an interactive application that uses NISAR radar data to track and visualize
changes on the Earth's surface. Candidate change types include:

- wetland and flood extent (expansion and retreat),
- deforestation and wildfire,
- crop type and health,
- soil moisture,
- glaciers and sea ice,
- earthquake deformation and land subsidence.

The expected workflow is: choose a study area, download free NISAR data, optionally add
optical imagery or GIS layers for context, and present the result interactively (change
maps, time-series animation, dashboards, image sliders, web maps or story maps).
Teams should also hypothesize the physical drivers of the observed change, discuss which
polarizations reveal which changes, and consider future NISAR use cases.

## Why SAR and NISAR

Synthetic Aperture Radar is an active microwave sensor. It images day and night and
through clouds. The backscattered signal is sensitive to surface roughness and to the
dielectric constant of the target. Water has a high dielectric constant and a smooth
surface, so open water, floods and soil moisture stand out clearly. Interferometric SAR
(InSAR) measures ground deformation at centimeter scale.

NISAR is a joint NASA-ISRO mission carrying L-band and S-band radars with multiple
polarizations, providing frequent, free and open global coverage.

## What the application does

- Search NISAR scenes over a user-selected area of interest and fetch cropped data.
- Show radar imagery on an interactive web map, with land cover, elevation, natural
  features and place labels for context.
- Play time series of scenes as an animation.
- Detect surface water with a U-Net model, either on the server or through a
  user-run external model service.
- Guide new users with an onboarding tour.

The project is open source and aimed at scientists, managers, educators, decision makers
and the general public.
