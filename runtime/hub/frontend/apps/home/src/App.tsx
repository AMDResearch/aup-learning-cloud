// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

import { useState, useEffect, useCallback } from "react";
import type { NotificationItem, Resource, ResourceGroup, UserQuotaInfo, UserDetail } from "@auplc/shared";
import {
  getNotifications,
  getMyQuota,
  getMyUsage,
  getResources,
  getResourceType,
  getResourceTypeLabel,
  PLATFORM_NAME,
  fetchPlatformInfo,
} from "@auplc/shared";
import onboardingLaunchWorkspaceUrl from "./onboarding-launch-workspace.png";
import onboardingResourcePickerUrl from "./onboarding-resource-picker.png";
import onboardingDeveloperProgramQrUrl from "./onboarding-developer-program-qr.png";

type Theme = "light" | "dark";
function getInitialTheme(): Theme {
  const stored =
    (localStorage.getItem("auplc-theme") as Theme | null) ??
    (localStorage.getItem("jupyterhub-bs-theme") as Theme | null);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-bs-theme", t);
  localStorage.setItem("auplc-theme", t);
  localStorage.setItem("jupyterhub-bs-theme", t);
}
applyTheme(getInitialTheme());

interface HomeData {
  server_active: boolean;
  server_url: string;
}

interface OnboardingState {
  should_show: boolean;
  dismissed_at: string | null;
}

type OnboardingStep = 0 | 1 | 2;

const DEVELOPER_PROGRAM_URL = "https://www.amd.com/en/developer/ai-dev-program.html?utm_source=Generic&utm_campaign=AUP&utm_id=AUP";

declare global {
  interface Window {
    HOME_DATA?: HomeData;
    AVAILABLE_RESOURCES?: string[];
  }
}

const jhdata = window.jhdata ?? {
  base_url: "/hub/",
  xsrf_token: "",
  user: "student",
};

const baseUrl = jhdata.base_url ?? "/hub/";

const homeData: HomeData = window.HOME_DATA ?? {
  server_active: false,
  server_url: `${baseUrl.replace(/\/?$/, "/")}user/${jhdata.user ?? "student"}/`,
};

const homepageAnnouncementTitleStyles = `
.homepage-announcement-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.35;
  margin-bottom: 0.2rem;
  color: var(--home-text);
}
.homepage-announcement-title p,
.homepage-announcement-title ul,
.homepage-announcement-title ol {
  font: inherit;
  color: inherit;
  line-height: inherit;
  margin: 0;
}
`;

async function fetchLegacyAnnouncement(): Promise<string | null> {
  const resp = await fetch(`${baseUrl}static/announcement.txt`);
  if (!resp.ok) throw new Error("Not found");

  const data = (await resp.text()).trim();
  return data || null;
}

function HomepageAnnouncementCard({ item }: { item: NotificationItem }) {
  const eyebrow = item.eyebrow?.trim() || "Announcement";
  const sanitizedTitleHtml = item.titleHtml.trim();
  const sanitizedMessageHtml = item.messageHtml.trim();

  return (
    <div className="news-card">
      <div className="news-meta">{eyebrow}</div>
      {sanitizedTitleHtml && (
        <div
          aria-level={4}
          className="homepage-announcement-title"
          dangerouslySetInnerHTML={{ __html: sanitizedTitleHtml }}
          role="heading"
        />
      )}
      {sanitizedMessageHtml && (
        <div dangerouslySetInnerHTML={{ __html: sanitizedMessageHtml }} />
      )}
      {item.link && (
        <p>
          <a href={item.link.url} rel={item.link.rel ?? "noopener noreferrer"}>
            {item.link.label}
          </a>
        </p>
      )}
    </div>
  );
}

