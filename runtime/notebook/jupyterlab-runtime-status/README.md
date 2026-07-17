# @auplc/jupyterlab-runtime-status

`@auplc/jupyterlab-runtime-status` is an internal/no-publish package for the JupyterLab runtime countdown. It includes a JupyterLab frontend status item and a Python server companion endpoint.

## Runtime Display

The frontend status item fetches same-origin safe metadata from the Python server companion endpoint, then uses `@auplc/runtime-status` for display decisions and text rendering. This keeps JupyterLab behavior aligned with the VS Code helper path without exposing extra pod metadata.

Runtime status settings match the shared helper defaults:

```ts
{
  template: "Runtime: {remaining}",
  hideWhenUnavailable: true,
  hideWhenUnlimited: true,
  updateIntervalMs: 1000,
}
```

`updateIntervalMs` has minimum `250`. Supported template tokens are `{remaining}`, `{remainingSeconds}`, `{totalMinutes}`, and `{elapsedSeconds}`.

When metadata contains `AUPLC_RUNTIME_UNLIMITED=true`, the status item follows runtime-unlimited behavior from the shared helper. It is hidden by default and does not show a fake `4320` minute or `72:00:00` countdown.

## Related Consumers

VS Code support lives in `runtime/code-server/extensions/auplc-hub-link`. That extension consumes `@auplc/runtime-status` through the pnpm workspace and preserves the finite display as `$(clock) Runtime: HH:MM:SS`.

The shared helper package has no UI or runtime dependencies. If this runtime display system needs to move outside the monorepo later, extract `@auplc/runtime-status` first, then keep this JupyterLab package as the notebook-specific consumer.

## Maintenance

Run these commands from `runtime`:

```bash
pnpm --filter @auplc/jupyterlab-runtime-status build
pnpm --filter @auplc/jupyterlab-runtime-status test
```

For shared logic changes, also run:

```bash
pnpm --filter @auplc/runtime-status test
pnpm --filter @auplc/runtime-status typecheck
pnpm --filter @auplc/runtime-status build
```

Keep this package private and internal unless packaging policy changes. Don't add public registry or release workflow notes here.
