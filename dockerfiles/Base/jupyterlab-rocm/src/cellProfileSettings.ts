import { ISettingRegistry } from '@jupyterlab/settingregistry';

export const PLUGIN_ID = 'jupyterlab-rocm:plugin';

export type CellProfileMode = 'full' | 'live';

export interface ICellProfileSettings {
  cellProfileMode: CellProfileMode;
  timeWindowSeconds: number;
  timeWarmupSeconds: number;
  recordShapes: boolean;
  profileMemory: boolean;
  withStack: boolean;
  keepTrace: boolean;
}

export const DEFAULT_CELL_PROFILE_SETTINGS: ICellProfileSettings = {
  cellProfileMode: 'full',
  timeWindowSeconds: 2,
  timeWarmupSeconds: 0,
  recordShapes: false,
  profileMemory: false,
  withStack: false,
  keepTrace: false
};

/**
 * Read the Cell Profile settings from a loaded ISettings object, falling back
 * to defaults for any missing keys.
 */
export function readCellProfileSettings(
  settings: ISettingRegistry.ISettings | null
): ICellProfileSettings {
  if (!settings) {
    return { ...DEFAULT_CELL_PROFILE_SETTINGS };
  }
  const composite = settings.composite as Partial<ICellProfileSettings>;
  return { ...DEFAULT_CELL_PROFILE_SETTINGS, ...composite };
}

/**
 * Translate Cell Profile settings into the ``%%rocprofv3`` magic flag string.
 * This is the single source of truth shared by the toolbar button and any
 * other GUI entry point so it stays consistent with the magic.
 *
 * The toolbar button always profiles the whole cell run; the time-window
 * sampling path now lives under Live capture (sidebar), not the magic flags.
 */
export function buildCellProfileFlags(settings: ICellProfileSettings): string {
  const flags: string[] = ['--preset', 'kernel'];

  if (settings.recordShapes) {
    flags.push('--shapes');
  }
  if (settings.profileMemory) {
    flags.push('--memory');
  }
  if (settings.withStack) {
    flags.push('--stack');
  }
  if (settings.keepTrace) {
    flags.push('--trace');
  }

  return flags.join(' ');
}
