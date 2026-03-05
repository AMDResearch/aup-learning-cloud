export function domReady(callback) {
  if (document.readyState !== "loading") {
    callback();
  } else {
    document.addEventListener("DOMContentLoaded", callback, { once: true });
  }
}

const DEBUG = false;
export const logDebug = (...args) => {
  if (DEBUG) {
    console.debug("[AUPSelector]", ...args);
  }
};
