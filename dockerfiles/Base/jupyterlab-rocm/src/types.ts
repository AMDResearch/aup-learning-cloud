// Shared types mirroring the JSON payloads returned by the server extension.

export interface IBackendStatus {
  available: boolean;
  error: string | null;
  import_error?: string | null;
  init_error?: string | null;
}

export interface IRocprofAttachStatus {
  supported: boolean;
  ptrace_scope: number | null;
  tool_attach_env: boolean;
  hint: string | null;
}

export interface IRocprofStatus {
  available: boolean;
  error: string | null;
  executable?: string;
  presets?: string[];
  attach?: IRocprofAttachStatus;
}

export interface IDeviceInfo {
  index: number;
  name: string;
  serial: string | null;
  manufacturer: string | null;
  market_name: string | null;
  vram_total_mb: number | null;
}

export interface IGpusResponse {
  status: IBackendStatus;
  devices: IDeviceInfo[];
  rocprof: IRocprofStatus;
}

export interface IGpuActivity {
  gfx: number | null;
  umc: number | null;
  mm: number | null;
}

export interface IGpuVram {
  total_mb: number | null;
  used_mb: number | null;
  percent: number | null;
}

export interface IGpuPower {
  watts: number | null;
  limit_watts: number | null;
}

export interface IGpuClock {
  cur_mhz: number | null;
  max_mhz: number | null;
}

export interface IGpuProcess {
  pid: number | null;
  name: string | null;
  gtt_mem: number | null;
  vram_mem: number | null;
  mem_usage: number | null;
  cu_percent: number | null;
  sdma_us: number | null;
}

export interface IGpuSample {
  index: number;
  name: string;
  activity: IGpuActivity;
  vram: IGpuVram;
  power: IGpuPower;
  temperature_c: number | null;
  clock: IGpuClock | null;
  processes: IGpuProcess[];
}

export interface IMetricsSample {
  available: boolean;
  error: string | null;
  timestamp?: number;
  gpus: IGpuSample[];
}

export interface IKernelStat {
  name: string;
  calls: number;
  total_ns: number;
  avg_ns: number;
  min_ns: number;
  max_ns: number;
  percent: number;
}

export interface IMemoryCopyStat {
  direction: string;
  calls: number;
  total_ns: number;
}

export interface IOperatorStat {
  name: string;
  calls: number;
  cpu_total_ns: number;
  self_cpu_ns: number;
  gpu_total_ns: number;
  self_gpu_ns: number;
  cpu_mem: number;
  self_cpu_mem: number;
  gpu_mem: number;
  self_gpu_mem: number;
  input_shapes: string | null;
  stack: string[] | null;
  percent: number;
}

export interface IProfileJob {
  id: string;
  target_type: string;
  target: string;
  preset: string;
  status: 'queued' | 'running' | 'done' | 'error';
  error: string | null;
  returncode: number | null;
  command: string;
  created: number;
  finished: number | null;
  extra?: {
    backend?: string;
    mode?: 'full' | 'live';
    approx?: boolean;
    trace_available?: boolean;
    window_s?: number;
    warmup_s?: number;
    [key: string]: any;
  };
  stdout?: string;
  stderr?: string;
  kernels?: IKernelStat[];
  operators?: IOperatorStat[];
  memory_copies?: IMemoryCopyStat[];
  summary?: {
    kernel_count: number;
    total_kernel_ns: number;
    total_dispatches: number;
    operator_count?: number;
    self_cpu_total_ns?: number;
    self_gpu_total_ns?: number;
  };
}

export interface IProfileListResponse {
  jobs: IProfileJob[];
  rocprof: IRocprofStatus;
}

export interface IStaticResponse {
  available: boolean;
  error: string | null;
  executable?: string;
  list: Record<string, any>[];
  static: Record<string, any>[];
}
