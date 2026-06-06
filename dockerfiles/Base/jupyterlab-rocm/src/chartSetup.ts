// Register the minimal set of chart.js components we need so the bundle stays
// small and tree-shakeable.
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip
} from 'chart.js';

let registered = false;

export function ensureChartsRegistered(): void {
  if (registered) {
    return;
  }
  Chart.register(
    LineController,
    BarController,
    LineElement,
    PointElement,
    BarElement,
    LinearScale,
    CategoryScale,
    Filler,
    Legend,
    Tooltip
  );
  registered = true;
}