function formatResourceSpecs(r: Resource): string {
  const req = r.requirements;
  const parts: string[] = [];
  const cpu = parseFloat(req.cpu);
  if (cpu > 0) parts.push(`${req.cpu} CPU`);
  const memNum = parseFloat(req.memory);
  if (memNum > 0) parts.push(req.memory.replace("Gi", "GB"));
  if (req["amd.com/gpu"]) parts.push(`${req["amd.com/gpu"]} GPU`);
  if (req["amd.com/npu"]) parts.push(`${req["amd.com/npu"]} NPU`);
  return parts.join(", ");
}

function getAcceleratorType(r: Resource): "gpu" | "npu" | "cpu" {
  if (r.requirements["amd.com/gpu"]) return "gpu";
  if (r.requirements["amd.com/npu"]) return "npu";
  return "cpu";
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}


function formatMins(m: number): string {
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r > 0 ? `${h}h ${r}m` : `${h}h`;
}

function App() {
  const [serverActive, setServerActive] = useState(homeData.server_active);
  const [stopping, setStopping] = useState(false);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [showUsage, setShowUsage] = useState(false);
  const [usageData, setUsageData] = useState<UserDetail | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [homepageAnnouncements, setHomepageAnnouncements] = useState<NotificationItem[]>([]);
  const [legacyAnnouncement, setLegacyAnnouncement] = useState<string | null>(null);
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(true);
  const [resourcesError, setResourcesError] = useState<string | null>(null);
  const [stopError, setStopError] = useState<string | null>(null);
  const [quota, setQuota] = useState<UserQuotaInfo | null>(null);

  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);
  const [onboardingLoading, setOnboardingLoading] = useState(true);
  const [onboardingError, setOnboardingError] = useState<string | null>(null);
  const [dismissingOnboarding, setDismissingOnboarding] = useState(false);
  const [showOnboardingModal, setShowOnboardingModal] = useState(false);
  const [onboardingStep, setOnboardingStep] = useState<OnboardingStep>(0);

  const [platformName, setPlatformName] = useState<string>(PLATFORM_NAME);

  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const toggleTheme = useCallback(() => {
    setTheme(t => {
      const next = t === "light" ? "dark" : "light";
      applyTheme(next);
      return next;
    });
  }, []);

  useEffect(() => {
    fetchPlatformInfo().then(info => setPlatformName(info.platform)).catch(() => {});
  }, []);

  useEffect(() => {
    getMyQuota().then(setQuota).catch(() => {});
  }, []);

  useEffect(() => {
    fetch(`${baseUrl}api/onboarding/me`, {
      headers: {
        Accept: "application/json",
        "X-XSRFToken": jhdata.xsrf_token ?? "",
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch onboarding state (HTTP ${res.status})`);
        return res.json();
      })
      .then((data: OnboardingState) => {
        setOnboarding(data);
        setOnboardingError(null);
        if (data.should_show) {
          setOnboardingStep(0);
          setShowOnboardingModal(true);
        }
      })
      .catch((err) => setOnboardingError(err instanceof Error ? err.message : "Unable to load onboarding status."))
      .finally(() => setOnboardingLoading(false));
  }, []);

  const dismissOnboarding = useCallback(async (): Promise<boolean> => {
    if (dismissingOnboarding) return false;
    setDismissingOnboarding(true);
    setOnboardingError(null);
    try {
      const res = await fetch(`${baseUrl}api/onboarding/dismiss`, {
        method: "POST",
        headers: {
          "X-XSRFToken": jhdata.xsrf_token ?? "",
        },
      });
      if (res.ok) {
        try {
          const data = await res.json();
          setOnboarding(data);
        } catch {
          setOnboarding((prev) => (prev ? { ...prev, should_show: false } : null));
        }
        return true;
      } else {
        setOnboardingError(`Failed to dismiss onboarding (HTTP ${res.status})`);
        return false;
      }
    } catch (err) {
      setOnboardingError(err instanceof Error ? err.message : "Network error while dismissing onboarding.");
      return false;
    } finally {
      setDismissingOnboarding(false);
    }
  }, [dismissingOnboarding]);

  const openOnboarding = useCallback(() => {
    setOnboardingStep(0);
    setShowOnboardingModal(true);
  }, []);

  const handleCloseOnboarding = useCallback(() => {
    setShowOnboardingModal(false);
    setOnboardingStep(0);
    if (onboarding?.should_show) {
      void dismissOnboarding();
    }
  }, [dismissOnboarding, onboarding?.should_show]);

  const handleOnboardingDone = useCallback(async () => {
    if (onboarding?.should_show) {
      await dismissOnboarding();
    }
    setShowOnboardingModal(false);
    setOnboardingStep(0);
  }, [dismissOnboarding, onboarding?.should_show]);

  const goToPreviousOnboardingStep = useCallback(() => {
    setOnboardingStep((prev) => {
      if (prev === 2) return 1;
      return 0;
    });
  }, []);

  const goToNextOnboardingStep = useCallback(() => {
    setOnboardingStep((prev) => {
      if (prev === 0) return 1;
      return 2;
    });
  }, []);

  // Poll server status every 15s to keep launch bar in sync
  useEffect(() => {
    const poll = () => {
      fetch(`${baseUrl}api/users/${jhdata.user ?? "student"}`, {
        headers: {
          Accept: "application/json",
          "X-XSRFToken": jhdata.xsrf_token ?? "",
        },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data) setServerActive(Boolean(data.server));
        })
        .catch(() => {});
    };
    const id = setInterval(poll, 15_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadLegacyAnnouncement = async () => {
      const fallback = await fetchLegacyAnnouncement().catch(() => null);
      if (!cancelled) setLegacyAnnouncement(fallback);
    };

    const loadHomepageAnnouncements = async () => {
      try {
        const notifications = await getNotifications();
        const items = notifications.homepage.items;

        if (cancelled) return;

        if (items.length > 0) {
          setHomepageAnnouncements(items);
          setLegacyAnnouncement(null);
          return;
        }

        setHomepageAnnouncements([]);
        if (notifications.homepage.legacyAnnouncementFallback) {
          await loadLegacyAnnouncement();
        } else {
          setLegacyAnnouncement(null);
        }
      } catch {
        if (!cancelled) setHomepageAnnouncements([]);
        await loadLegacyAnnouncement();
      }
    };

    void loadHomepageAnnouncements();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    getResources()
      .then((data) => {
        setGroups(data.groups.filter((g) => g.resources.length > 0));
      })
      .catch((err) => {
        setResourcesError(
          err instanceof Error ? err.message : "Failed to load resources",
        );
      })
      .finally(() => setResourcesLoading(false));
  }, []);

  const handleStopClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.nativeEvent.stopImmediatePropagation();
      if (stopping) return;
      setShowStopConfirm(true);
    },
    [stopping],
  );

  const doStop = useCallback(async () => {
    setShowStopConfirm(false);
    setStopping(true);
    setStopError(null);
    try {
      const resp = await fetch(
        `${baseUrl}api/users/${jhdata.user}/server`,
        {
          method: "DELETE",
          headers: { "X-XSRFToken": jhdata.xsrf_token ?? "" },
        },
      );
      if (resp.ok || resp.status === 204 || resp.status === 202) {
        setServerActive(false);
      } else {
        setStopError(`Failed to stop server (HTTP ${resp.status})`);
      }
    } catch {
      setStopError("Network error — could not reach the server");
    } finally {
      setStopping(false);
    }
  }, []);

  const openUsage = useCallback(() => {
    setShowUsage(true);
    setUsageLoading(true);
    getMyUsage(30)
      .then(setUsageData)
      .catch(() => setUsageData(null))
      .finally(() => setUsageLoading(false));
  }, []);

  const totalResources = groups.reduce(
    (sum, g) => sum + g.resources.length,
    0,
  );

  return (
    <div className="home-page">
      <style>{homepageAnnouncementTitleStyles}</style>
      {/* Hero */}
      <section className="home-hero">
        <div className="container" style={{ position: "relative" }}>
          <nav className="hero-nav">
            <a href={`${baseUrl}spawn`}>
              <i className="fa fa-rocket"></i> Launch Server
            </a>
            <button className="hero-nav-btn onboarding-reopen-btn" onClick={openOnboarding} type="button" title="Open quick guide" aria-label="Open AUP quick guide">
              <i className="fa fa-question-circle"></i> Guide
            </button>
            <button className="hero-nav-btn" onClick={openUsage} type="button">
              <i className="fa fa-bar-chart"></i> Usage
            </button>
            {Boolean((jhdata as Record<string, unknown>).admin) && (
              <a href={`${baseUrl}admin/users`}>
                <i className="fa fa-cog"></i> Admin
              </a>
            )}
            <button className="theme-toggle" onClick={toggleTheme} title={theme === "light" ? "Dark mode" : "Light mode"}>
              <i className={`fa ${theme === "light" ? "fa-moon-o" : "fa-sun-o"}`}></i>
            </button>
          </nav>
          <p className="hero-greeting">
            {getGreeting()}, {jhdata.user ?? "student"}
          </p>
          <h1>
            Welcome to <span className="accent">{platformName}</span>
          </h1>
          <p className="hero-desc">
            Experience next-generation AI acceleration with AMD ROCm. Launch
            GPU-powered Jupyter notebooks for deep learning, computer vision,
            LLMs, and more.
          </p>
        </div>
      </section>

      {!onboardingLoading && onboardingError && !showOnboardingModal && (
        <div className="container">
          <div className="onboarding-error-subtle">
            <i className="fa fa-info-circle"></i> {onboardingError}
          </div>
        </div>
      )}

      {/* Launch Bar */}
      <div className="container">
        <div className="launch-bar">
          <div
            className={`lb-icon ${serverActive ? "running" : "stopped"}`}
          >
            <i className="fa fa-server"></i>
          </div>
          <div className="lb-info">
            <div className="lb-title">
              My Server
              {serverActive ? (
                <span className="status-badge running">
                  <span className="status-dot running"></span> Running
                </span>
              ) : (
                <span className="status-badge stopped">
                  <span className="status-dot stopped"></span> Stopped
                </span>
              )}
            </div>
            <div className="lb-desc">
              {stopError ? (
                <span className="lb-error">{stopError}</span>
              ) : stopping
                ? "Stopping your server\u2026"
                : serverActive
                  ? 'Your server is running \u2014 click "My Server" to open JupyterLab'
                  : "Choose a resource below and launch your Jupyter environment"}
              {quota?.enabled && (
                <span className="lb-quota-inline">
                  {" · Quota: "}
                  {quota.unlimited ? "Unlimited" : `${quota.balance} min remaining`}
                </span>
              )}
            </div>
          </div>
          <div className="lb-actions">
            {serverActive ? (
              <>
                <a
                  id="stop"
                  role="button"
                  className={`btn-home-sm danger${stopping ? " disabled" : ""}`}
                  onClick={handleStopClick}
                >
                  <i
                    className={`fa ${stopping ? "fa-spinner fa-spin" : "fa-stop"}`}
                  ></i>{" "}
                  {stopping ? "Stopping\u2026" : "Stop My Server"}
                </a>
                <a
                  id="start"
                  role="button"
                  className={`btn-launch${stopping ? " disabled" : ""}`}
                  href={stopping ? undefined : homeData.server_url}
                  onClick={stopping ? (e: React.MouseEvent) => e.preventDefault() : undefined}
                >
                  <i className={`fa ${stopping ? "fa-spinner fa-spin" : "fa-external-link"}`}></i>
                  {stopping ? " Stopping\u2026" : " My Server"}
                </a>
              </>
            ) : (
              <a
                id="start"
                role="button"
                className="btn-launch"
                href={`${baseUrl}spawn`}
              >
                <i className="fa fa-play"></i> Start My Server
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Quick Start */}
      <div className="container">
        <section className="home-section" style={{ paddingBottom: "0.5rem" }}>
          <div className="qs-strip">
            <div className="qs-step">
              <div className="qs-num">1</div>
              <div className="qs-step-text">
                <h4>Choose a Resource</h4>
                <p>Pick a pre-configured environment below</p>
              </div>
            </div>
            <div className="qs-step">
              <div className="qs-num">2</div>
              <div className="qs-step-text">
                <h4>Configure &amp; Launch</h4>
                <p>Select GPU, set runtime, then launch</p>
              </div>
            </div>
            <div className="qs-step">
              <div className="qs-num">3</div>
              <div className="qs-step-text">
                <h4>Start Learning</h4>
                <p>Open notebooks and run experiments</p>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Available Resources (dynamic from API) */}
      <div className="container">
        <section className="home-section">
          <div className="home-section-header">
            <h2>Available Resources</h2>
            {serverActive ? (
              <span style={{ fontSize: "0.78rem", color: "var(--home-text-muted)" }}>
                <i className="fa fa-info-circle"></i> Stop your server to launch a different resource
              </span>
            ) : (
              <a href={`${baseUrl}spawn`}>
                View all options{" "}
                <i
                  className="fa fa-arrow-right"
                  style={{ fontSize: "0.7rem" }}
                ></i>
              </a>
            )}
          </div>

          {resourcesLoading ? (
            <div className="resources-loading">
              <i className="fa fa-spinner fa-spin"></i> Loading resources…
            </div>
          ) : resourcesError ? (
            <div className="resources-error">
              <p>
                <strong>Error:</strong> {resourcesError}
              </p>
              <p>
                <a href={`${baseUrl}spawn`}>Go to Spawner</a>
              </p>
            </div>
          ) : totalResources === 0 ? (
            <div className="resources-empty">
              <p>
                No resources available.{" "}
                <a href={`${baseUrl}spawn`}>Go to Spawner</a>
              </p>
            </div>
          ) : (
            groups.map((group) => (
              <div className="resource-group" key={group.name}>
                <div className="resource-group-header">
                  <h3>{group.displayName}</h3>
                  <span className="group-count">
                    {group.resources.length}{" "}
                    {group.resources.length === 1 ? "resource" : "resources"}
                  </span>
                </div>
                <div className="resources-grid">
                  {group.resources.map((resource) => {
                    const accelType = getAcceleratorType(resource);
                    return (
                      <a
                        className={`resource-card${serverActive ? " disabled" : ""}`}
                        href={serverActive ? undefined : `${baseUrl}spawn?resource=${encodeURIComponent(resource.key)}`}
                        key={resource.key}
                        onClick={(e) => {
                          if (serverActive) { e.preventDefault(); }
                        }}
                        title={serverActive ? "Stop your running server first" : undefined}
                      >
                        <div className="resource-card-top">
                          <div className="resource-card-info">
                            <h4>
                              {resource.metadata?.description ?? resource.key}
                            </h4>
                            {resource.metadata?.subDescription && (
                              <p>{resource.metadata.subDescription}</p>
                            )}
                          </div>
                          <span className="resource-card-arrow">
                            <i className="fa fa-arrow-right"></i>
                          </span>
                        </div>
                        <div className="resource-card-tags">
                          <span
                            className="resource-type-badge"
                            data-resource-type={getResourceType(resource)}
                          >
                            {getResourceTypeLabel(resource)}
                          </span>
                          <span
                            className={`resource-tag tag-${accelType}`}
                          >
                            {accelType.toUpperCase()}
                          </span>
                          <span className="resource-tag tag-spec">
                            {formatResourceSpecs(resource)}
                          </span>
                          {resource.metadata?.allowGitClone && (
                            <span className="resource-tag tag-git">
                              <i
                                className="fa fa-code-fork"
                                style={{ fontSize: "0.55rem" }}
                              ></i>{" "}
                              Git
                            </span>
                          )}
                        </div>
                      </a>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </section>
      </div>

      {/* Docs + News */}
      <div className="container">
        <section className="home-section" style={{ paddingTop: 0 }}>
          <div className="home-two-col">
            <div>
              <div className="home-section-header">
                <h2>Documentation</h2>
              </div>
              <div className="doc-list">
                <a
                  className="doc-item"
                  href="https://rocm.docs.amd.com/"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#fce8e6", color: "#d93025" }}
                  >
                    <i className="fa fa-book"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AMD ROCm Documentation</h4>
                    <p>Official ROCm platform docs &amp; API references</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://amdresearch.github.io/aup-learning-cloud/"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#e8f0fe", color: "#1a73e8" }}
                  >
                    <i className="fa fa-laptop"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AUP Learning Cloud User Guide</h4>
                    <p>Notebooks, terminals &amp; extensions</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://amdresearch.github.io/aup-learning-cloud/installation/single-node.html"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#f3e8fd", color: "#9334e6" }}
                  >
                    <i className="fa fa-rocket"></i>
                  </div>
                  <div className="doc-text">
                    <h4>Platform Getting Started</h4>
                    <p>First-time user guide for AUP Learning Cloud setup</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://github.com/AMDResearch/aup-learning-cloud"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#e6f4ea", color: "#1e8e3e" }}
                  >
                    <i className="fa fa-code-fork"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AUP Learning Cloud GitHub Repository</h4>
                    <p>Clone &amp; launch your own AUP Learning Cloud</p>
                  </div>
                </a>
              </div>
            </div>
            <div>
              <div className="home-section-header">
                <h2 id="home-news-updates-heading">News &amp; Updates</h2>
              </div>
              <div
                aria-labelledby="home-news-updates-heading"
                className="news-list"
                role="region"
                tabIndex={0}
              >
                {homepageAnnouncements.map((item) => (
                  <HomepageAnnouncementCard key={`${item.id}:${item.version}`} item={item} />
                ))}
                {legacyAnnouncement && homepageAnnouncements.length === 0 && (
                  <div className="news-card">
                    <div className="news-meta">Announcement</div>
                    <h4>Platform Announcement</h4>
                    {/<[a-z][\s\S]*>/i.test(legacyAnnouncement) ? (
                      <div dangerouslySetInnerHTML={{ __html: legacyAnnouncement }} />
                    ) : (
                      <p>{legacyAnnouncement}</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Stop Server Confirm Modal */}
      {/* Stop Server Confirm Modal */}
      {showStopConfirm && (
        <div className="confirm-overlay" onClick={() => setShowStopConfirm(false)}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-icon">
              <i className="fa fa-exclamation-triangle"></i>
            </div>
            <h3>Stop Server?</h3>
            <p>Any unsaved work in your notebooks may be lost. Are you sure you want to stop?</p>
            <div className="confirm-actions">
              <button className="btn-home-sm" onClick={() => setShowStopConfirm(false)}>
                Cancel
              </button>
              <button className="btn-home-sm danger" onClick={doStop}>
                <i className="fa fa-stop"></i> Stop Server
              </button>
            </div>
          </div>
        </div>
      )}

      {showOnboardingModal && (
        <div className="onboarding-overlay" onClick={handleCloseOnboarding}>
          <div
            aria-labelledby="onboarding-modal-title"
            aria-modal="true"
            className="onboarding-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
          >
            <div className="onboarding-modal-header">
              <div>
                <div className="onboarding-modal-eyebrow">AUP quick guide</div>
                <div className="onboarding-modal-step-label">Step {onboardingStep + 1} of 3</div>
              </div>
              <button className="onboarding-close" onClick={handleCloseOnboarding} type="button" title="Close onboarding">
                <i className="fa fa-times"></i>
              </button>
            </div>

            <div className="onboarding-modal-body">
              {onboardingStep === 0 && (
                <div className="onboarding-step-layout">
                  <div className="onboarding-panel-copy">
                    <span className="onboarding-kicker">Developer resources</span>
                    <h2 id="onboarding-modal-title">AMD Developer Program</h2>
                    <p>
                      Scan the QR code or open the Developer Program to explore documentation, tools, and updates beyond the platform.
                    </p>
                    <div className="onboarding-resource-summary">
                      Keep this page handy when you want deeper ROCm docs, learning paths, or AMD developer updates.
                    </div>
                  </div>
                  <div className="onboarding-dev-resources">
                    <div className="onboarding-qr-card" aria-label="Developer Program QR code">
                      <img src={onboardingDeveloperProgramQrUrl} alt="QR code for AMD Developer Program" />
                      <span>Scan to open AMD Developer Program</span>
                    </div>
                    <div className="onboarding-side-card">
                      <h3>Open the Developer Program</h3>
                      <p>Explore AMD documentation, tooling, community resources, and the latest developer updates.</p>
                      <a className="btn-launch" href={DEVELOPER_PROGRAM_URL} rel="noopener noreferrer" target="_blank">
                        <i className="fa fa-external-link"></i> AMD AI Developer Program
                      </a>
                    </div>
                  </div>
                </div>
              )}

              {onboardingStep === 1 && (
                <div className="onboarding-step-layout onboarding-step-layout-welcome">
                  <div className="onboarding-panel-copy">
                    <span className="onboarding-kicker">Welcome</span>
                    <h2 id="onboarding-modal-title">Welcome to {platformName}</h2>
                    <p>
                      This short guide will show you how to get started, where to launch your environment,
                      and where to find AMD developer resources later.
                    </p>
                    <div className="onboarding-feature-list">
                      <div className="onboarding-feature-card">
                        <strong>Pick a resource</strong>
                        <span>Choose the environment that fits your course, project, or experiment.</span>
                      </div>
                      <div className="onboarding-feature-card">
                        <strong>Launch Jupyter</strong>
                        <span>Start quickly with prepared notebooks, tools, and AMD acceleration already wired in.</span>
                      </div>
                      <div className="onboarding-feature-card">
                        <strong>Keep exploring</strong>
                        <span>Use the guide button anytime if you want a quick refresher later.</span>
                      </div>
                    </div>
                  </div>
                  <div className="onboarding-side-card onboarding-side-card-highlight">
                    <div className="onboarding-side-card-icon">
                      <i className="fa fa-graduation-cap"></i>
                    </div>
                    <h3>Three quick stops</h3>
                    <p>In less than a minute, you’ll know where to launch, what to expect, and where to go for developer support.</p>
                  </div>
                </div>
              )}

              {onboardingStep === 2 && (
                <div className="onboarding-step-layout">
                  <div className="onboarding-panel-copy">
                    <span className="onboarding-kicker">How to use</span>
                    <h2 id="onboarding-modal-title">Choose a resource and start learning</h2>
                    <p>
                      Pick a resource profile, launch Jupyter, and start from the notebooks and tools already prepared for you.
                    </p>
                    <div className="onboarding-tips-list">
                      <div className="onboarding-tip-row">
                        <span className="onboarding-tip-index">1</span>
                        <span>Review the available resources on the Home page and open the one that fits your workload.</span>
                      </div>
                      <div className="onboarding-tip-row">
                        <span className="onboarding-tip-index">2</span>
                        <span>Launch your environment, then open notebooks or JupyterLab from the running server.</span>
                      </div>
                    </div>
                  </div>
                  <div className="onboarding-shot-grid" aria-label="Guide screenshots">
                    <figure className="onboarding-shot-card">
                      <div className="onboarding-shot-window">
                        <div className="onboarding-shot-chrome" aria-hidden="true">
                          <span></span><span></span><span></span>
                        </div>
                        <img src={onboardingResourcePickerUrl} alt="Available Resources cards on the Home page" />
                      </div>
                      <figcaption>
                        <strong>Choose a resource</strong>
                        <span>Start from the Home page cards.</span>
                      </figcaption>
                    </figure>
                    <figure className="onboarding-shot-card">
                      <div className="onboarding-shot-window">
                        <div className="onboarding-shot-chrome" aria-hidden="true">
                          <span></span><span></span><span></span>
                        </div>
                        <img src={onboardingLaunchWorkspaceUrl} alt="Spawner page for configuring and launching a workspace" />
                      </div>
                      <figcaption>
                        <strong>Configure and launch</strong>
                        <span>Review options, then start Jupyter.</span>
                      </figcaption>
                    </figure>
                  </div>
                </div>
              )}
            </div>

            <div className="onboarding-modal-footer">
              <div className="onboarding-progress">
                <span className="onboarding-progress-count">{onboardingStep + 1} / 3</span>
                <div className="onboarding-progress-dots" aria-hidden="true">
                  {[0, 1, 2].map((step) => (
                    <span
                      className={`onboarding-progress-dot${step === onboardingStep ? " active" : ""}`}
                      key={step}
                    />
                  ))}
                </div>
              </div>

              <div className="onboarding-footer-actions">
                {onboardingStep > 0 && (
                  <button className="btn-home-sm" onClick={goToPreviousOnboardingStep} type="button">
                    Back
                  </button>
                )}
                {onboardingStep < 2 ? (
                  <button className="btn-launch" onClick={goToNextOnboardingStep} type="button">
                    Next
                  </button>
                ) : (
                  <button className="btn-launch" disabled={dismissingOnboarding} onClick={handleOnboardingDone} type="button">
                    {dismissingOnboarding ? "Saving..." : "Done"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Usage Modal */}
      {showUsage && (
        <div className="confirm-overlay" onClick={() => setShowUsage(false)}>
          <div className="usage-modal" onClick={(e) => e.stopPropagation()}>
            <div className="usage-modal-header">
              <h3><i className="fa fa-bar-chart"></i> My Usage</h3>
              <button className="usage-close" onClick={() => setShowUsage(false)}>
                <i className="fa fa-times"></i>
              </button>
            </div>
            {usageLoading ? (
              <div className="usage-loading">
                <i className="fa fa-spinner fa-spin"></i> Loading usage data…
              </div>
            ) : !usageData ? (
              <div className="usage-loading">No usage data available yet.</div>
            ) : (
              <div className="usage-body">
                <div className="usage-stats-row">
                  <div className="usage-stat">
                    <div className="usage-stat-value">{formatMins(usageData.total_minutes)}</div>
                    <div className="usage-stat-label">Total Usage</div>
                  </div>
                  <div className="usage-stat">
                    <div className="usage-stat-value">{usageData.total_sessions}</div>
                    <div className="usage-stat-label">Sessions</div>
                  </div>
                  <div className="usage-stat">
                    <div className="usage-stat-value">
                      {usageData.total_sessions > 0
                        ? formatMins(Math.round(usageData.total_minutes / usageData.total_sessions))
                        : "—"}
                    </div>
                    <div className="usage-stat-label">Avg / Session</div>
                  </div>
                </div>

                {usageData.by_resource.length > 0 && (
                  <div className="usage-section">
                    <h4>By Resource</h4>
                    <div className="usage-resource-list">
                      {usageData.by_resource.map((r) => (
                        <div className="usage-resource-item" key={r.resource_type}>
                          <span className="usage-resource-name">
                            {r.resource_display ?? r.resource_type}
                          </span>
                          <span className="usage-resource-detail">
                            {formatMins(r.minutes)} · {r.sessions} sessions
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {usageData.recent_sessions.length > 0 && (
                  <div className="usage-section">
                    <h4>Recent Sessions</h4>
                    <div className="usage-sessions-list">
                      {usageData.recent_sessions.slice(0, 10).map((s, i) => (
                        <div className="usage-session-item" key={i}>
                          <div className="usage-session-name">
                            {s.resource_display ?? s.resource_type}
                            {s.accelerator_display && (
                              <span className="usage-session-accel"> · {s.accelerator_display}</span>
                            )}
                          </div>
                          <div className="usage-session-meta">
                            {s.start_time.slice(0, 16).replace("T", " ")}
                            {s.duration_minutes != null && ` · ${formatMins(s.duration_minutes)}`}
                            <span className={`usage-session-status ${s.status}`}>{s.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
