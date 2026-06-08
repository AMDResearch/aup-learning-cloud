import { Cell } from '@jupyterlab/cells';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { LabIcon } from '@jupyterlab/ui-components';
import { CommandRegistry } from '@lumino/commands';

/**
 * A fixed-position "Cell Profile" button that tracks the active notebook cell.
 */
export class CellProfileFloatButton {
  private _button: HTMLButtonElement;
  private _notebooks: INotebookTracker;
  private _commands: CommandRegistry;
  private _commandId: string;
  private _rafId: number | null = null;
  private _resizeObserver: ResizeObserver | null = null;
  private _observedCell: Cell | null = null;
  private _boundPanel: NotebookPanel | null = null;

  constructor(
    notebooks: INotebookTracker,
    commands: CommandRegistry,
    commandId: string,
    icon: LabIcon
  ) {
    this._notebooks = notebooks;
    this._commands = commands;
    this._commandId = commandId;

    this._button = document.createElement('button');
    this._button.type = 'button';
    this._button.className = 'jp-rocm-cell-profile-float';
    this._button.title =
      'Profile the active PyTorch GPU cell with torch.profiler in the live kernel';
    this._button.setAttribute('aria-label', 'Cell Profile');
    this._button.hidden = true;

    const iconHost = document.createElement('span');
    iconHost.className = 'jp-rocm-cell-profile-float-icon';
    void icon.element({ container: iconHost, height: '15px', width: '15px' });
    this._button.appendChild(iconHost);

    this._button.addEventListener('click', () => {
      void this._commands.execute(this._commandId);
    });

    document.body.appendChild(this._button);

    notebooks.currentChanged.connect(this._onTrackerChanged, this);
    notebooks.activeCellChanged.connect(this._scheduleUpdate, this);
    notebooks.widgetAdded.connect(this._onNotebookAdded, this);
    notebooks.forEach(panel => this._onNotebookAdded(notebooks, panel));

    window.addEventListener('scroll', this._onScroll, true);
    window.addEventListener('resize', this._onScroll, { passive: true });

    this._onTrackerChanged(notebooks, notebooks.currentWidget);
  }

  dispose(): void {
    if (this._rafId !== null) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    this._clearResizeObserver();
    window.removeEventListener('scroll', this._onScroll, true);
    window.removeEventListener('resize', this._onScroll);
    this._button.remove();
  }

  private _onNotebookAdded(_: INotebookTracker, panel: NotebookPanel): void {
    panel.content.activeCellChanged.connect(this._scheduleUpdate, this);
    panel.content.selectionChanged.connect(this._scheduleUpdate, this);
    panel.disposed.connect(() => {
      if (this._boundPanel === panel) {
        this._boundPanel = null;
        this._scheduleUpdate();
      }
    });
  }

  private _onTrackerChanged(_sender: INotebookTracker, panel: NotebookPanel | null): void {
    this._boundPanel = panel;
    this._scheduleUpdate();
  }

  private _onScroll = (): void => {
    this._scheduleUpdate();
  };

  private _scheduleUpdate = (): void => {
    if (this._rafId !== null) {
      return;
    }
    this._rafId = requestAnimationFrame(() => {
      this._rafId = null;
      this._updatePosition();
    });
  };

  private _observeCell(cell: Cell | null): void {
    if (this._observedCell === cell) {
      return;
    }
    this._clearResizeObserver();
    this._observedCell = cell;
    if (!cell || typeof ResizeObserver === 'undefined') {
      return;
    }
    this._resizeObserver = new ResizeObserver(() => this._scheduleUpdate());
    this._resizeObserver.observe(cell.node);
    const input = cell.node.querySelector('.jp-Cell-inputWrapper');
    if (input) {
      this._resizeObserver.observe(input);
    }
  }

  private _clearResizeObserver(): void {
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
    this._observedCell = null;
  }

  private _updatePosition(): void {
    const panel = this._notebooks.currentWidget;
    const cell = this._notebooks.activeCell;

    if (!panel || !cell || cell.model.type !== 'code') {
      this._observeCell(null);
      this._button.hidden = true;
      return;
    }

    this._observeCell(cell);

    const panelRect = panel.node.getBoundingClientRect();
    if (panelRect.width <= 0 || panelRect.height <= 0) {
      this._button.hidden = true;
      return;
    }

    const cellRect = cell.node.getBoundingClientRect();
    if (cellRect.width <= 0 || cellRect.height <= 0) {
      this._button.hidden = true;
      return;
    }

    // Anchor vertically to the input row; horizontally place the ball in the
    // strip between the cell's left edge and the blue input collapser bar.
    const inputWrapper = cell.node.querySelector('.jp-Cell-inputWrapper');
    const anchor = inputWrapper?.getBoundingClientRect() ?? cellRect;
    const collapser = cell.node.querySelector('.jp-Cell-inputCollapser');
    const collapserRect = collapser?.getBoundingClientRect() ?? anchor;
    const margin = 6;
    const visible =
      anchor.bottom > panelRect.top &&
      anchor.top < panelRect.bottom &&
      cellRect.right > panelRect.left;

    if (!visible) {
      this._button.hidden = true;
      return;
    }

    const source = cell.model.sharedModel.getSource().trim();
    this._button.disabled = source.length === 0;
    this._button.hidden = false;

    const buttonRect = this._button.getBoundingClientRect();
    const buttonWidth = buttonRect.width > 0 ? buttonRect.width : 24;
    const buttonHeight = buttonRect.height > 0 ? buttonRect.height : 24;

    // Place the ball just to the LEFT of the blue collapser bar: its right edge
    // sits `gap` px left of the bar. If the strip is narrow the ball overhangs
    // further left (into the padding) rather than covering the bar.
    const gap = 4;
    let left = collapserRect.left - gap - buttonWidth;
    left = Math.max(left, 2);

    let top = anchor.top + (anchor.height - buttonHeight) / 2;
    const minTop = Math.max(panelRect.top + margin, margin);
    const maxTop = Math.min(
      panelRect.bottom - buttonHeight - margin,
      window.innerHeight - buttonHeight - margin
    );
    top = Math.max(minTop, Math.min(top, maxTop));

    this._button.style.top = `${top}px`;
    this._button.style.left = `${left}px`;
  }
}
