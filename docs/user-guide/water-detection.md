# Water detection (U-Net)

Luzsi includes a U-Net that maps surface water from NISAR L-band HH backscatter. It is the reference example for the **Modelo propio** (Own model) section; see {doc}`custom-model` for the connection steps.

## Model

- Name: `NISAR_UNET_MODELO_V1`, a small U-Net trained only on the Okavango Delta.
- Input: NISAR L2 GCOV HH backscatter, averaged to 30 m, in dB.
- Output: water probability. The map shows it in blue; probabilities of 0.05 or below are transparent.

## Run it

1. Start the model client in `model_service/water_unet/` with the token from the **Modelo propio** section (see {doc}`custom-model`).
2. Select a point of interest, or else make sure a study area exists. The model runs on the selected point's square, otherwise on the last study area.
3. Click **Ejecutar modelo** (Run model).

The area side must not exceed 60 km. The first run on an area reads 50 to 110 MB of NISAR data and takes about 22 to 40 s. Repeated runs use the cache.

## Read the result

The result panel shows the label, the scene, a blue legend, the water fraction and an opacity slider.

```{note}
The model was trained on one region. Expect weaker results elsewhere.
```

## Threshold layer

The **Capas** section also has a simple alternative: the NISAR layer mode **Agua (umbral)** (Water, threshold) next to **Color (suavizado)** (Color, smoothed). It is a threshold display, not the U-Net.
