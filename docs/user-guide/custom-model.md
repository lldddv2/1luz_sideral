# Custom model

The **Modelo propio** (Own model) section connects any model running on your own computer. The model pulls jobs from the backend over HTTP, processes NISAR input and uploads a result that the app draws on the map. The water U-Net ({doc}`water-detection`) is one example.

## Connect

1. Open **Modelo propio**.
2. Click **Conectar modelo** (Connect model). This creates a session token. The app does not create a token until you click.
3. Copy the token with the copy button. The regenerate button creates a new one.
4. Start your model with that token. Follow **Guía de uso** (Usage guide) for the exact commands.

The status line reads **Conectado: name · label** (Connected) or **Desconectado** (Disconnected). A model counts as connected when it contacted the backend in the last 30 s.

If token creation fails, the app shows "No se pudo generar el token (¿backend actualizado?)" (Could not create the token, is the backend up to date?).

```{note}
The token lasts 2 hours and belongs to one browser session. It is kept in session storage, so a page reload reconnects.
```

## Usage guide

**Guía de uso** opens a dialog with seven `curl` steps, filled with the real server address, token and job id:

1. Get a token.
2. Say hello (`POST /api/models/hello`), with a PowerShell variant.
3. Run the model from the UI.
4. Fetch the next job (`GET /api/models/jobs/next`).
5. Download the input GeoTIFF.
6. Process it.
7. Upload the result (`POST /api/models/jobs/{id}/result`).

Close the dialog with `Esc`, the X button or a click on the backdrop.

## Live updates (SSE)

The page listens to `/api/models/events` with Server-Sent Events. A `status` event updates the connection line. A `job` event updates the job state.

## Run a job

**Ejecutar modelo** (Run model) is disabled until a model is connected. A hint below it names the target area. The job goes through these states:

- **En cola** (Queued): waiting for the model to pick it up.
- **Procesando** (Processing): the model took the job.
- **Listo** (Done): the result is ready.
- **Error**: the message explains the cause, for example a missing polarization.

## Result

When the job is done the panel shows **Listo** with the label, **Escena** (Scene), a legend, a statistics line, **Mostrar resultado** (Show result) and an opacity slider. The legend depends on the model output type:

- `probability`: blue scale.
- `continuous`: viridis gradient from min to max with units.
- `classes`: one color swatch per class.
