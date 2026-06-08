import { INotebookTracker } from '@jupyterlab/notebook';
import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { ReactWidget } from '@jupyterlab/ui-components';
import React, { useState } from 'react';
import { Dashboard } from './components/Dashboard';
import { Profiler } from './components/Profiler';
import { StaticInfo } from './components/StaticInfo';

type Tab = 'monitor' | 'info' | 'profiler';

function RocmPanel(props: {
  settingRegistry: ISettingRegistry | null;
  notebooks: INotebookTracker | null;
}): JSX.Element {
  const [tab, setTab] = useState<Tab>('monitor');
  return (
    <div className="jp-rocm-root">
      <div className="jp-rocm-tabs">
        <button
          className={tab === 'monitor' ? 'active' : ''}
          onClick={() => setTab('monitor')}
        >
          GPU Monitor
        </button>
        <button
          className={tab === 'info' ? 'active' : ''}
          onClick={() => setTab('info')}
        >
          GPU Info
        </button>
        <button
          className={tab === 'profiler' ? 'active' : ''}
          onClick={() => setTab('profiler')}
        >
          Cell Profile
        </button>
      </div>
      <div className="jp-rocm-tabpanel">
        {tab === 'monitor' && <Dashboard />}
        {tab === 'info' && <StaticInfo />}
        {tab === 'profiler' && (
          <Profiler
            settingRegistry={props.settingRegistry}
            notebooks={props.notebooks}
          />
        )}
      </div>
    </div>
  );
}

export class RocmWidget extends ReactWidget {
  private _settingRegistry: ISettingRegistry | null;
  private _notebooks: INotebookTracker | null;

  constructor(
    settingRegistry: ISettingRegistry | null = null,
    notebooks: INotebookTracker | null = null
  ) {
    super();
    this._settingRegistry = settingRegistry;
    this._notebooks = notebooks;
    this.addClass('jp-rocm-widget');
    this.id = 'jupyterlab-rocm-panel';
    this.title.label = 'ROCm GPU';
    this.title.caption = 'AMD ROCm GPU monitor and profiler';
    this.title.closable = true;
  }

  render(): JSX.Element {
    return (
      <RocmPanel
        settingRegistry={this._settingRegistry}
        notebooks={this._notebooks}
      />
    );
  }
}
