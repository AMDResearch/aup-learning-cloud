import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { Cell } from '@jupyterlab/cells';
import { ILauncher } from '@jupyterlab/launcher';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { OutputAreaModel, SimplifiedOutputArea } from '@jupyterlab/outputarea';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { LabIcon } from '@jupyterlab/ui-components';
import { PanelLayout, Widget } from '@lumino/widgets';
import { CellProfileFloatButton } from './cellProfileFloat';
import { RocmWidget } from './widget';

const rocmIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24">
<path class="jp-icon3 jp-icon-selectable" fill="#616161" d="M2 6.5A1.5 1.5 0 0 1 3.5 5h17A1.5 1.5 0 0 1 22 6.5v11a1.5 1.5 0 0 1-1.5 1.5H18v-2h-2.5v2h-12A1.5 1.5 0 0 1 2 17.5v-11Zm5 2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm8.5-2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/>
</svg>`;

const rocmIcon = new LabIcon({
  name: 'jupyterlab-rocm:icon',
  svgstr: rocmIconSvg
});

// Stopwatch/timer glyph for Cell Profile. Uses currentColor so it inherits the
// accent color from the surrounding button/menu styles.
const profileIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
<path d="M9 1h6v2H9z"/>
<path d="M19.03 7.39l1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.96 8.96 0 0 0 12 4a9 9 0 1 0 9 9 8.96 8.96 0 0 0-1.97-5.61zM13 14h-2V8h2z"/>
</svg>`;

const profileIcon = new LabIcon({
  name: 'jupyterlab-rocm:profile-icon',
  svgstr: profileIconSvg
});

namespace CommandIDs {
  export const open = 'jupyterlab-rocm:open';
  export const profileCell = 'jupyterlab-rocm:profile-cell';
}

// Default trace preset used by the Cell Profile button.
const CELL_PROFILE_FLAGS = '--preset kernel';

// Tracks the inline profile-result widget mounted under each cell so a repeat
// click disposes the previous result instead of stacking widgets.
const inlineResults = new WeakMap<Cell, Widget>();

/**
 * Build kernel code that loads the extension's cell magic (idempotently) and
 * runs it against the given cell source without altering the saved cell.
 */
function buildProfileCellCode(source: string): string {
  const loadExt =
    'try:\n' +
    '    _ip = get_ipython()\n' +
    "    if 'jupyterlab_rocm' not in getattr(_ip.extension_manager, 'loaded', {}):\n" +
    "        _ip.run_line_magic('load_ext', 'jupyterlab_rocm')\n" +
    'except Exception:\n' +
    '    pass\n';
  const run = `get_ipython().run_cell_magic('rocprofv3', ${JSON.stringify(
    CELL_PROFILE_FLAGS
  )}, ${JSON.stringify(source)})`;
  return loadExt + run;
}

/**
 * Run the profile code against the live kernel and render the rocprofv3 output
 * (the cell magic's inline HTML table) directly underneath the cell.
 */
function profileCellInline(
  cell: Cell,
  panel: NotebookPanel,
  rendermime: IRenderMimeRegistry,
  code: string
): void {
  // Dispose any previous inline result for this cell.
  const previous = inlineResults.get(cell);
  if (previous && !previous.isDisposed) {
    previous.dispose();
  }

  const container = new Widget();
  container.addClass('jp-rocm-inline-result');

  const row = document.createElement('div');
  row.className = 'jp-rocm-inline-row';

  const gutter = document.createElement('div');
  gutter.className = 'jp-rocm-inline-gutter';
  gutter.setAttribute('aria-hidden', 'true');
  row.appendChild(gutter);

  const content = document.createElement('div');
  content.className = 'jp-rocm-inline-content';

  const header = document.createElement('div');
  header.className = 'jp-rocm-inline-header';

  const title = document.createElement('span');
  title.className = 'jp-rocm-inline-title';
  title.textContent = 'Cell Profile';
  header.appendChild(title);

  const close = document.createElement('button');
  close.className = 'jp-rocm-inline-close';
  close.title = 'Dismiss profile result';
  close.textContent = '\u2715';
  close.onclick = () => container.dispose();
  header.appendChild(close);

  content.appendChild(header);

  const model = new OutputAreaModel({ trusted: true });
  const outputArea = new SimplifiedOutputArea({ model, rendermime });
  outputArea.addClass('jp-rocm-inline-output');
  content.appendChild(outputArea.node);

  row.appendChild(content);
  container.node.appendChild(row);

  const layout = cell.layout as PanelLayout;
  layout.addWidget(container);
  inlineResults.set(cell, container);

  void SimplifiedOutputArea.execute(code, outputArea, panel.sessionContext);
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab-rocm:plugin',
  description:
    'Monitor AMD ROCm GPU usage (amd-smi) and run rocprofv3 profiling inside JupyterLab.',
  autoStart: true,
  optional: [
    ICommandPalette,
    ILauncher,
    INotebookTracker,
    ILayoutRestorer,
    IRenderMimeRegistry
  ],
  activate: (
    app: JupyterFrontEnd,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    notebooks: INotebookTracker | null,
    restorer: ILayoutRestorer | null,
    rendermime: IRenderMimeRegistry | null
  ) => {
    const { commands, shell } = app;

    // Create the panel once and dock it in the left sidebar so it is visible
    // by default near the top of the leftmost column.
    const widget = new RocmWidget();
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
      label: 'Cell Profile',
      caption:
        'Profile the active PyTorch GPU cell with torch.profiler; results appear under the cell',
      icon: profileIcon,
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
        const code = buildProfileCellCode(source);

        // Preferred path: render the rocprofv3 result inline under the cell.
        if (rendermime) {
          profileCellInline(cell, panel, rendermime, code);
          return;
        }

        // Fallback (no rendermime): run silently and surface results in the
        // left sidebar instead.
        kernel.requestExecute({
          code,
          silent: true,
          store_history: false
        });
        shell.activateById(widget.id);
      }
    });

    if (notebooks) {
      void new CellProfileFloatButton(
        notebooks,
        commands,
        CommandIDs.profileCell,
        profileIcon
      );
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
