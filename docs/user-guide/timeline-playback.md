# Timeline playback

The acquisition timeline at the bottom lists NISAR pass dates for the study area. **Ascendente** (Ascending) and **Descendente** (Descending) filter the passes; at least one must stay selected ("Debe quedar al menos una pasada").

## Play an animation

1. Press play. The NISAR layer turns on.
2. The button turns into a spinner and the bar reads "Preparando animación… Teselas N/M" (Preparing animation… Tiles N/M) while one frame per pass date is composed from the mosaic tiles.
3. When the frames are ready, playback starts at 450 ms per frame. Dates without data are skipped.

Press the spinner to cancel. Playback needs at least two frames; otherwise it stops.

Frames are kept while the area and date range stay the same, so a second play starts immediately. Changing the passes stops playback.

```{note}
Cancelling only stops playback. Frame building continues in the background to fill the cache.
```
