const $ = (selector) => document.querySelector(selector);

const request = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw Object.assign(
      new Error(typeof detail === "string" ? detail : detail?.[0]?.msg || "Something went wrong."),
      { status: response.status },
    );
  }
  return body;
};

const setBusy = (button, busy, busyLabel) => {
  if (!button.dataset.label) button.dataset.label = button.querySelector("span").textContent;
  button.disabled = busy;
  button.classList.toggle("is-busy", busy);
  button.querySelector("span").textContent = busy ? busyLabel : button.dataset.label;
};

const showPanel = (name) => {
  ["invite", "signin", "clubs"].forEach((panelName) => {
    $(`#${panelName}-panel`).hidden = panelName !== name;
  });
  $(".entry-tabs").hidden = name === "clubs";
  document.querySelectorAll(".entry-tab").forEach((tab) => {
    const active = tab.dataset.panel === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
};

document.querySelectorAll(".entry-tab").forEach((tab) => {
  tab.addEventListener("click", () => showPanel(tab.dataset.panel));
});

const parseClubCode = (value) => {
  let candidate = value.trim();
  if (!candidate) return "";
  if (!candidate.includes("://") && /^clubs\//i.test(candidate)) {
    candidate = candidate.replace(/^clubs\//i, "").split(/[/?#]/)[0];
  }
  try {
    const url = new URL(candidate.includes("://") ? candidate : `https://${candidate}`);
    const parts = url.pathname.split("/").filter(Boolean);
    const clubsIndex = parts.indexOf("clubs");
    if (clubsIndex >= 0 && parts[clubsIndex + 1]) candidate = parts[clubsIndex + 1];
    else if (url.hostname.includes(".")) candidate = parts[0] || "";
  } catch {
    candidate = candidate.replace(/^clubs\//i, "").split(/[/?#]/)[0];
  }
  try {
    candidate = decodeURIComponent(candidate);
  } catch {
    return "";
  }
  candidate = candidate.trim().toLowerCase();
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(candidate) ? candidate : "";
};

$("#find-club-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = $("#find-club-error");
  const button = $("#find-club-submit");
  const slug = parseClubCode($("#club-slug-input").value);
  error.textContent = "";
  if (!slug) {
    error.textContent = "Paste a complete invitation link or enter a club code.";
    $("#club-slug-input").focus();
    return;
  }
  setBusy(button, true, "Finding your club…");
  try {
    await request(`/api/public/clubs/${encodeURIComponent(slug)}`);
    location.href = `/clubs/${encodeURIComponent(slug)}`;
  } catch (requestError) {
    error.textContent = requestError.status === 404
      ? "We couldn't find that club. Check the invitation and try again."
      : requestError.message;
    setBusy(button, false);
  }
});

const clubMeta = (club) => club.organizer_branch || club.organizer_name || "Your reading community";

const renderClubs = (clubs) => {
  const list = $("#club-choice-list");
  list.replaceChildren();
  clubs.forEach((club) => {
    const button = document.createElement("button");
    button.className = "club-choice";
    button.type = "button";
    button.innerHTML = '<span class="club-choice-mark" aria-hidden="true">B</span><span class="club-choice-copy"><strong></strong><small></small></span><b aria-hidden="true">→</b>';
    button.querySelector("strong").textContent = club.name;
    button.querySelector("small").textContent = clubMeta(club);
    button.addEventListener("click", async () => {
      $("#club-choice-error").textContent = "";
      button.disabled = true;
      try {
        await request(`/participant/auth/clubs/${encodeURIComponent(club.slug)}/select`, { method: "POST" });
        location.href = "/dashboard";
      } catch (error) {
        $("#club-choice-error").textContent = error.message;
        button.disabled = false;
      }
    });
    list.append(button);
  });
  showPanel("clubs");
};

$("#global-login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = $("#global-login-error");
  const button = $("#global-login-submit");
  error.textContent = "";
  if (!form.reportValidity()) return;
  setBusy(button, true, "Signing in…");
  try {
    const clubs = await request("/participant/auth/login/global", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    renderClubs(clubs);
    form.reset();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    setBusy(button, false);
  }
});

$("#participant-signout").addEventListener("click", async () => {
  await request("/participant/auth/logout", { method: "POST" }).catch(() => null);
  $("#club-choice-list").replaceChildren();
  showPanel("signin");
});

(async () => {
  try {
    await request("/participant/auth/me");
    const clubs = await request("/participant/auth/clubs");
    if (clubs.length) renderClubs(clubs);
  } catch {
    // The landing page defaults to the invitation path for signed-out visitors.
  }
})();
