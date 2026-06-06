import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette, ToolbarButton } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { LabIcon } from '@jupyterlab/ui-components';
import { RocmWidget } from './widget';

const rocmIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24">
<path class="jp-icon3 jp-icon-selectable" fill="#616161" d="M2 6.5A1.5 1.5 0 0 1 3.5 5h17A1.5 1.5 0 0 1 22 6.5v11a1.5 1.5 0 0 1-1.5 1.5H18v-2h-2.5v2h-12A1.5 1.5 0 0 1 2 17.5v-11Zm5 2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm8.5-2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/>
</svg>`;

const rocmIcon = new LabIcon({
  name: 'jupyterlab-rocm:icon',
  svgstr: rocmIconSvg
});

namespace CommandIDs {
  export const open = 'jupyterlab-rocm:open';
  export const profileCell = 'jupyterlab-rocm:profile-cell';
}

// Default trace preset used by the toolbar "Profile cell" button.
const CELL_PROFILE_FLAGS = '--preset kernel';

/**
 * Build kernel code that loads the extension's cell magic (idempotently) and
 * runs it against the given cell source without altering the saved cell.
 */
function buildProfileCellCode(source: string): string {
  const loadExt =
    "try:\n" +
    "    get_ipython().run_line_magic('load_ext', 'jupyterlab_rocm')\n" +
    'except Exception:\n' +
    '    pass\n';
  const run = `get_ipython().run_cell_magic('rocprofv3', ${JSON.stringify(
    CELL_PROFILE_FLAGS
  )}, ${JSON.stringify(source)})`;
  return loadExt + run;
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-rocm:plugin',
  description:
    'Monitor AMD ROCm GPU usage (amd-smi) and run rocprofv3 profiling inside JupyterLab.',
  autoStart: true,
  optional: [ICommandPalette, ILauncher, INotebookTracker, ILayoutRestorer],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    notebooks: INotebookTracker | null,
    restorer: ILayoutRestorer | null
  ) => {
    const { commands, shell } = app;

    const getCurrentNotebook = (): string | null => {
      const current = notebooks?.currentWidget;
      return current ? current.context.path : null;
    };

    // Create the panel once and dock it in the left sidebar so it is visible
    // by default near the top of the leftmost column.
    const widget = new RocmWidget(getCurrentNotebook);
    widget.id = 'jupyterlab-rocm-sidebar';
    widget.title.icon = rocmIcon;
    // Show only the icon in the sidebar tab (no rotated text label); the
    // caption still provides a hover tooltip.
    widget.title.label = '';
    widget.title.caption = 'AMD ROCm GPU monitor and profiler';
    widget.title.closable = false;

    shell.add(widget, 'left', { rank: 50 });

    commands.addCommand(CommandIDs.open, {
      label: 'ROCm GPU Monitor',
      caption: 'Reveal the AMD ROCm GPU monitor and profiler',
      icon: rocmIcon,
      execute: () => {
        shell.activateById(widget.id);
      }
    });

    commands.addCommand(CommandIDs.profileCell, {
      label: 'ROCm: Profile active cell (rocprofv3)',
      caption:
        'Profile the active notebook cell with rocprofv3 by attaching to the live kernel',
      icon: rocmIcon,
      isEnabled: () => !!notebooks?.activeCell,
      execute: async () => {
        const panel = notebooks?.currentWidget;
        const cell = panel?.content.activeCell;
        if (!panel || !cell) {
          return;
        }
        const kernel = panel.sessionContext.session?.kernel;
        if (!kernel) {
          return;
        }
        const source = cell.model.sharedModel.getSource();
        if (!source.trim()) {
          return;
        }
        kernel.requestExecute({
          code: buildProfileCellCode(source),
          silent: true,
          store_history: false
        });
        shell.activateById(widget.id);
      }
    });

    if (notebooks) {
      notebooks.widgetAdded.connect((_, panel: NotebookPanel) => {
        const button = new ToolbarButton({
          icon: rocmIcon,
          label: 'Profile cell',
          tooltip:
            'Profile the active cell with rocprofv3 (attaches to the live kernel)',
          onClick: () => {
            void commands.execute(CommandIDs.profileCell);
          }
        });
        panel.toolbar.insertItem(10, 'rocmProfileCell', button);
      });
    }

    if (palette) {
      palette.addItem({ command: CommandIDs.open, category: 'ROCm' });
      palette.addItem({ command: CommandIDs.profileCell, category: 'ROCm' });
    }

    if (launcher) {
      launcher.add({
        command: CommandIDs.open,
        category: 'Other',
        rank: 1
      });
    }

    if (restorer) {
      restorer.add(widget, 'jupyterlab-rocm');
    }
  }
};

export default plugin;
