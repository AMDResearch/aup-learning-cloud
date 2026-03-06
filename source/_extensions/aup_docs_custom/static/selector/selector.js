import { domReady, logDebug } from "./utils.js";
import {
  updateTOC2ContentsList,
  updateTOC2OptionsList,
} from "./selector-toc.js";

const GROUP_QUERY = ".rocm-docs-selector-group";
const OPTION_QUERY = ".rocm-docs-selector-option";
const COND_QUERY = "[data-show-when],[data-disable-when]";
const DEFAULT_OPTION_CLASS = "rocm-docs-selector-option-default";
const DISABLED_CLASS = "rocm-docs-disabled";
const HIDDEN_CLASS = "rocm-docs-hidden";
const SELECTED_CLASS = "rocm-docs-selected";
const STORAGE_KEY = "aup-docs-selector-state";

/** GPU value -> --gpu= value for Quick Start install commands (single code block) */
const GPU_TO_GPU_TYPE = {
  "ai-r9700": "rdna4",
  "ai-r9600d": "rdna4",
  "rx-9070-xt": "rdna4",
  "rx-9070-gre": "rdna4",
  "rx-9070": "rdna4",
  "rx-9060-xt-lp": "rdna4",
  "rx-9060-xt": "rdna4",
  "rx-9060": "rdna4",
  "w7900-dual-slot": "rdna4",
  "w7900": "rdna4",
  "w7800-48gb": "rdna4",
  "w7800": "rdna4",
  "w7700": "rdna4",
  "v710": "rdna4",
  "rx-7900-xtx": "rdna4",
  "rx-7900-xt": "rdna4",
  "rx-7900-gre": "rdna4",
  "rx-7800-xt": "rdna4",
  "rx-7700-xt": "rdna4",
  "rx-7700": "rdna4",
  "max-pro-395": "strix-halo",
  "max-pro-390": "strix-halo",
  "max-pro-385": "strix-halo",
  "max-pro-380": "strix-halo",
  "max-395": "strix-halo",
  "max-390": "strix-halo",
  "max-385": "strix-halo",
  "9-hx-375": "strix",
  "9-hx-370": "strix",
  "9-365": "strix",
};

const isDefaultOption = (elem) => elem.classList.contains(DEFAULT_OPTION_CLASS);
const disable = (elem) => {
  elem.classList.add(DISABLED_CLASS);
  elem.setAttribute("aria-disabled", "true");
  elem.setAttribute("tabindex", "-1");
};
const enable = (elem) => {
  elem.classList.remove(DISABLED_CLASS);
  elem.setAttribute("aria-disabled", "false");
  elem.setAttribute("tabindex", "0");
};
const hide = (elem) => {
  elem.classList.add(HIDDEN_CLASS);
  elem.setAttribute("aria-hidden", "true");
};
const show = (elem) => {
  elem.classList.remove(HIDDEN_CLASS);
  elem.setAttribute("aria-hidden", "false");
};
const select = (elem) => {
  elem.classList.add(SELECTED_CLASS);
  elem.setAttribute("aria-checked", "true");
};
const deselect = (elem) => {
  elem.classList.remove(SELECTED_CLASS);
  elem.setAttribute("aria-checked", "false");
};

function syncStateToURL() {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) {
    params.set(key, value);
  }
  const newURL = params.toString()
    ? `${window.location.pathname}?${params.toString()}${window.location.hash}`
    : `${window.location.pathname}${window.location.hash}`;
  window.history.replaceState({}, "", newURL);
  logDebug("URL updated:", newURL);
}

function getStateFromURL() {
  const params = new URLSearchParams(window.location.search);
  const urlState = {};
  for (const [key, value] of params) {
    urlState[key] = value;
  }
  return urlState;
}

function syncStateToLocalStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    logDebug("localStorage updated:", state);
  } catch (err) {
    console.warn("[AUPSelector] Failed to save to localStorage:", err);
  }
}

function getStateFromLocalStorage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return {};
    const parsed = JSON.parse(stored);
    logDebug("localStorage loaded:", parsed);
    return parsed;
  } catch (err) {
    console.warn("[AUPSelector] Failed to read from localStorage:", err);
    return {};
  }
}

const state = {};
function getState() {
  return { ...state };
}
function setState(updates) {
  Object.assign(state, updates);
  logDebug("State updated:", state);
  syncStateToURL();
  syncStateToLocalStorage();
}

function parseConditions(attrName, raw) {
  if (!raw) return null;
  try {
    const conditions = JSON.parse(raw);
    if (typeof conditions !== "object" || Array.isArray(conditions)) {
      console.warn(`[AUPSelector] Invalid '${attrName}' format:`, raw);
      return null;
    }
    return conditions;
  } catch (err) {
    console.error(`[AUPSelector] Couldn't parse '${attrName}' conditions:`, err);
    return null;
  }
}

function matchesConditions(conditions, currentState) {
  for (const [key, expected] of Object.entries(conditions)) {
    const actual = currentState[key];
    if (actual === undefined) return false;
    if (Array.isArray(expected)) {
      if (!expected.includes(actual)) return false;
    } else if (actual !== expected) {
      return false;
    }
  }
  return true;
}

function shouldBeDisabled(elem) {
  const raw = elem.dataset.disableWhen;
  if (!raw) return false;
  const conditions = parseConditions("disable-when", raw);
  if (!conditions) return false;
  return matchesConditions(conditions, state);
}

function shouldBeShown(elem) {
  const raw = elem.dataset.showWhen;
  if (!raw) return true;
  const conditions = parseConditions("show-when", raw);
  if (!conditions) return true;
  return matchesConditions(conditions, state);
}

