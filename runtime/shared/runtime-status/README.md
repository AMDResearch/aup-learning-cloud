# @auplc/runtime-status

`@auplc/runtime-status` is an internal/no-publish package for shared runtime countdown logic. It has no UI or runtime dependencies, so VS Code, JupyterLab, and future consumers can share the same metadata parsing, visibility rules, and text rendering.

## Settings

Defaults:

```ts
{
  template: "Runtime: {remaining}",
  hideWhenUnavailable: true,
  hideWhenUnlimited: true,
  updateIntervalMs: 1000,
}
```

`updateIntervalMs` is clamped to a minimum `250`.

Supported template tokens are `{remaining}`, `{remainingSeconds}`, `{totalMinutes}`, and `{elapsedSeconds}`.

When metadata contains `AUPLC_RUNTIME_UNLIMITED=true`, the helper returns runtime-unlimited state. That state is hidden by default through `hideWhenUnlimited: true`, and it never creates a fake `4320` minute or `72:00:00` countdown.

## Consumers

`runtime/code-server/extensions/auplc-hub-link` consumes this helper through the pnpm workspace and keeps the finite VS Code display as `$(clock) Runtime: HH:MM:SS`.

`@auplc/jupyterlab-runtime-status` consumes the same helper after its Python server companion exposes same-origin safe runtime metadata to the frontend status item.

## Maintenance

Run these commands from `runtime`:

```bash
pnpm --filter @auplc/runtime-status test
pnpm --filter @auplc/runtime-status typecheck
pnpm --filter @auplc/runtime-status build
```

Keep this package free of UI framework, browser, editor, Jupyter, and server dependencies. Because the package only exports TypeScript helper logic with ESM, CJS, and type outputs, it can be externalized later if desired.