function handleOptionSelect(e) {
  const option = e.currentTarget;
  if (
    option.classList.contains(DISABLED_CLASS) ||
    option.classList.contains(SELECTED_CLASS)
  ) {
    return;
  }
  const { selectorKey: key, selectorValue: value } = option.dataset;
  if (!key || !value) return;
  const allOptions = document.querySelectorAll(
    `${OPTION_QUERY}[data-selector-key="${key}"]`
  );
  allOptions.forEach((opt) => {
    if (opt.dataset.selectorValue === value) select(opt);
    else deselect(opt);
  });
  setState({ [key]: value });
  updateVisibility();
}

function handleOptionKeydown(e) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    handleOptionSelect(e);
  }
}

function reconcileGroupSelections() {
  const currentState = getState();
  const updates = {};
  document.querySelectorAll(GROUP_QUERY).forEach((group) => {
    if (
      group.classList.contains(HIDDEN_CLASS) ||
      group.closest(`.${HIDDEN_CLASS}`)
    ) {
      return;
    }
    const options = Array.from(group.querySelectorAll(OPTION_QUERY));
    if (!options.length) return;
    const groupKey = group.dataset.selectorKey || options[0].dataset.selectorKey;
    if (!groupKey) return;
    const enabledVisible = options.filter(
      (opt) =>
        !opt.classList.contains(DISABLED_CLASS) &&
        !opt.classList.contains(HIDDEN_CLASS)
    );
    if (!enabledVisible.length) {
      options.forEach(deselect);
      return;
    }
    const currentlySelected = options.find((opt) =>
      opt.classList.contains(SELECTED_CLASS)
    );
    const selectedStillValid =
      currentlySelected && enabledVisible.includes(currentlySelected);
    if (selectedStillValid) {
      const selectedValue = currentlySelected.dataset.selectorValue;
      if (selectedValue && currentState[groupKey] !== selectedValue) {
        updates[groupKey] = selectedValue;
      }
      return;
    }
    let replacement;
    const stateValue = currentState[groupKey];
    if (stateValue) {
      replacement = enabledVisible.find(
        (opt) => opt.dataset.selectorValue === stateValue
      );
    }
    if (!replacement) replacement = enabledVisible.find(isDefaultOption);
    if (!replacement) replacement = enabledVisible[0];
    if (!replacement) return;
    options.forEach(deselect);
    select(replacement);
    const newValue = replacement.dataset.selectorValue;
    if (newValue && currentState[groupKey] !== newValue) {
      updates[groupKey] = newValue;
    }
  });
  const changedKeys = Object.keys(updates);
  if (changedKeys.length > 0) {
    setState(updates);
    return true;
  }
  return false;
}

let isUpdatingVisibility = false;
function updateVisibility() {
  if (isUpdatingVisibility) return;
  isUpdatingVisibility = true;
  try {
    let stateChanged = false;
    let iterations = 0;
    do {
      document.querySelectorAll(COND_QUERY).forEach((elem) => {
        if (elem.dataset.showWhen !== undefined) {
          if (shouldBeShown(elem)) show(elem);
          else hide(elem);
        }
        if (elem.dataset.disableWhen !== undefined) {
          if (shouldBeDisabled(elem)) disable(elem);
          else enable(elem);
        }
      });
      stateChanged = reconcileGroupSelections();
      iterations += 1;
    } while (stateChanged && iterations < 5);
    updateTOC2OptionsList();
    updateTOC2ContentsList();
    updateInstallCommandsGpuType();
  } finally {
    isUpdatingVisibility = false;
  }
}

function updateInstallCommandsGpuType() {
  const container = document.querySelector(".rocm-docs-install-commands");
  if (!container) return;
  const pre = container.querySelector("pre");
  if (!pre) return;
  const gpu = state.gpu;
  const gpuType = (gpu && GPU_TO_GPU_TYPE[gpu]) || "rdna4";
  const text = pre.textContent || "";
  const newText = text.replace(/--gpu=\S+/m, `--gpu=${gpuType}`);
  if (newText === text && pre.querySelector(".rocm-docs-gpu-type-value")) return;
  const withHighlight = newText.replace(
    /--gpu=(\S+)/m,
    '--gpu=<span class="rocm-docs-gpu-type-value">$1</span>'
  );
  pre.innerHTML = withHighlight;
}

domReady(() => {
  const selectorOptions = document.querySelectorAll(OPTION_QUERY);
  if (!selectorOptions?.length) {
    const url = new URL(window.location);
    url.search = "";
    window.history.replaceState({}, "", url);
    return;
  }
  const defaultState = {};
  const localStorageState = getStateFromLocalStorage();
  const urlState = getStateFromURL();
  selectorOptions.forEach((option) => {
    option.addEventListener("click", handleOptionSelect);
    option.addEventListener("keydown", handleOptionKeydown);
    if (isDefaultOption(option)) {
      const { selectorKey: key, selectorValue: value } = option.dataset;
      if (key && value && defaultState[key] === undefined) {
        defaultState[key] = value;
      }
    }
  });
  const initialState = {
    ...defaultState,
    ...localStorageState,
    ...urlState,
  };
  for (const [key, value] of Object.entries(initialState)) {
    const allOptions = document.querySelectorAll(
      `${OPTION_QUERY}[data-selector-key="${key}"]`
    );
    allOptions.forEach((opt) => {
      if (opt.dataset.selectorValue === value) select(opt);
      else deselect(opt);
    });
  }
  setState(initialState);
  updateVisibility();
  updateInstallCommandsGpuType();
  document.querySelectorAll(GROUP_QUERY).forEach((group) => {
    group.classList.add("rocm-docs-selector-initialized");
  });
});
